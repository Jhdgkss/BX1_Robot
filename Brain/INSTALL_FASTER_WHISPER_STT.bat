@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BX1 faster-whisper STT Installer

echo ============================================================
echo  BX1 Desktop Speech Recognition Installer
echo  Model: large-v3-turbo
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating the Brain virtual environment...
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :FAIL
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :FAIL
".venv\Scripts\python.exe" -m pip install "faster-whisper>=1.1.0,<2.0"
if errorlevel 1 goto :FAIL

echo.
echo Downloading and validating the large-v3-turbo model.
echo This is a one-time download and may take several minutes.
".venv\Scripts\python.exe" tools\prepare_faster_whisper.py
if errorlevel 1 goto :FAIL

echo.
echo Installation complete. Restart the BX1 Brain App.
pause
exit /b 0

:FAIL
echo.
echo Installation failed. Review the messages above.
pause
exit /b 1
