@echo off
setlocal
cd /d "%~dp0"

fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\dev-run.ps1" -LaunchGame16By9
set "DEV_RUN_EXIT=%errorlevel%"

if not "%DEV_RUN_EXIT%"=="0" (
    echo.
    echo dev-run-16x9 failed with exit code %DEV_RUN_EXIT%.
    pause
)

exit /b %DEV_RUN_EXIT%
