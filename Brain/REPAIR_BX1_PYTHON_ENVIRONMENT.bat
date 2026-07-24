@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Robot Brain - Clean Python Environment Repair

echo ============================================================
echo  Robot Brain V2.8.1 - Clean Windows Environment Repair
echo ============================================================
echo Dot.TTS remains isolated inside WSL2 and is not reinstalled here.
echo.

if not exist "main_pyqt.py" (
    echo ERROR: Run this file from the Robot Brain project folder.
    pause
    exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
if exist ".venv" (
    echo Preserving the current environment as .venv_backup_!STAMP! ...
    move ".venv" ".venv_backup_!STAMP!" >nul
    if errorlevel 1 (
        echo ERROR: Close Robot Brain and retry.
        pause
        exit /b 1
    )
)

set "PYLAUNCH="
py -3.12 -c "import sys" >nul 2>nul && set "PYLAUNCH=py -3.12"
if not defined PYLAUNCH py -3.11 -c "import sys" >nul 2>nul && set "PYLAUNCH=py -3.11"
if not defined PYLAUNCH python -c "import sys" >nul 2>nul && set "PYLAUNCH=python"
if not defined PYLAUNCH (
    echo ERROR: 64-bit Python 3.11 or 3.12 was not found.
    pause
    exit /b 1
)

echo Creating a fresh Windows environment...
!PYLAUNCH! -m venv .venv
if errorlevel 1 goto :FAIL
set "PY=.venv\Scripts\python.exe"

"!PY!" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :FAIL
"!PY!" -m pip install --no-cache-dir -r requirements.txt
if errorlevel 1 goto :FAIL
"!PY!" -m pip check
if errorlevel 1 goto :FAIL
"!PY!" -c "import PyQt6, requests, edge_tts, pygame, faster_whisper; print('Robot Brain Windows environment: OK')"
if errorlevel 1 goto :FAIL

echo.
echo Repair complete. Run CHECK_DOT_TTS_WSL.bat to verify the WSL voice environment.
echo Then start Robot Brain with START_BX1_BRAIN.bat.
pause
exit /b 0

:FAIL
echo.
echo Repair failed. The previous environment is preserved as .venv_backup_!STAMP!.
pause
exit /b 1
