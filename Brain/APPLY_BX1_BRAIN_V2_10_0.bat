@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "PATCH_DIR=%~dp0"
set "PAYLOAD=%PATCH_DIR%payload"
set "TARGET=%~1"

if not defined TARGET if exist "%CD%\main_pyqt.py" set "TARGET=%CD%"
if not defined TARGET (
  for %%I in ("%PATCH_DIR%..") do set "PARENT=%%~fI"
  if exist "!PARENT!\main_pyqt.py" set "TARGET=!PARENT!"
)
if not defined TARGET (
  echo Enter the full path to the current Robot Brain project folder.
  set /p "TARGET=Brain project: "
)

if not exist "%TARGET%\main_pyqt.py" (
  echo.
  echo ERROR: main_pyqt.py was not found in:
  echo   %TARGET%
  echo.
  pause
  exit /b 2
)
if not exist "%PAYLOAD%\main_pyqt.py" (
  echo ERROR: Patch payload is incomplete.
  pause
  exit /b 3
)

for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
set "BACKUP=%TARGET%\backups\v2_10_0_%STAMP%"
mkdir "%BACKUP%\bx1_modules" >nul 2>&1

copy /Y "%TARGET%\main_pyqt.py" "%BACKUP%\main_pyqt.py" >nul
if exist "%TARGET%\bx1_modules\body_voice_library.py" copy /Y "%TARGET%\bx1_modules\body_voice_library.py" "%BACKUP%\bx1_modules\body_voice_library.py" >nul
if exist "%TARGET%\CHANGELOG_V2.md" copy /Y "%TARGET%\CHANGELOG_V2.md" "%BACKUP%\CHANGELOG_V2.md" >nul
if exist "%TARGET%\VERSION.txt" copy /Y "%TARGET%\VERSION.txt" "%BACKUP%\VERSION.txt" >nul
if exist "%TARGET%\README_START_HERE_V2.md" copy /Y "%TARGET%\README_START_HERE_V2.md" "%BACKUP%\README_START_HERE_V2.md" >nul

copy /Y "%PAYLOAD%\main_pyqt.py" "%TARGET%\main_pyqt.py" >nul || goto :failed
if not exist "%TARGET%\bx1_modules" mkdir "%TARGET%\bx1_modules"
copy /Y "%PAYLOAD%\bx1_modules\body_voice_library.py" "%TARGET%\bx1_modules\body_voice_library.py" >nul || goto :failed
copy /Y "%PAYLOAD%\CHANGELOG_V2.md" "%TARGET%\CHANGELOG_V2.md" >nul
copy /Y "%PAYLOAD%\VERSION.txt" "%TARGET%\VERSION.txt" >nul
copy /Y "%PAYLOAD%\README_START_HERE_V2.md" "%TARGET%\README_START_HERE_V2.md" >nul

pushd "%TARGET%"
if exist "%TARGET%\.venv\Scripts\python.exe" (
  "%TARGET%\.venv\Scripts\python.exe" -m py_compile main_pyqt.py bx1_modules\body_voice_library.py
) else (
  py -3 -m py_compile main_pyqt.py bx1_modules\body_voice_library.py
)
if errorlevel 1 (
  popd
  goto :failed
)
popd

echo.
echo ============================================================
echo  Robot Brain V2.10.0 installed successfully
echo ============================================================
echo Backup: %BACKUP%
echo.
echo Start Robot Brain, then open:
echo   Robot ^> Body Wake / Queued Speech
echo Save the definitions and press Generate All.
echo.
pause
exit /b 0

:failed
echo.
echo ERROR: Validation failed. Restoring the previous files...
copy /Y "%BACKUP%\main_pyqt.py" "%TARGET%\main_pyqt.py" >nul 2>&1
if exist "%BACKUP%\bx1_modules\body_voice_library.py" (
  copy /Y "%BACKUP%\bx1_modules\body_voice_library.py" "%TARGET%\bx1_modules\body_voice_library.py" >nul 2>&1
) else (
  del /Q "%TARGET%\bx1_modules\body_voice_library.py" >nul 2>&1
)
if exist "%BACKUP%\CHANGELOG_V2.md" copy /Y "%BACKUP%\CHANGELOG_V2.md" "%TARGET%\CHANGELOG_V2.md" >nul 2>&1
if exist "%BACKUP%\VERSION.txt" copy /Y "%BACKUP%\VERSION.txt" "%TARGET%\VERSION.txt" >nul 2>&1
if exist "%BACKUP%\README_START_HERE_V2.md" copy /Y "%BACKUP%\README_START_HERE_V2.md" "%TARGET%\README_START_HERE_V2.md" >nul 2>&1
echo Previous files restored from %BACKUP%
pause
exit /b 1
