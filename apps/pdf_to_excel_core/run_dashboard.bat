@echo off
setlocal
cd /d "%~dp0"
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set LOGFILE=%~dp0dashboard_error.log

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run install_and_run.bat first.
    pause
    exit /b 1
)

start "" http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo Dashboard crashed. Opening log...
    type "%LOGFILE%"
    pause
)
