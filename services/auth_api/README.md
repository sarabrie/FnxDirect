# Auth API (standalone)

A separate FastAPI + PostgreSQL authentication service. **The Streamlit app does not use it** —
the app has its own SQLite-based auth in `fnx_direct/auth/`. Kept here as an alternative backend.

Required environment: `DATABASE_URL`, `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `CSRF_SECRET`
(optional: `COOKIE_SECURE`, `DB_POOL_MIN`, `DB_POOL_MAX`). Schema: `auth/migrations/001_initial.sql`.

```sh
docker build -t fnx-auth-api services/auth_api
docker run -p 8000:8000 --env-file .env fnx-auth-api
```
