@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BX1 Dot.TTS Force Standard Mode V2

echo ============================================================
echo  BX1 Dot.TTS - Force Standard Mode V2
echo ============================================================
echo.
echo This update makes standard mode authoritative in BOTH:
echo   1. the Windows/WSL launcher
echo   2. the Dot.TTS service itself
echo.
echo It also prevents a direct service start from enabling
echo torch.compile unless --optimize is deliberately supplied.
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
if not exist "%TARGET%\scripts" (
  echo.
  echo ERROR: scripts folder was not found.
  pause
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%I"
set "BACKUP=%TARGET%\backups\dottts_force_standard_v2_%STAMP%"
mkdir "%BACKUP%\bx1_services\dottts_service" >nul 2>&1
mkdir "%BACKUP%\scripts" >nul 2>&1

copy /Y "%TARGET%\bx1_services\dottts_service\app.py" "%BACKUP%\bx1_services\dottts_service\app.py" >nul
copy /Y "%TARGET%\scripts\start_dottts_wsl.ps1" "%BACKUP%\scripts\start_dottts_wsl.ps1" >nul

copy /Y "%~dp0payload\bx1_services\dottts_service\app.py" "%TARGET%\bx1_services\dottts_service\app.py" >nul
if errorlevel 1 goto :fail
copy /Y "%~dp0payload\scripts\start_dottts_wsl.ps1" "%TARGET%\scripts\start_dottts_wsl.ps1" >nul
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "$errors=$null; [System.Management.Automation.Language.Parser]::ParseFile('%TARGET:\=\\%\scripts\start_dottts_wsl.ps1',[ref]$null,[ref]$errors) ^| Out-Null; if($errors.Count){$errors ^| ForEach-Object { Write-Error $_ }; exit 1}; Write-Host 'PowerShell syntax check: OK'"
if errorlevel 1 goto :fail

if exist "%TARGET%\.venv\Scripts\python.exe" (
  "%TARGET%\.venv\Scripts\python.exe" -m py_compile "%TARGET%\bx1_services\dottts_service\app.py"
) else (
  py -3 -m py_compile "%TARGET%\bx1_services\dottts_service\app.py"
)
if errorlevel 1 goto :fail

echo.
echo Stopping any old Dot.TTS instance still holding port 8092...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=((& wsl.exe --list --quiet) -replace [char]0,'') ^| Where-Object {$_.Trim()} ^| Where-Object {$_ -match 'Ubuntu^|Debian'} ^| Select-Object -First 1; if($d){$d=$d.Trim(); & wsl.exe -d $d -- bash -lc 'pkill -f "[b]x1_services/dottts_service/app.py" 2^>/dev/null ^|^| true'; Start-Sleep -Seconds 2; Write-Host ('Stopped old Dot.TTS processes in ' + $d)} else {Write-Host 'No Ubuntu/Debian WSL distribution was found; stop the service manually.'}"

echo.
echo ============================================================
echo  Force-standard update installed successfully
echo ============================================================
echo Backup: %BACKUP%
echo.
echo Now start START_DOT_TTS_MF.bat.
echo The service window must show BOTH:
echo   Mode: standard compatibility mode (torch.compile disabled)
echo   Model: rednote-hilab/dots.tts-mf
echo.
echo Then reload the Voice Lab, press Refresh health, and confirm:
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
