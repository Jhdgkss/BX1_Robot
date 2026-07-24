@echo off
setlocal
cd /d "%~dp0"
title Check Dot.TTS WSL2
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check_dottts_wsl.ps1"
pause

