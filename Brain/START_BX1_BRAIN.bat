@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Robot Brain Launcher

REM ============================================================
REM  Robot Brain - Single Launcher
REM ============================================================
REM  Normal single robot start:
REM      START_BX1_BRAIN.bat
REM
REM  Multi-robot shorthand:
REM      START_BX1_BRAIN.bat bx1
REM      START_BX1_BRAIN.bat bx2
REM
REM  Advanced/manual:
REM      START_BX1_BRAIN.bat --profile bx3 --robot-name BX3 --api-port 8767
REM ============================================================

set "PROFILE_ARGS=%*"

REM With no arguments, main_pyqt.py reads config/robot_profiles.json and opens
REM the last-selected robot directly.

REM Friendly shorthand profiles. These replace the old separate PROFILE_BX1/PROFILE_BX2 bat files.
if /I "%~1"=="bx1" (
    set "PROFILE_ARGS=--profile bx1 --robot-name BX1 --api-port 8765"
)
if /I "%~1"=="bx2" (
    set "PROFILE_ARGS=--profile bx2 --robot-name BX2 --api-port 8766"
)

echo ============================================================
echo  Robot Brain - Single Launcher
echo ============================================================
echo Folder : %CD%
echo Args   : %PROFILE_ARGS%
echo.

REM --- Start Ollama if it is not already listening.
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 ^| Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo Ollama is not listening on 127.0.0.1:11434.
    where ollama >nul 2>nul
    if errorlevel 1 (
        echo WARNING: ollama.exe was not found on PATH.
        echo Start Ollama manually, then use Diagnostics - Test Ollama in the app.
    ) else (
        echo Starting Ollama in a separate window...
        start "BX1 Ollama Server" cmd /k "ollama serve"
        timeout /t 4 /nobreak >nul
    )
) else (
    echo Ollama: already running.
)

REM --- Prepare the shared Windows environment without launching another app.
call scripts\INSTALL_CORE.bat
if errorlevel 1 (
    echo Failed to prepare the Robot Brain environment. See the messages above.
    pause
    exit /b 1
)

echo.
echo Starting Robot Brain...
echo.
set "BRAIN_PYTHON=.venv\Scripts\python.exe"
"%BRAIN_PYTHON%" -c "import sys; from zoneinfo import ZoneInfo; ZoneInfo('Europe/London'); print('Verified Brain Python:', sys.executable)"
if errorlevel 1 (
    echo Reminder Clock timezone dependency verification failed.
    echo Installing dependencies into the same interpreter used to launch Brain...
    "%BRAIN_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo WARNING: Dependency repair failed. Brain will still start with Reminder Clock unavailable.
    )
)
"%BRAIN_PYTHON%" main_pyqt.py %PROFILE_ARGS%

echo.
echo Robot Brain has closed.
pause
