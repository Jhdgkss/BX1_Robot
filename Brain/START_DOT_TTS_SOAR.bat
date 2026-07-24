@echo off
setlocal
cd /d "%~dp0"
title Robot Brain - Dot.TTS SOAR (WSL2)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_dottts_wsl.ps1" -Model soar
if errorlevel 1 pause

