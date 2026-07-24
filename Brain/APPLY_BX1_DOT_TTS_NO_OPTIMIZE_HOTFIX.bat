@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BX1 Dot.TTS Compatibility Hotfix

echo ============================================================
echo  BX1 Dot.TTS - NVCC Compatibility Hotfix
echo ============================================================
echo.
echo This changes the normal Dot.TTS launcher to standard mode.
echo It avoids torch.compile and therefore does not require nvcc.
echo.

set "TARGET=%~1"
if not defined TARGET set /p "TARGET=Enter Robot Brain project folder: "
set "TARGET=%TARGET:"=%"

if not exist "%TARGET%\main_pyqt.py" (
  echo.
  echo ERROR: main_pyqt.py was not found in:
  echo %TARGET%
  pause
  exit /b 1
)
if not exist "%TARGET%\scripts" (
  echo.
  echo ERROR: scripts folder was not found in:
  echo %TARGET%
  pause
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "BACKUP=%TARGET%\backups\dottts_noopt_%STAMP%"
mkdir "%BACKUP%" >nul 2>&1

if exist "%TARGET%\scripts\start_dottts_wsl.ps1" (
  copy /Y "%TARGET%\scripts\start_dottts_wsl.ps1" "%BACKUP%\start_dottts_wsl.ps1" >nul
)

copy /Y "%~dp0payload\scripts\start_dottts_wsl.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1" >nul
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "$null=[System.Management.Automation.Language.Parser]::ParseFile('%TARGET:\=\\%\scripts\start_dottts_wsl.ps1',[ref]$null,[ref]$null); Write-Host 'PowerShell syntax check: OK'"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  Hotfix installed successfully
echo ============================================================
echo Backup: %BACKUP%
echo.
echo Stop the current voice service, then start Dot.TTS MF again.
echo The service window should show: standard compatibility mode
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: Hotfix installation failed. Restoring backup...
if exist "%BACKUP%\start_dottts_wsl.ps1" copy /Y "%BACKUP%\start_dottts_wsl.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1" >nul
echo Restore complete.
pause
exit /b 1
