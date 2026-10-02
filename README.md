# Money Tracking Dashboard

Personal finance dashboard backed by your **"Money Tracking - AUD"** Google Sheet. React (Vite) frontend + Django API in one monorepo, deployable to Vercel.

**For AI coding agents:** read [AGENTS.md](AGENTS.md) first.

```
Browser (React SPA)
   │  session cookie
   ▼
Django API  ──  Google OAuth (auth code + refresh)
   │            Google Sheets API v4  (writes + Category/Sources metadata)
   │            Groq (assistant + receipt OCR)
   │            Postgres (local Docker; read + dual-write mirror)
   ▼
Named Sheets Tables + Postgres (Transactions / Receipt / Receipt_Items / Category / Sources)
```

The frontend never talks to Sheets or Groq directly. Secrets (`GOOGLE_CLIENT_SECRET`, `GROQ_API_KEY`, sheet ID) stay on the server. **Postgres is the read source of truth** for `Transactions`, `Receipt`, and `Receipt_Items`. Creates still append to Sheets first, then dual-write into Postgres. `Category` and `Sources` are also mirrored via **Management → Sync**.

## Features

- **Dashboard** — net worth and current-month totals, three-month subcategory breakdowns, current-month transactions
- **Sources** — balances and per-source history
- **Add Transaction** / **Transfer** / **Receipt** — append rows to Sheets tables
- **Assistant** — natural-language logging via Groq
- **Receipt scan** — vision OCR fills the receipt form

## Setup

### 0. Postgres (local Docker)

Local development needs Docker Desktop and a Postgres container:

```bash
docker compose up -d
```

Defaults match [`backend/.env.example`](backend/.env.example): `DATABASE_URL=postgres://finance:finance@127.0.0.1:5432/finance`.

Or use [`start.bat`](start.bat), which starts the container, waits until it is healthy, runs `migrate`, then launches Django and Vite.

### 1. Google Cloud OAuth client

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Google Sheets API**.
2. **APIs & Services → Credentials → Create OAuth client ID** → type **Web application**.
3. Authorized redirect URIs:
   - Local: `http://localhost:5173/api/auth/google/callback`
   - Production: `https://<your-vercel-domain>/api/auth/google/callback`
4. Copy **Client ID** and **Client secret**.

### 2. Backend

```bash
cd backend
cp .env.example .env
# fill DJANGO_SECRET_KEY, GOOGLE_*, GROQ_API_KEY, …
# (each user sets their Google Spreadsheet ID in the Management page)
# Postgres defaults in .env.example match docker compose (`DATABASE_URL`)
py -3 -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

API listens on `http://127.0.0.1:8000`. Routes live under `/api/…`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` → Django. Open the printed localhost URL and **Sign in with Google**.

### Sheet tables

The app expects Google Sheets **Insert → Table** names (configurable via env):

| Table | Role |
|-------|------|
| `Transactions` | Appends on create (dual-written to Postgres; list reads from Postgres) |
| `Computed_Transactions` | Legacy computed view (no longer used by the API) |
| `Category` / `Sources` | Dropdown metadata (mirrored to Postgres via Management Sync) |
| `Receipt` / `Receipt_Items` | Appends on create (dual-written to Postgres; detail reads from Postgres) |
| `Product` / `Product_Items` | Product catalog and purchase links. `Product_Items` columns: `Product Item ID`, `Product ID`, `Price`, `Transaction ID`, `Receipt Item ID`, `End Date` (optional DATE; when the purchase is expected to run out). Existing spreadsheets must add the `End Date` column — the app cannot create it on a user-managed sheet. |

## Deploy on Vercel

One project for the whole repo (Vite frontend + Django backend) with Supabase Postgres.
See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full runbook (pooler URLs, env vars, migrations, OAuth).

## Local architecture notes

- Sessions use **signed cookies** (no DB rows required for auth).
- Postgres (Docker) stores **Transactions**, **Receipt**, **Receipt_Items**, **Category**, **Sources**, **Giftcard**, **Product**, **Product_Items**, **Payment**, and **GiftcardPayment** (`id` UUID + `version` on every table; `Receipt.id` equals sheet `Receipt ID`, `Transaction.id` equals sheet `Transaction ID`). Receipt rows link to a transaction via `Transaction ID`. Transaction category FKs point at Category by sub category; funding is via Payment / GiftcardPayment. Dashboard **net worth** is signed source Payments plus remaining giftcard balances (buying a giftcard is cash→credit, not an expense; using it is the expense). Dashboard/history and receipt detail read from Postgres; an empty DB needs **Management → Sync** once to load historical sheet data.
- Writes dual-write: Sheets first, then Postgres mirror; dual-write failure after a successful sheet write must not return success.
- CSRF: `GET /api/auth/me` sets the `csrftoken` cookie; the SPA sends `X-CSRFToken` on mutating requests.
- Some flows support update/delete on sheet rows with the same dual-write contract; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
