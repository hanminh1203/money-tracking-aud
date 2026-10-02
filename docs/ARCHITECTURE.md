# Architecture

```
Browser (React SPA)
   │  signed session cookie + CSRF
   ▼
Vercel project (Services)  —  or locally Vite :5173 proxying /api
   ├─ /api/*  →  backend service (Django, serverless)
   │                 │
   │                 ├── Google OAuth + Sheets API v4
   │                 ├── Groq (assistant + receipt OCR)
   │                 ▼
   │           Supabase Postgres (transaction pooler)
   └─ /*      →  frontend service (Vite static + SPA)
```

## Why this shape

- **One Vercel project, one repo.** [Services](https://vercel.com/docs/services) builds `frontend/` (Vite) and
  `backend/` (Django). Root [`vercel.json`](../vercel.json) routes `/api/*` to Django and everything else to the SPA.
- **Same-origin API.** The browser only talks to the app domain. Locally, [`frontend/vite.config.js`](../frontend/vite.config.js)
  proxies `/api` to `http://127.0.0.1:8000`. The session cookie stays first-party; no CORS for normal SPA usage.
- **Sheets + Postgres.** The user's spreadsheet remains the durable ledger they edit in Google Sheets. The app
  writes Sheets first for creates/updates/deletes that touch sheet rows, then mirrors into Postgres via `db_writer`.
  **Reads** for dashboard, transaction lists, and receipt detail come from **Postgres** (`db_reader`). An empty
  Postgres after first login needs **Management → Sync** (`db_sync`) to import historical sheet data.
- **Category / Sources** metadata is mirrored to Postgres on sync; dropdowns can be served from Postgres after sync.

## Backend

- `config/` — settings, urls, wsgi.
- `finance/` — single Django app:
  - `oauth.py` — Google OAuth, session storage for tokens and user identity.
  - `api_views.py` — JSON HTTP handlers (auth, dashboard, transactions, receipts, giftcards, products, assistant, management).
  - `sheets_client.py` — Google Sheets API v4 (table names from env).
  - `db_reader.py` / `db_writer.py` / `db_sync.py` — Postgres read, dual-write, full sheet→Postgres sync.
  - `funding.py` — Payment / GiftcardPayment must sum to transaction `abs(Change)`.
  - `groq_client.py` — natural-language assistant and receipt OCR.
  - `models.py` — UUID `id` + `version` on finance tables; `User` with per-user `sheet_id`.

Auth flow: Google login → callback → session cookie → `@require_auth` on protected views. SPA loads `GET /api/auth/me`
for user info and CSRF token setup.

## Frontend

- Vite SPA with react-router: Dashboard, Sources, Transactions, Giftcards, Products, Chat (assistant), Health, Management.
- Unauthenticated users see `SignInScreen` (Google sign-in).
- `lib/api.js` — fetch wrapper, CSRF header, JSON errors.
- `hooks/useAuth.js`, `hooks/useFinanceData.js` — session and data loading.
- Design: Quiet Ledger (see [`design-system/finance-dashboard/MASTER.md`](../design-system/finance-dashboard/MASTER.md)).

## Dual-write and errors

For operations that change sheet data:

1. Apply change to Google Sheets (via `SheetsClient`).
2. Mirror to Postgres in the same request path (`db_writer`).

If step 2 fails after step 1 succeeds, the API must surface an error (dual-write failure), not a 200. Tests in
`finance/tests.py` cover this contract for creates and deletes/updates where implemented.

Some entities (e.g. products) may be Postgres-first or sheet-backed depending on the endpoint; follow existing
patterns in `api_views.py` and `sheets_client.py` when extending.

## Database access on Vercel

Use the Supabase **transaction pooler** (port 6543) for runtime `DATABASE_URL`: short-lived serverless functions,
`conn_max_age=0`, server-side cursors disabled, prepared statements disabled in Django DB options.

Use the **session pooler** (port 5432 on the pooler host) for `MIGRATION_DATABASE_URL` in GitHub Actions — see
[DEPLOYMENT.md](DEPLOYMENT.md).

## Local development

- `docker compose up -d` — Postgres 16 on port 5432.
- [`start.bat`](../start.bat) — starts Postgres, migrates, runs Django + Vite.
- [`setup-env.ps1`](../setup-env.ps1) — interactive `.env` from `.env.example`.

Spreadsheet ID is **not** in deploy env; each user sets it under Management after sign-in.
