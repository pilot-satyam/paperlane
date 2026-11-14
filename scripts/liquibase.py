"""Run native Liquibase against Paperlane's PostgreSQL database."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from storage import configured_database_url, is_postgres_url  # noqa: E402

COMMANDS = ('validate', 'status', 'update', 'update-sql', 'history')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=COMMANDS)
    args = parser.parse_args()
    url = configured_database_url()
    if not url or not is_postgres_url(url):
        parser.error('Set DATABASE_URL or create the ignored .env.local with a PostgreSQL URL')
    parsed = urlparse(url)
    if not parsed.username or not parsed.password or not parsed.hostname or not parsed.path:
        parser.error('PostgreSQL URL needs a username, password, host and database')
    jdbc_url = f'jdbc:postgresql://{parsed.hostname}:{parsed.port or 5432}{parsed.path}'
    if parsed.query:
        jdbc_url += f'?{parsed.query}'
    env = os.environ.copy()
    env.update(LIQUIBASE_COMMAND_URL=jdbc_url,
               LIQUIBASE_COMMAND_USERNAME=unquote(parsed.username),
               LIQUIBASE_COMMAND_PASSWORD=unquote(parsed.password),
               LIQUIBASE_COMMAND_CHANGELOG_FILE='changelog.sql',
               LIQUIBASE_SEARCH_PATH=str(ROOT / 'db'),
               LIQUIBASE_LIQUIBASE_SCHEMA_NAME='public',
               LIQUIBASE_COMMAND_DEFAULT_SCHEMA_NAME='public')
    if sys.platform == 'darwin':
        java_home = subprocess.run(['/usr/libexec/java_home', '-v', '17'],
                                   text=True, capture_output=True, check=True).stdout.strip()
        env['JAVA_HOME'] = java_home
    command = ['liquibase', args.command]
    raise SystemExit(subprocess.call(command, env=env))


if __name__ == '__main__':
    main()
