@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Backend venv not found. Creating it and installing dependencies...
  py -3 -m venv backend\.venv
  if errorlevel 1 (
    echo Failed to create venv. Is Python installed and on PATH as "py"?
    pause
    exit /b 1
  )
  call backend\.venv\Scripts\pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo Failed to install backend requirements.
    pause
    exit /b 1
  )
)

if not exist "backend\.env" (
  echo Missing backend\.env — run setup-env.bat first to enter secrets.
  pause
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is required for local Postgres. Install Docker Desktop and retry.
  pause
  exit /b 1
)

echo Starting Postgres container...
docker compose up -d
if errorlevel 1 (
  echo Failed to start Postgres. Is Docker Desktop running?
  pause
  exit /b 1
)

echo Waiting for Postgres to be ready...
:wait_pg
docker compose exec -T db pg_isready -U finance -d finance >nul 2>nul
if errorlevel 1 (
  timeout /t 2 /nobreak >nul
  goto wait_pg
)

echo Running database migrations...
pushd backend
call .venv\Scripts\python manage.py migrate
if errorlevel 1 (
  echo Migration failed.
  popd
  pause
  exit /b 1
)
popd

if not exist "frontend\node_modules\" (
  echo Installing frontend dependencies...
  pushd frontend
  call npm install
  if errorlevel 1 (
    echo Failed to install frontend dependencies.
    popd
    pause
    exit /b 1
  )
  popd
)

echo Starting Django backend on http://127.0.0.1:8000 ...
start "finance-dashboard-backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python manage.py runserver"

echo Starting Vite frontend (proxies /api to backend)...
start "finance-dashboard-frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Both servers are starting in separate windows.
echo Open the Vite URL shown in the frontend window (usually http://localhost:5173).
echo Close those windows to stop the servers. Postgres keeps running via Docker.
endlocal
