@echo off
setlocal
cd /d "%~dp0"
title Robot Brain

REM The main PyQt application reads the last-selected robot profile directly.
REM Profile management now lives inside Robot Brain; no launcher GUI is shown.
call START_BX1_BRAIN.bat
exit /b %ERRORLEVEL%
