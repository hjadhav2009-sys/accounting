@echo off
cd /d "%~dp0"
if exist dashboard_error.log (
    type dashboard_error.log
) else (
    echo No dashboard_error.log found yet.
)
pause
