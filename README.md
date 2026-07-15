# Money Tracking Dashboard

Personal finance dashboard backed by your **"Money Tracking - AUD"** Google Sheet. React (Vite) frontend + Django API in one monorepo, deployable to Vercel.

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

The frontend never talks to Sheets or Groq directly. Secrets (`GOOGLE_CLIENT_SECRET`, `GROQ_API_KEY`, sheet ID) stay on the server. **Postgres is the read source of truth** for `Transactions`, `Receipt`, and `Receipt_Items`. Creates still append to Sheets first, then dual-write into Postgres. `Category` and `Sources` are also mirrored via **Management → Sync** (metadata API and the income-vs-expense chart still read from Sheets).

## Features

- **Dashboard** — net worth trend, income vs expense by month, category breakdown, recent transactions
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

Defaults match [`backend/.env.example`](backend/.env.example): user/password/db `finance` on `127.0.0.1:5432`.

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
# fill DJANGO_SECRET_KEY, GOOGLE_*, SHEET_ID, GROQ_API_KEY, …
# Postgres defaults in .env.example match docker compose
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
| `Income vs Expense by Month` | Monthly chart |
| `Category` / `Sources` | Dropdown metadata (mirrored to Postgres via Management Sync) |
| `Receipt` / `Receipt_Items` | Appends on create (dual-written to Postgres; detail reads from Postgres) |

## Deploy on Vercel

One project for the whole repo. Root [`vercel.json`](vercel.json) defines two **Services** (Vite frontend + Django backend) and rewrites `/api/*` to Django.

1. Import the GitHub repo in Vercel; set framework to **Services** if prompted.
2. Add env vars from [`backend/.env.example`](backend/.env.example), with production values:
   - `GOOGLE_REDIRECT_URI=https://<domain>/api/auth/google/callback`
   - `FRONTEND_URL=https://<domain>`
   - `CSRF_TRUSTED_ORIGINS=https://<domain>`
   - `DJANGO_DEBUG=false`
   - `ALLOWED_HOSTS=.vercel.app,<your-domain>`
   - `POSTGRES_*` pointing at a reachable Postgres instance (required; local Docker defaults are not for production)
3. Add the production redirect URI on the Google OAuth client.
4. Deploy.

## Local architecture notes

- Sessions use **signed cookies** (no DB rows required for auth).
- Postgres (Docker) stores **Transactions**, **Receipt**, **Receipt_Items**, **Category**, and **Sources** (`id` UUID + `version` on every table; `Receipt.id` equals sheet `Receipt ID`). Transaction `source` / category FKs point at Sources / Category by name / sub category. Dashboard/history and receipt detail read from Postgres; an empty DB needs **Management → Sync** once to load historical sheet data.
- Creates dual-write: Sheets append first, then Postgres mirror after success.
- CSRF: `GET /api/auth/me` sets the `csrftoken` cookie; the SPA sends `X-CSRFToken` on mutating requests.
- Append-only writes — no edit/delete of existing sheet rows.
