@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BX1 Dot.TTS Force Standard Mode V3 Fixed

echo ============================================================
echo  BX1 Dot.TTS - Force Standard Mode V3 Fixed
echo ============================================================
echo.
echo This update disables torch.compile in both:
echo   1. the Windows/WSL Dot.TTS launcher
echo   2. the Dot.TTS service default
echo.
echo It also corrects the PowerShell validation error in V2.
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
if not exist "%TARGET%\bx1_services\dottts_service\app.py" (
  echo.
  echo ERROR: Dot.TTS service app.py was not found.
  pause
  exit /b 1
)
if not exist "%TARGET%\scripts\start_dottts_wsl.ps1" (
  echo.
  echo ERROR: scripts\start_dottts_wsl.ps1 was not found.
  pause
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "BACKUP=%TARGET%\backups\dottts_force_standard_v3_%STAMP%"
mkdir "%BACKUP%\bx1_services\dottts_service" >nul 2>&1
mkdir "%BACKUP%\scripts" >nul 2>&1

copy /Y "%TARGET%\bx1_services\dottts_service\app.py" "%BACKUP%\bx1_services\dottts_service\app.py" >nul
if errorlevel 1 goto :fail_no_restore
copy /Y "%TARGET%\scripts\start_dottts_wsl.ps1" "%BACKUP%\scripts\start_dottts_wsl.ps1" >nul
if errorlevel 1 goto :fail_no_restore

copy /Y "%~dp0payload\bx1_services\dottts_service\app.py" "%TARGET%\bx1_services\dottts_service\app.py" >nul
if errorlevel 1 goto :fail
copy /Y "%~dp0payload\scripts\start_dottts_wsl.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1" >nul
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0helpers\validate_powershell.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1"
if errorlevel 1 goto :fail

if exist "%TARGET%\.venv\Scripts\python.exe" (
  "%TARGET%\.venv\Scripts\python.exe" -m py_compile "%TARGET%\bx1_services\dottts_service\app.py"
) else (
  py -3 -m py_compile "%TARGET%\bx1_services\dottts_service\app.py"
)
if errorlevel 1 goto :fail

echo.
echo Stopping any old Dot.TTS process still using the previous mode...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0helpers\stop_old_dottts.ps1"

echo.
echo ============================================================
echo  Force-standard V3 installed successfully
echo ============================================================
echo Backup: %BACKUP%
echo.
echo Now start START_DOT_TTS_MF.bat.
echo The service window should show:
echo   Mode: standard compatibility mode (torch.compile disabled)
echo.
echo In Voice Lab press Refresh health and confirm:
echo   "optimize": false
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: Update or validation failed. Restoring backup...
copy /Y "%BACKUP%\bx1_services\dottts_service\app.py" "%TARGET%\bx1_services\dottts_service\app.py" >nul
copy /Y "%BACKUP%\scripts\start_dottts_wsl.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1" >nul
echo Restore complete. See the error above.
pause
exit /b 1

:fail_no_restore
echo.
echo ERROR: The backup could not be created. No project files were changed.
pause
exit /b 1
