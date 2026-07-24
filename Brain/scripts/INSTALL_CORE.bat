@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
title Robot Brain Core Environment Setup

echo ============================================================
echo  Robot Brain - Windows Core Environment
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating the shared Python environment...
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 (
        echo Failed to create .venv. Check that Python 3 is installed.
        exit /b 1
    )
)

set "ROBOT_PYTHON=.venv\Scripts\python.exe"
"%ROBOT_PYTHON%" -c "import PyQt6, requests, pypdf, docx, faster_whisper, edge_tts, pygame" >nul 2>nul
if not errorlevel 1 (
    echo Core environment is ready.
    exit /b 0
)

echo Installing or updating Robot Brain requirements...
"%ROBOT_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%ROBOT_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install the Robot Brain requirements.
    exit /b 1
)

"%ROBOT_PYTHON%" -c "import PyQt6, requests, pypdf, docx, faster_whisper, edge_tts, pygame" >nul 2>nul
if errorlevel 1 (
    echo The environment was created, but one or more core modules still cannot be imported.
    exit /b 1
)

echo Core environment is ready.
exit /b 0
