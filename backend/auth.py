"""OIDC configuration and PostgreSQL-backed, account-scoped app sessions."""

import hashlib
import hmac
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SESSION_SECONDS = 8 * 60 * 60
SESSION_COOKIE = 'paperlane_sid'
ACCOUNT_TABLES = ('account', 'positions', 'orders', 'trades', 'notes', 'quotes',
                  'learning_progress', 'trade_plans', 'trade_technical')
SCHEMA_PATTERN = re.compile(r'^paperlane(?:_u_[0-9a-f]{32})?$')


def setting(name):
    """Environment takes precedence over the ignored local development file."""
    if name in os.environ:
        return os.environ[name].strip()
    local = Path(__file__).resolve().parent.parent / '.env.local'
    if local.is_file():
        for line in local.read_text(encoding='utf-8').splitlines():
            if line.startswith(name + '='):
                return line.split('=', 1)[1].strip()
    return ''


@dataclass(frozen=True)
class AuthSettings:
    issuer: str
    client_id: str
    client_secret: str
    base_url: str
    secret_key: str
    legacy_owner_sub: str = ''

    @classmethod
    def from_environment(cls):
        names = ('OIDC_ISSUER', 'OIDC_CLIENT_ID', 'OIDC_CLIENT_SECRET',
                 'PAPERLANE_BASE_URL', 'PAPERLANE_SESSION_SECRET')
        values = [setting(name) for name in names]
        missing = [name for name, value in zip(names, values) if not value]
        if missing:
            raise RuntimeError('Authentication is not configured. Set ' + ', '.join(missing) +
                               ' in the ignored .env.local or process environment. See AUTH0_SETUP.md.')
        issuer, client_id, client_secret, base_url, secret_key = values
        issuer = issuer.rstrip('/')
        base_url = base_url.rstrip('/')
        identity = urlparse(issuer)
        site = urlparse(base_url)
        if (identity.scheme != 'https' or not identity.hostname or identity.username or
                identity.password or identity.query or identity.fragment):
            raise RuntimeError('OIDC_ISSUER must be an HTTPS issuer URL')
        local = site.hostname in ('127.0.0.1', 'localhost')
        if ((site.scheme != 'https' and not (local and site.scheme == 'http')) or
                not site.hostname or site.path or site.query or site.fragment or
                site.username or site.password):
            raise RuntimeError('PAPERLANE_BASE_URL must be HTTPS, or HTTP on localhost for development')
        if len(secret_key) < 32:
            raise RuntimeError('PAPERLANE_SESSION_SECRET must contain at least 32 characters')
        return cls(issuer, client_id, client_secret, base_url, secret_key,
                   setting('PAPERLANE_LEGACY_OWNER_SUB'))

    @property
    def secure_cookies(self):
        return self.base_url.startswith('https://')


class AuthStore:
    """Only the Flask backend can create users, account schemas, and sessions."""

    def __init__(self, database_url, settings):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.dict_row = dict_row
        self.database_url = str(database_url)
        self.settings = settings
        with self.connect() as db:
            if not db.execute("SELECT to_regclass('paperlane_auth.app_users') AS users").fetchone()['users']:
                raise RuntimeError('Authentication schema is missing; run Liquibase update')

    def connect(self):
        parsed = urlparse(self.database_url)
        options = {'row_factory': self.dict_row, 'connect_timeout': 5}
        if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') and 'sslmode' not in parse_qs(parsed.query):
            options['sslmode'] = 'require'
        return self.psycopg.connect(self.database_url, **options)

    def get_or_create_user(self, issuer, subject, display_name=''):
        if issuer != self.settings.issuer or not isinstance(subject, str) or not 1 <= len(subject) <= 255:
            raise ValueError('Invalid authenticated identity')
        display_name = str(display_name or '')[:200]
        with self.connect() as db:
            existing = db.execute('''SELECT id, issuer, subject, display_name, account_schema, disabled_at
                                     FROM paperlane_auth.app_users WHERE issuer=%s AND subject=%s''',
                                  (issuer, subject)).fetchone()
            if existing:
                return self._user(existing)
        user_id = uuid.uuid4()
        legacy = bool(self.settings.legacy_owner_sub and subject == self.settings.legacy_owner_sub)
        schema = 'paperlane' if legacy else f'paperlane_u_{user_id.hex}'
        try:
            with self.connect() as db:
                if not legacy:
                    from psycopg import sql
                    db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                    for table in ACCOUNT_TABLES:
                        db.execute(sql.SQL('CREATE TABLE {}.{} (LIKE paperlane.{} INCLUDING ALL)').format(
                            sql.Identifier(schema), sql.Identifier(table), sql.Identifier(table)))
                    db.execute(sql.SQL('INSERT INTO {}.account(id,cash,realized) VALUES (1,1000000,0)').format(
                        sql.Identifier(schema)))
                row = db.execute('''INSERT INTO paperlane_auth.app_users
                                    (id,issuer,subject,display_name,account_schema) VALUES (%s,%s,%s,%s,%s)
                                    RETURNING id,issuer,subject,display_name,account_schema,disabled_at''',
                                 (user_id, issuer, subject, display_name, schema)).fetchone()
                return self._user(row)
        except self.psycopg.errors.UniqueViolation:
            # Another callback may have registered this identity first. The whole
            # attempted account/schema creation is rolled back with the conflict.
            with self.connect() as db:
                row = db.execute('''SELECT id,issuer,subject,display_name,account_schema,disabled_at
                                    FROM paperlane_auth.app_users WHERE issuer=%s AND subject=%s''',
                                 (issuer, subject)).fetchone()
                if row:
                    return self._user(row)
            raise

    @staticmethod
    def _user(row):
        if not SCHEMA_PATTERN.fullmatch(row['account_schema']):
            raise ValueError('Invalid account mapping')
        return dict(id=str(row['id']), issuer=row['issuer'], subject=row['subject'],
                    display_name=row['display_name'], account_schema=row['account_schema'],
                    disabled=row['disabled_at'] is not None)

    def create_session(self, user):
        if user['disabled']:
            raise PermissionError('This account is disabled')
        token = secrets.token_urlsafe(48)
        digest = hashlib.sha256(token.encode('ascii')).hexdigest()
        expiry = datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)
        with self.connect() as db:
            db.execute('''INSERT INTO paperlane_auth.sessions(token_hash,user_id,expires_at)
                          VALUES (%s,%s,%s)''', (digest, user['id'], expiry))
        return token

    def resolve_session(self, token):
        if not isinstance(token, str) or len(token) > 128 or len(token) < 32:
            return None
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with self.connect() as db:
            row = db.execute('''SELECT u.id,u.issuer,u.subject,u.display_name,u.account_schema,u.disabled_at
                                FROM paperlane_auth.sessions s
                                JOIN paperlane_auth.app_users u ON u.id=s.user_id
                                WHERE s.token_hash=%s AND s.revoked_at IS NULL
                                  AND s.expires_at>now() AND u.disabled_at IS NULL''',
                             (digest,)).fetchone()
            return self._user(row) if row else None

    def revoke_session(self, token):
        if not token:
            return
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('''UPDATE paperlane_auth.sessions SET revoked_at=now()
                          WHERE token_hash=%s AND revoked_at IS NULL''', (digest,))

    def csrf_token(self, session_token):
        return hmac.new(self.settings.secret_key.encode('utf-8'),
                        ('paperlane-csrf:' + session_token).encode('utf-8'),
                        hashlib.sha256).hexdigest()

    def valid_csrf(self, session_token, supplied):
        return isinstance(supplied, str) and hmac.compare_digest(
            self.csrf_token(session_token), supplied)
