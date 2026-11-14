# PostgreSQL setup

Paperlane uses PostgreSQL for paper accounts, trades, notes, learning progress, and revocable login sessions. Liquibase manages the schema in [db/changelog.sql](db/changelog.sql). Flask checks for the schema at startup; it does not create the PostgreSQL tables itself.

## Local setup

1. Install and start PostgreSQL. On macOS with Homebrew, `brew services start postgresql@17` is one option.
2. Create a database and login role for Paperlane with a strong password. Give the role permission to create schemas in that database, because the migration and account creation both need it.
3. Copy `.env.example` to ignored `.env.local` and replace `DATABASE_URL` with that role's connection URL. URL-encode special characters in the password.
4. Install Liquibase Community, Java 17, and the PostgreSQL JDBC driver so the `liquibase` command can connect. Run:

```sh
.venv/bin/python scripts/liquibase.py validate
.venv/bin/python scripts/liquibase.py update-sql
.venv/bin/python scripts/liquibase.py update
.venv/bin/python scripts/liquibase.py status
```

The first migration creates the `paperlane` account schema and the shared `paperlane_auth` mapping/session tables. A new authenticated user gets a separate `paperlane_u_<UUID>` account schema. To change the schema later, append a new Liquibase changeset; do not edit an applied changeset whose checksum is already recorded.

Use pgAdmin or `psql` to inspect the database. `orders`, `trades`, `positions`, and `quotes` live in each account schema. `paperlane_auth.app_users` and `paperlane_auth.sessions` hold identity mappings and hashed session tokens. Keep the database URL only on the server.

Back up the database with PostgreSQL's `pg_dump -Fc`, store the backup outside the repository, and test a restore to a separate database. Pending paper orders are cancelled when the simulator restarts; saved fills and account records persist. This local database setup is not a production deployment design; see [PUBLIC_ARCHITECTURE.md](PUBLIC_ARCHITECTURE.md).
