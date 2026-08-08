@echo off
title Repair Business Automation Suite Database
cd /d "%~dp0"

echo Running database repair and cleanup...
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    set PY=python
)

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

%PY% -c "from shared import database as db; db.cleanup_database(); print('Database repaired:', db.DB_PATH); print(db.database_summary())"
pause
