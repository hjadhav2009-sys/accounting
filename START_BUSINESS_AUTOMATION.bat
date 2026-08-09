@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0runtime\Start-BusinessAutomation.ps1"
if errorlevel 1 pause
