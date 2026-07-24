@echo off
setlocal
cd /d "%~dp0"
title Robot Brain - Dot.TTS MF (WSL2)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_dottts_wsl.ps1" -Model mf
if errorlevel 1 pause

