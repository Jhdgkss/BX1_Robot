@echo off
setlocal
cd /d "%~dp0"
title Install Dot.TTS in WSL2
echo ============================================================
echo  Robot Brain - Dot.TTS WSL2 Installer
echo ============================================================
echo Dot.TTS will run in Ubuntu inside Windows.
echo Robot Brain and all other programs remain Windows programs.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_dottts_wsl.ps1"
echo.
if errorlevel 1 (
  echo Setup did not complete. Read the guidance above.
) else (
  echo Setup completed successfully.
)
pause

