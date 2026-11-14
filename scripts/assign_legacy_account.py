"""Assign the preserved pre-login ledger to one already signed-in identity."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from auth import AuthSettings, AuthStore, SCHEMA_PATTERN  # noqa: E402
from storage import configured_database_url  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True, help='Exact subject from GET /api/auth/me')
    args = parser.parse_args()
    settings = AuthSettings.from_environment()
    store = AuthStore(configured_database_url(), settings)
    from psycopg import sql
    with store.connect() as db:
        user = db.execute('''SELECT id, account_schema FROM paperlane_auth.app_users
                             WHERE issuer=%s AND subject=%s FOR UPDATE''',
                          (settings.issuer, args.subject)).fetchone()
        if not user:
            parser.error('Sign in with this identity once before assigning the old ledger')
        if user['account_schema'] == 'paperlane':
            print('The preserved ledger is already assigned to this identity.')
            return
        if not SCHEMA_PATTERN.fullmatch(user['account_schema']):
            parser.error('Stored account mapping is invalid')
        owner = db.execute("SELECT 1 FROM paperlane_auth.app_users WHERE account_schema='paperlane'").fetchone()
        if owner:
            parser.error('The preserved ledger is already assigned to another identity')
        for table in ('positions', 'orders', 'trades', 'notes', 'learning_progress',
                      'trade_plans', 'trade_technical'):
            found = db.execute(sql.SQL('SELECT 1 FROM {}.{} LIMIT 1').format(
                sql.Identifier(user['account_schema']), sql.Identifier(table))).fetchone()
            if found:
                parser.error('The new account already has activity; assignment requires a manual merge')
        db.execute("UPDATE paperlane_auth.app_users SET account_schema='paperlane' WHERE id=%s", (user['id'],))
        db.execute('DELETE FROM paperlane_auth.sessions WHERE user_id=%s', (user['id'],))
    print('Preserved ledger assigned. Sign in again to see the earlier trades.')


if __name__ == '__main__':
    main()
