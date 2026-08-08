@echo off
setlocal
cd /d "%~dp0"
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
set LOGFILE=%~dp0dashboard_error.log

echo ==================================================
echo Installing PDF to Excel Dashboard Core
echo Folder: %cd%
echo ==================================================

echo Checking Python...
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Python not found. Install Python 3.10+ from python.org and tick "Add Python to PATH".
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=python
    )
) else (
    set PYTHON_CMD=py
)

echo Using Python command: %PYTHON_CMD%

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv >> "%LOGFILE%" 2>&1
    if errorlevel 1 goto ERROR
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
if errorlevel 1 goto ERROR

echo Installing required packages. This can take a few minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOGFILE%" 2>&1
if errorlevel 1 goto ERROR

echo Starting dashboard...
start "" http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false
pause
exit /b 0

:ERROR
echo.
echo Something failed. Opening log...
type "%LOGFILE%"
echo.
pause
exit /b 1
