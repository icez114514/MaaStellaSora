@echo off
setlocal
cd /d "%~dp0"

fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b
)

set "PYTHON_EXE=%~dp0install\python\python.exe"
set "RESTORE_SCRIPT=%~dp0agent\utils\window_aspect.py"
set "GAME_EXE=C:\StargazerGames\StellaSora_TW\StellaSora.exe"

tasklist /FI "IMAGENAME eq StellaSora.exe" /NH | findstr /I /C:"StellaSora.exe" >nul
if not errorlevel 1 (
    if not exist "%PYTHON_EXE%" (
        echo Embedded Python was not found: %PYTHON_EXE%
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" "%RESTORE_SCRIPT%" --restore-native
    if errorlevel 1 (
        echo Failed to restore the running game window.
        pause
        exit /b 1
    )
    exit /b 0
)

if not exist "%GAME_EXE%" (
    echo StellaSora was not found: %GAME_EXE%
    pause
    exit /b 1
)

start "" "%GAME_EXE%" -screen-width 5120 -screen-height 2160 -screen-fullscreen 1
exit /b 0
