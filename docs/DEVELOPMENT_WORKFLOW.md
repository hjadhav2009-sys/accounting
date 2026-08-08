# Development Workflow

Tested targets: Python 3.14.3, Node 25.8.1, npm 11.11.0, Next.js 16.3.0. Python uses the project `.venv`; npm uses `v2/frontend/package-lock.json`. Legacy requirements remain in `requirements.txt`; V2 and combined development inputs are in `requirements-v2.txt` and `requirements-dev.txt`.

- Legacy Streamlit: `START_CLEAN_DASHBOARD.bat`, port 8501.
- V2 backend: `.\.venv\Scripts\python.exe -m uvicorn v2.backend.app.main:app --host 127.0.0.1 --port 8000`.
- V2 frontend: from `v2/frontend`, `npm.cmd run dev`, port 3000.

V2 startup never kills or replaces the legacy server. Environment configuration is optional in Phase 1; `.env.example` contains names only. Do not blindly upgrade dependencies: update reviewed packages, regenerate locks, audit, build, and rerun tests.
# Phase 2 simultaneous startup

- Legacy: `START_CLEAN_DASHBOARD.bat` at `http://localhost:8501`
- Backend: `python -m uvicorn v2.backend.app.main:app --port 8000`
- Frontend: `cd v2/frontend`, then `npm run dev` at `http://localhost:3000`
- PostgreSQL: `docker compose --env-file .env -f docker-compose.postgres.yml up -d`

The V2 commands do not stop or bind the legacy port. PostgreSQL credentials stay
in ignored `.env`; copy variable names from `.env.example` and choose separate
`business_automation_dev` and `business_automation_test` databases.

Phase 2B also certifies native PostgreSQL 18.4 on Windows. When using the native
service, libpq reads the password from the user-local `pgpass.conf`; repository
URLs therefore do not need embedded passwords. Docker is optional, not required.
