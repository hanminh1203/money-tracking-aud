# Conventions

## Git

- Branch from `main`, small PRs, imperative commit messages ("Add receipt OCR retry").
- CI must pass. Merging to `main` deploys the Vercel project and runs migrations when `backend/` changes (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Python (backend)

- Django 6, function views returning JSON (no DRF in this repo).
- Type hints where they clarify; follow existing module layout under `finance/`.
- Migrations are committed; never edit an applied migration — add a new one.
- Errors go through established patterns (`JsonExceptionMiddleware`, consistent JSON error bodies in views).
- Tests live in `finance/tests.py`; run with `python manage.py test finance`.

## JavaScript (frontend)

- React 18, JSX in `frontend/src/`. No TypeScript in this repo today.
- Page components in `pages/`, shared UI in `components/`.
- API access only via `lib/api.js` (relative `/api`, CSRF on mutations).
- Pure helpers in `lib/transform.js` with tests in `lib/transform.test.js` (`npm test`).

## Naming

- API JSON fields use snake_case; frontend mirrors API shapes in plain objects.
- Domain words: *transaction*, *source*, *receipt*, *giftcard*, *payment*, *category*, *subcategory*. Keep UI labels aligned with the sheet column semantics where users see both.

## UI copy

Sentence case. Buttons describe the action ("Add transaction", "Run sync"). Empty states say what to do next.
Errors explain what failed and how to recover (e.g. set sheet ID, run sync, check OAuth).

## Frontend display

- **Quiet Ledger** — light-first dashboard; see [design-system/finance-dashboard/MASTER.md](../design-system/finance-dashboard/MASTER.md).
- Dates shown to the user: `dd/MM/yyyy` via `formatDateShort` in `lib/transform.js`. Form `type="date"` and API values stay `YYYY-MM-DD`.
- Currency: AUD; use existing formatting helpers and tabular numbers for tables.

## Environment variables

Secrets and table-name defaults are documented in [`backend/.env.example`](../backend/.env.example). When adding or renaming vars, update that file and [`setup-env.ps1`](../setup-env.ps1) (see `.cursor/rules/env-setup-script.mdc`).

| Var | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Session and CSRF signing (required in production) |
| `DJANGO_DEBUG` | `true` locally, `false` in production |
| `DATABASE_URL` | Postgres (local Docker or Supabase transaction pooler) |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` / `FRONTEND_URL` | Host and CSRF/OAuth alignment |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | OAuth |
| `GROQ_API_KEY` (+ optional model vars) | Assistant and receipt OCR |
| `*_TABLE` | Google Sheets table names |

Per-user **spreadsheet ID** is stored in the database after sign-in (Management), not in Vercel env.

## Sheet schema changes

Document migrations users must apply to their spreadsheets in `docs/` (example: [sheet-payment-migration.md](sheet-payment-migration.md)). The app cannot add columns to a user's sheet automatically.

## AI agents

Coding agents should start at [AGENTS.md](../AGENTS.md) and the `.cursor/rules/` files.
