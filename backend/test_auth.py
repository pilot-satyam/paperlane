"""Security boundary checks without contacting an external identity provider."""

import unittest

from auth import AuthSettings, SESSION_COOKIE
from server import Exchange, create_app


class FakeAuth:
    def __init__(self):
        self.settings = AuthSettings('https://example.auth0.com', 'client', 'secret',
                                     'http://127.0.0.1:8000', 'x' * 64)
        self.users = {
            'token-a': dict(id='a', display_name='A', subject='auth0|a', account_schema='paperlane_u_' + 'a' * 32),
            'token-b': dict(id='b', display_name='B', subject='auth0|b', account_schema='paperlane_u_' + 'b' * 32),
        }

    def resolve_session(self, token):
        return self.users.get(token)

    def csrf_token(self, token):
        return 'csrf-' + token

    def valid_csrf(self, token, supplied):
        return supplied == self.csrf_token(token)

    def revoke_session(self, token):
        self.users.pop(token, None)


class FakeManager:
    def __init__(self):
        self.accounts = {key: Exchange(':memory:') for key in ('a', 'b')}

    def get(self, user):
        return self.accounts[user['id']]

    def close(self):
        for account in self.accounts.values():
            account.db.close()


class AuthBoundaryTests(unittest.TestCase):
    def test_app_fails_closed_without_auth_configuration(self):
        exchange = Exchange(':memory:')
        try:
            with self.assertRaisesRegex(RuntimeError, 'Authentication is required'):
                create_app(exchange)
        finally:
            exchange.db.close()

    def setUp(self):
        self.auth = FakeAuth()
        self.manager = FakeManager()
        self.app = create_app(self.manager, auth=self.auth)
        self.anonymous = self.app.test_client()
        self.alice = self.app.test_client()
        self.bob = self.app.test_client()
        self.alice.set_cookie(SESSION_COOKIE, 'token-a')
        self.bob.set_cookie(SESSION_COOKIE, 'token-b')

    def tearDown(self):
        self.manager.close()

    def test_all_personal_api_routes_require_a_session(self):
        self.assertEqual(self.anonymous.get('/api/health').status_code, 200)
        self.assertEqual(self.anonymous.get('/api/auth/me').status_code, 401)
        for path in ('/api/state', '/api/investing/overview', '/api/report', '/api/learning', '/api/journal',
                     '/api/catalogue', '/api/options'):
            with self.subTest(path=path):
                self.assertEqual(self.anonymous.get(path).status_code, 401)
        self.assertEqual(self.anonymous.post('/api/orders', json={}).status_code, 401)
        self.assertEqual(self.anonymous.post('/api/reset', json={}).status_code, 401)

    def test_investing_overview_is_scoped_to_signed_in_account(self):
        order = {'symbol': 'RELIANCE', 'side': 'BUY', 'type': 'MARKET', 'quantity': 2}
        placed = self.alice.post('/api/orders', json=order,
                                 headers={'X-CSRF-Token': 'csrf-token-a'})
        self.assertEqual(placed.status_code, 200)
        alice = self.alice.get('/api/investing/overview')
        bob = self.bob.get('/api/investing/overview')
        self.assertEqual(alice.status_code, 200)
        self.assertEqual(bob.status_code, 200)
        self.assertEqual(alice.json['summary']['holding_count'], 1)
        self.assertEqual(bob.json['summary']['holding_count'], 0)
        self.assertEqual(alice.json['holdings'][0]['quantity'], 2)

    def test_csrf_origin_and_account_isolation(self):
        order = {'symbol': 'RELIANCE', 'side': 'BUY', 'type': 'MARKET', 'quantity': 1}
        self.assertEqual(self.alice.post('/api/orders', json=order).status_code, 403)
        self.assertEqual(self.alice.post('/api/orders', json=order, headers={
            'X-CSRF-Token': 'wrong'}).status_code, 403)
        self.assertEqual(self.alice.post('/api/orders', json=order, headers={
            'X-CSRF-Token': 'csrf-token-a', 'Origin': 'https://attacker.example'}).status_code, 403)
        placed = self.alice.post('/api/orders', json=order,
                                 headers={'X-CSRF-Token': 'csrf-token-a'})
        self.assertEqual(placed.status_code, 200)
        self.assertEqual(self.alice.get('/api/state').json['positions'][0]['quantity'], 1)
        self.assertEqual(self.bob.get('/api/state').json['positions'], [])
        self.assertEqual(self.bob.get('/api/report').json['summary']['fill_count'], 0)
        self.assertEqual(self.bob.post('/api/orders/' + str(placed.json['order']['id']) + '/cancel',
                                       json={}, headers={'X-CSRF-Token': 'csrf-token-b'}).status_code, 400)
        self.assertEqual(self.bob.post('/api/reset', json={},
                                       headers={'X-CSRF-Token': 'csrf-token-b'}).status_code, 200)
        self.assertEqual(self.alice.get('/api/report').json['summary']['fill_count'], 1)

    def test_logout_revokes_server_session(self):
        self.assertTrue(self.alice.get('/api/auth/me').json['authenticated'])
        response = self.alice.post('/api/auth/logout', headers={'X-CSRF-Token': 'csrf-token-a'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.alice.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.alice.get('/api/state').status_code, 401)

    def test_invalid_callback_returns_to_safe_retry_page(self):
        response = self.anonymous.get('/auth/callback?code=fake&state=missing')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['Location'], 'http://127.0.0.1:8000/?auth_error=signin')

    def test_localhost_redirects_to_cookie_host(self):
        response = self.anonymous.get('http://localhost:8000/?view=terminal')
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers['Location'], 'http://127.0.0.1:8000/?view=terminal')

    def test_login_preserves_existing_session(self):
        response = self.alice.get('/auth/login')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], 'http://127.0.0.1:8000/#terminal')
        self.assertNotIn(SESSION_COOKIE, response.headers.get('Set-Cookie', ''))


if __name__ == '__main__':
    unittest.main()
