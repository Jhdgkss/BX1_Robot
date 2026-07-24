@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Install Robot Brain Workshop Coding Model

echo ============================================================
echo  ROBOT BRAIN WORKSHOP CODING MODEL
echo ============================================================
echo.
where ollama >nul 2>nul
if errorlevel 1 (
    echo [ERROR] ollama.exe was not found on PATH.
    echo Install or start Ollama, then run this file again.
    pause
    exit /b 1
)

echo Installing qwen2.5-coder:7b...
echo This is separate from Leo's conversation model.
echo.
ollama pull qwen2.5-coder:7b
if errorlevel 1 (
    echo.
    echo The coding model installation failed.
    pause
    exit /b 1
)

echo.
echo Workshop coding model is ready.
pause
