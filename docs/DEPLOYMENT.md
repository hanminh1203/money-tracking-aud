# Deployment: Vercel + Supabase

Nothing here has been run against your accounts; follow it in order and check the Vercel and Supabase
docs if a screen has changed.

## 1. Supabase (database)

1. Create a project. Save the database password (URL-encode special characters when putting it in a URL).
2. Click **Connect** in the dashboard and copy two connection strings:
   - **Transaction pooler** (port 6543): runtime `DATABASE_URL` for the backend on Vercel.
   - **Session pooler** (port 5432 on the pooler host): `MIGRATION_DATABASE_URL` for GitHub Actions.
3. Append `?sslmode=require` to both.

Why two: Vercel functions are short-lived, so they use the transaction pooler (which does not support
prepared statements; the Django settings already disable them). Migrations run from GitHub-hosted runners,
which are IPv4-only, so they use the session pooler rather than the IPv6-only direct connection.

## 2. GitHub

Push this repo. Add repository secret `MIGRATION_DATABASE_URL` (Settings > Secrets and variables > Actions).

## 3. Vercel: one project

The monorepo deploys as a single project via [Vercel Services](https://vercel.com/docs/services)
(`frontend` = Vite, `backend` = Django). Root `vercel.json` routes `/api/*` to Django and everything else
to the SPA. The Vercel team must have Services enabled.

1. Import the repo. Leave **Root Directory** empty (repo root). Framework should follow `vercel.json`
   (Services).
2. Environment variables (Production):
   - `DJANGO_SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_DEBUG`: `false`
   - `DATABASE_URL`: the transaction pooler URL
   - `ALLOWED_HOSTS`: the app hostname(s), e.g. `finance-dashboard.vercel.app` (and any custom domain)
   - `CSRF_TRUSTED_ORIGINS`: `https://<app-host>` (and custom domain if any)
   - `FRONTEND_URL`: `https://<app-host>`
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`: `https://<app-host>/api/auth/google/callback`
   - `GROQ_API_KEY` (and optional `GROQ_MODEL` / `GROQ_VISION_MODEL` if not using defaults)
3. Do **not** set a separate frontend API base URL. The SPA calls relative `/api/...` paths; Vercel
   rewrites them to Django on the same host.
4. Add the production redirect URI on the Google OAuth client.
5. Deploy, then open `https://<app-host>/api/health`. Expect `{"status": "ok"}`.
6. Open the site, sign in with Google, set the sheet ID under Management, and run Sync if the DB is empty.

## 4. Migrations

`.github/workflows/migrate.yml` runs `python manage.py migrate` against `MIGRATION_DATABASE_URL` on every push
to `main` that touches `backend/`. Run it once manually (Actions > Migrate database > Run workflow)
before the first visit, or run locally:

```bash
cd backend
DATABASE_URL="<session pooler url>" DJANGO_DEBUG=false DJANGO_SECRET_KEY=any-32-char-string-for-migrate-only python manage.py migrate
```

Vercel and the migrate workflow start on the same push. For a schema change that the new code needs, a
request can briefly arrive before the migration finishes. Make migrations backwards compatible
(add nullable columns first, remove columns in a later release).

## 5. Automatic deploys

The Vercel project deploys on every push to `main` (production) and on pull requests (preview). Each
preview includes both Vite and Django on the same host.

## Gotchas

- **Services access.** Without Services on the team, this layout will not build; enable it or check
  Vercel's docs for your plan.
- **Cold starts.** The first request after idle is slower.
- **Rotating `DJANGO_SECRET_KEY`** invalidates all signed session cookies (everyone must sign in again).
- **Custom domain.** Point it at this single project and add the hostname to `ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS`.
- **Sheet ID** is per-user in Management, not a Vercel env var.
