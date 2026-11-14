"""Copy one local Paperlane account to an empty PostgreSQL database.

Stop the paper server before the final copy. The SQLite source is opened read-only
and remains available for rollback. This does not create public user accounts.
"""

import argparse
import sqlite3
from pathlib import Path

from server import DEFAULT_DB, INITIAL
from storage import PostgresConnection, configured_database_url


TABLES = (
    'account', 'positions', 'orders', 'trades', 'notes', 'quotes',
    'learning_progress', 'trade_plans', 'trade_technical',
)
IDENTITY_TABLES = ('orders', 'trades', 'trade_plans')


def source_rows(source):
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f'SQLite source does not exist: {source}')
    db = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN')
        found = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(TABLES) - found
        if missing:
            raise ValueError('SQLite source is missing tables: ' + ', '.join(sorted(missing)))
        result = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                  for table in TABLES}
        if len(result['account']) != 1 or result['account'][0]['id'] != 1:
            raise ValueError('Expected exactly one local account with id 1')
        if any(row['status'] == 'PENDING' for row in result['orders']):
            raise ValueError('Pending orders exist. Stop the server and cancel them before copying.')
        return result
    finally:
        db.close()


def require_empty_target(db):
    for table in TABLES:
        rows = db.execute(f'SELECT COUNT(*) AS count FROM {table}').fetchone()['count']
        if table == 'account':
            account = db.execute('SELECT id,cash,realized FROM account').fetchone()
            if rows != 1 or account != {'id': 1, 'cash': INITIAL, 'realized': 0.0}:
                raise ValueError('PostgreSQL target already has account data; choose an empty database')
        elif rows:
            raise ValueError(f'PostgreSQL target already contains {table} rows; refusing to overwrite data')


def copy(source, database_url):
    rows = source_rows(source)
    db = PostgresConnection(database_url)
    try:
        with db:
            require_empty_target(db)
            account = rows['account'][0]
            db.execute('UPDATE account SET cash=?,realized=? WHERE id=1',
                       (account['cash'], account['realized']))
            for table in TABLES:
                if table == 'account':
                    continue
                for row in rows[table]:
                    columns = tuple(row)
                    statement = (f'INSERT INTO {table} (' + ','.join(f'"{column}"' for column in columns) + ') VALUES ('
                                 + ','.join('?' for _ in columns) + ')')
                    db.execute(statement, tuple(row[column] for column in columns))
            for table in IDENTITY_TABLES:
                db.execute(
                    f"SELECT setval(pg_get_serial_sequence('paperlane.{table}','id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}),1), "
                    f"(SELECT COUNT(*) > 0 FROM {table}))"
                )
            for table in TABLES:
                actual = db.execute(f'SELECT COUNT(*) AS count FROM {table}').fetchone()['count']
                if actual != len(rows[table]):
                    raise RuntimeError(f'Count mismatch for {table}: source {len(rows[table])}, target {actual}')
        return {table: len(items) for table, items in rows.items()}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', default=str(DEFAULT_DB), help='Existing local SQLite file')
    parser.add_argument('--check', action='store_true', help='Check and count source records without connecting to PostgreSQL')
    args = parser.parse_args()
    try:
        if args.check:
            counts = {table: len(items) for table, items in source_rows(args.sqlite).items()}
        else:
            database_url = configured_database_url()
            if not database_url:
                parser.error('Set DATABASE_URL to the PostgreSQL connection string')
            counts = copy(args.sqlite, database_url)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f'Migration stopped: {exc}\n')
    print('Record counts: ' + ', '.join(f'{table}={count}' for table, count in counts.items()))
    if args.check:
        print('Source check only; no PostgreSQL records were changed.')
    else:
        print('Copy complete. SQLite source was not changed.')


if __name__ == '__main__':
    main()
