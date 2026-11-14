# Auth0 setup for local development

Paperlane uses OpenID Connect Authorization Code with PKCE. Flask handles the callback and stores an opaque, revocable session in PostgreSQL. The React app never receives the Auth0 client secret or access token.

1. Create a **Regular Web Application** in your Auth0 tenant. Enable the login connections you want to use.
2. Set **Allowed Callback URLs** to `http://127.0.0.1:8000/auth/callback` and **Allowed Logout URLs** to `http://127.0.0.1:8000/`.
3. Copy `.env.example` to `.env.local`. Set `OIDC_ISSUER` to your tenant's HTTPS issuer URL, and set `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` from the application settings. Generate `PAPERLANE_SESSION_SECRET` with at least 32 random characters. Keep `.env.local` private.
4. Run the Liquibase migration described in [DATABASE_SETUP.md](DATABASE_SETUP.md), then start Flask with `.venv/bin/python backend/server.py`. Visit `http://127.0.0.1:8000/` and sign in.

Environment variables override `.env.local`. For a hosted deployment, set `PAPERLANE_BASE_URL` to the final HTTPS origin and configure matching callback and logout URLs in Auth0. Never put a client secret or database URL in Vite variables or browser code.

Each validated identity receives a separate PostgreSQL account schema and starts with virtual INR 10,00,000. The browser receives an HttpOnly app cookie; every protected API request resolves it against the PostgreSQL session table. Protected writes also require a CSRF token. Sign out revokes the app session but does not sign the user out of Auth0 or Google.

If migrating an older paper ledger, assign it only to an explicitly chosen identity. Set `PAPERLANE_LEGACY_OWNER_SUB` to that identity's exact OIDC `sub` before their first sign-in, or use `scripts/assign_legacy_account.py` after they sign in to a fresh empty account. The script refuses an account that already has activity.

This local sign-in setup is separate from launching a public service. See [PUBLIC_ARCHITECTURE.md](PUBLIC_ARCHITECTURE.md) for remaining deployment and security work.
