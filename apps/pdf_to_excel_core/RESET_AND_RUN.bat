@echo off
cd /d "%~dp0"
echo Removing old virtual environment...
rmdir /s /q .venv 2>nul
call install_and_run.bat
