@echo off
title Business Automation Suite - CLEAN START
cd /d "%~dp0"

echo ======================================================
echo Business Automation Suite - CLEAN START
echo ======================================================
echo This will close anything currently using localhost:8501
echo and then start this folder's dashboard.
echo ======================================================
echo.

echo Closing old localhost:8501 process if it exists...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }"

echo Closing old localhost:8510 process if it exists...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8510 -ErrorAction SilentlyContinue | ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }"

echo Cleaning Python cache...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    set PY=python
)

%PY% --version
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH.
    echo Install Python 3.10+ and tick Add Python to PATH.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PY% -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Installing / repairing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo Clearing Streamlit cache...
streamlit cache clear

echo.
echo Starting dashboard from THIS folder:
echo %cd%
echo.
echo Open: http://localhost:8501
echo.
streamlit run main_app.py --server.port 8501 --server.address localhost --global.developmentMode false
pause
