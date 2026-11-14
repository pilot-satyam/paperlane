"""PostgreSQL connection for one server-selected paper account schema."""

import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def is_postgres_url(value):
    return str(value).startswith(('postgresql://', 'postgres://'))


def configured_database_url(default=None):
    """Use a deployment secret, then the ignored local development secret."""
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    local = Path(__file__).resolve().parent.parent / '.env.local'
    if local.is_file():
        for line in local.read_text(encoding='utf-8').splitlines():
            if line.startswith('DATABASE_URL='):
                return line.split('=', 1)[1].strip()
    return default


class PostgresConnection:
    """Small transaction wrapper retaining the exchange's DB-API call pattern."""

    is_postgres = True

    def __init__(self, url, schema='paperlane'):
        try:
            import psycopg
            from psycopg import sql
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError('PostgreSQL support needs: pip install -r backend/requirements-postgres.txt') from exc
        if not re.fullmatch(r'paperlane(?:_u_[0-9a-f]{32})?', schema):
            raise ValueError('Invalid account schema')
        parsed = urlparse(str(url))
        if parsed.hostname not in ('localhost', '127.0.0.1', '::1') and 'sslmode' not in parse_qs(parsed.query):
            self.connection = psycopg.connect(str(url), row_factory=dict_row, sslmode='require')
        else:
            self.connection = psycopg.connect(str(url), row_factory=dict_row)
        self._depth = 0
        try:
            ready = self.connection.execute('SELECT to_regclass(%s) AS account',
                                            (schema + '.account',)).fetchone()
            if not ready['account']:
                raise RuntimeError('PostgreSQL schema is missing; run Liquibase update before starting the app')
            self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            self.connection.close()
            raise

    def execute(self, sql, params=()):
        # The exchange uses positional SQLite placeholders. All SQL is static;
        # parameters are still bound by psycopg, never interpolated into SQL.
        return self.connection.execute(sql.replace('?', '%s'), params)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()

    def __enter__(self):
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._depth -= 1
        if self._depth == 0:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        return False
