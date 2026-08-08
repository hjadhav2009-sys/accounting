@echo off
title Business Automation Suite ONE PORT
cd /d "%~dp0"
echo PDF to Excel Core is now inside the main dashboard.
echo Opening main dashboard on http://localhost:8501
if not exist ".venv\Scripts\activate.bat" (
    echo Run install_and_run.bat first.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
streamlit run main_app.py --server.port 8501 --global.developmentMode false
pause
