"""Create ignored local credentials and start Paperlane's PostgreSQL container."""

import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTGRES_ENV = ROOT / 'infra' / 'postgres.env'
APP_ENV = ROOT / '.env.local'


def write_secret(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        file.write(content)


def main():
    if POSTGRES_ENV.exists() != APP_ENV.exists():
        raise SystemExit('Only one local secret file exists. Inspect the files before retrying; refusing to overwrite credentials.')
    if not POSTGRES_ENV.exists():
        existing_volume = subprocess.run(
            ['docker', 'volume', 'inspect', 'paperlane_postgres_data'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if existing_volume.returncode == 0:
            raise SystemExit('A populated PostgreSQL volume may already exist. Restore its original credentials before starting it.')
        password = secrets.token_urlsafe(32)
        write_secret(POSTGRES_ENV, f'POSTGRES_USER=paperlane\nPOSTGRES_DB=paperlane\nPOSTGRES_PASSWORD={password}\n')
        write_secret(APP_ENV, f'DATABASE_URL=postgresql://paperlane:{password}@127.0.0.1:5432/paperlane\n')
        print('Created ignored local database credentials (not displayed).')
    else:
        print('Using existing ignored local database credentials.')
    subprocess.run(['docker', 'compose', 'up', '-d', 'postgres'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
