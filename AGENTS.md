# AGENTS.md

Guidance for AI coding agents (Cursor, Claude Code, Codex, etc.). Read this first, then the docs it links.

## What this is

Personal **Money Tracking (AUD)** dashboard backed by the user's **Google Sheet** ("Money Tracking - AUD" tables).
Each user signs in with Google, configures their spreadsheet ID in Management, and sees only their own data.

Monorepo:

- `backend/` Django 6 JSON API under `/api/*`, Google OAuth, signed session cookies, Google Sheets + Groq on the server only.
- `frontend/` Vite + React 18 + JavaScript + Tailwind 3 + react-router-dom.
- `docs/` architecture, conventions, deployment, sheet migration notes.

The browser never calls Sheets or Groq directly.

## Commands

```bash
# backend/  (venv active; Postgres via docker compose up -d)
python manage.py test finance
python manage.py makemigrations --check --dry-run

# frontend/
npm test && npm run build
```

Run the commands for the side you changed before finishing. CI runs the same checks.

## Rules that must not be broken

1. **Per-user isolation.** Every query and Sheets call is scoped to the signed-in user and their `sheet_id`.
   Never return another user's rows. New endpoints need a cross-user test where applicable.
2. **Postgres is the read source of truth** for Transactions, Receipt, Receipt_Items, and dashboard aggregates.
   **Sheets is written first** (append or update/delete as implemented), then **Postgres is dual-written** via `db_writer`.
   If Postgres fails after a successful sheet write, the API must **not** report success.
3. **Funding integrity.** Payment and GiftcardPayment rows for a transaction must sum to `abs(Change)` (`funding.py`).
   Do not bypass validation when adding or changing transaction funding.
4. **Secrets stay on the server.** `GOOGLE_CLIENT_SECRET`, `GROQ_API_KEY`, and spreadsheet access tokens live in backend env/session only.
   No `VITE_*` secrets. Do not commit `.env` or real credentials.
5. **Same-origin API.** The SPA uses relative `/api/...` URLs. Locally Vite proxies to Django; on Vercel, Services rewrites `/api/*` to the backend.
   Do not hardcode backend URLs in client code.
6. **Auth and CSRF.** Google OAuth stores tokens in **signed session cookies**. `GET /api/auth/me` sets the CSRF cookie;
   mutating requests from the SPA must send `X-CSRFToken` (`frontend/src/lib/api.js`). Do not disable CSRF for convenience.
7. **Env setup sync.** When you add, rename, or remove a secret or developer env var, update `backend/.env.example`
   (and `frontend/.env.example` if needed) **and** [`setup-env.ps1`](setup-env.ps1) per `.cursor/rules/env-setup-script.mdc`.
8. **User-managed sheet schema.** Table and column names are configurable via env; users own the spreadsheet.
   New columns the app needs must be documented (e.g. [`docs/sheet-payment-migration.md`](docs/sheet-payment-migration.md)).
   The app cannot create columns on a user's sheet for them.
9. **Money on the backend** uses appropriate decimal/numeric types; avoid float for persisted amounts.
   Frontend formatting uses helpers in `frontend/src/lib/transform.js`.

## Where things live

| Task | Backend | Frontend |
| --- | --- | --- |
| New or changed API route | `finance/api_views.py`, `finance/urls.py` | `src/lib/api.js`, page or component that calls it |
| Sheet read/write | `sheets_client.py` | — |
| Postgres read / sync / dual-write | `db_reader.py`, `db_sync.py`, `db_writer.py` | — |
| Models and migrations | `finance/models.py`, `finance/migrations/` | — |
| Google OAuth / session | `finance/oauth.py` | `hooks/useAuth.js`, `SignInScreen` |
| Groq assistant / receipt OCR | `groq_client.py`, `comment_parse.py` | `ChatBot`, receipt forms |
| Payment validation | `funding.py` | transaction/receipt forms |
| Dashboard / lists | `db_reader.py`, `api_views.py` | `pages/Dashboard.jsx`, `Transactions.jsx`, … |
| Management (sync, settings) | `api_views.py` (management/*) | `pages/Management.jsx` |

## UI conventions

- **Quiet Ledger** design: light-first, dense dashboard. See [`design-system/finance-dashboard/MASTER.md`](design-system/finance-dashboard/MASTER.md)
  for colours (primary `#1E40AF`, income/expense tokens), IBM Plex Sans / Mono, and spacing. Avoid playful gradients or emoji-as-icons.
- Display user-facing dates with `formatDateShort` (`dd/MM/yyyy`). Keep API values and `<input type="date">` as ISO `YYYY-MM-DD`.
- Copy: sentence case, calm and precise (personal ledger, not bank marketing). Errors state what happened and what to do.
- Tabular money: use monospace/tabular styling where the design system specifies.

## Definition of done

- Tests added or updated (`python manage.py test finance`; frontend `npm test` for transform/logic changes).
- `npm run build` passes when frontend changed; `makemigrations --check` when models changed.
- Docs updated if behaviour, setup, or sheet schema changed.
- New secrets reflected in `.env.example` and `setup-env.ps1`.

See also: [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/CONVENTIONS.md](docs/CONVENTIONS.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md),
[docs/sheet-payment-migration.md](docs/sheet-payment-migration.md).
