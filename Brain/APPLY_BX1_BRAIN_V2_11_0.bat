@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "PATCH_DIR=%~dp0"
set "PAYLOAD=%PATCH_DIR%payload_v2_11_0"
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

rem Allow either a typed path or a quoted path pasted from Explorer.
set "TARGET=%TARGET:"=%"

if not exist "%TARGET%\main_pyqt.py" (
  echo.
  echo ERROR: main_pyqt.py was not found in:
  echo %TARGET%
  pause
  exit /b 1
)
if not exist "%PAYLOAD%\main_pyqt.py" (
  echo ERROR: V2.11.0 payload is missing.
  pause
  exit /b 1
)

for /f "tokens=1-4 delims=/ " %%a in ("%date%") do set "DATESTAMP=%%d%%c%%b%%a"
set "TIMESTAMP=%time: =0%"
set "TIMESTAMP=%TIMESTAMP::=%"
set "TIMESTAMP=%TIMESTAMP:.=%"
set "BACKUP=%TARGET%\backups\v2_11_0_%DATESTAMP%_%TIMESTAMP%"
mkdir "%BACKUP%\robot_brain" >nul 2>&1
mkdir "%BACKUP%\bx1_services\dottts_service" >nul 2>&1
mkdir "%BACKUP%\docs" >nul 2>&1

copy /Y "%TARGET%\main_pyqt.py" "%BACKUP%\main_pyqt.py" >nul
if exist "%TARGET%\robot_brain\personality_store.py" copy /Y "%TARGET%\robot_brain\personality_store.py" "%BACKUP%\robot_brain\personality_store.py" >nul
if exist "%TARGET%\robot_brain\personality_studio.py" copy /Y "%TARGET%\robot_brain\personality_studio.py" "%BACKUP%\robot_brain\personality_studio.py" >nul
if exist "%TARGET%\bx1_services\dottts_service\app.py" copy /Y "%TARGET%\bx1_services\dottts_service\app.py" "%BACKUP%\bx1_services\dottts_service\app.py" >nul
if exist "%TARGET%\VERSION.txt" copy /Y "%TARGET%\VERSION.txt" "%BACKUP%\VERSION.txt" >nul
if exist "%TARGET%\CHANGELOG_V2.md" copy /Y "%TARGET%\CHANGELOG_V2.md" "%BACKUP%\CHANGELOG_V2.md" >nul
if exist "%TARGET%\README_START_HERE_V2.md" copy /Y "%TARGET%\README_START_HERE_V2.md" "%BACKUP%\README_START_HERE_V2.md" >nul

mkdir "%TARGET%\robot_brain" >nul 2>&1
mkdir "%TARGET%\bx1_services\dottts_service" >nul 2>&1
mkdir "%TARGET%\docs" >nul 2>&1
mkdir "%TARGET%\tests" >nul 2>&1

copy /Y "%PAYLOAD%\main_pyqt.py" "%TARGET%\main_pyqt.py" >nul || goto :failed
copy /Y "%PAYLOAD%\robot_brain\personality_store.py" "%TARGET%\robot_brain\personality_store.py" >nul || goto :failed
copy /Y "%PAYLOAD%\robot_brain\personality_studio.py" "%TARGET%\robot_brain\personality_studio.py" >nul || goto :failed
copy /Y "%PAYLOAD%\bx1_services\dottts_service\app.py" "%TARGET%\bx1_services\dottts_service\app.py" >nul || goto :failed
copy /Y "%PAYLOAD%\VERSION.txt" "%TARGET%\VERSION.txt" >nul
copy /Y "%PAYLOAD%\CHANGELOG_V2.md" "%TARGET%\CHANGELOG_V2.md" >nul
copy /Y "%PAYLOAD%\README_START_HERE_V2.md" "%TARGET%\README_START_HERE_V2.md" >nul
copy /Y "%PAYLOAD%\PATCH_SUMMARY_V2_11_0.md" "%TARGET%\PATCH_SUMMARY_V2_11_0.md" >nul
copy /Y "%PAYLOAD%\docs\PERSONALITY_PROJECTS_GUIDE.md" "%TARGET%\docs\PERSONALITY_PROJECTS_GUIDE.md" >nul
copy /Y "%PAYLOAD%\tests\test_personality_library.py" "%TARGET%\tests\test_personality_library.py" >nul

set "PYTHON_EXE=%TARGET%\.venv\Scripts\python.exe"
set "PYTHON_ARGS="
if not exist "%PYTHON_EXE%" (
  where py >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERROR: No usable Python interpreter was found.
      echo Expected: "%TARGET%\.venv\Scripts\python.exe"
      echo Or install the Windows Python launcher ^(py.exe^).
      goto :failed
    )
    set "PYTHON_EXE=python"
  )
)

pushd "%TARGET%"
if errorlevel 1 goto :failed
"%PYTHON_EXE%" %PYTHON_ARGS% -m py_compile main_pyqt.py robot_brain\personality_store.py robot_brain\personality_studio.py bx1_services\dottts_service\app.py
if errorlevel 1 (
  popd
  goto :failed
)
"%PYTHON_EXE%" %PYTHON_ARGS% -m unittest tests.test_personality_library
if errorlevel 1 (
  popd
  goto :failed
)
popd

echo.
echo ============================================================
echo  Robot Brain V2.11.0 installed successfully
echo ============================================================
echo Backup: %BACKUP%
echo.
echo Start Robot Brain normally, then open:
echo Robot ^> Identity / Personality ^> Open Personality Studio
echo.
echo If Dot.TTS is already running, use Stop Voice Service once so
 echo the updated Voice Lab page is loaded on the next start.
echo.
pause
exit /b 0

:failed
echo.
echo ERROR: Installation or validation failed. Restoring backup...
if exist "%BACKUP%\main_pyqt.py" copy /Y "%BACKUP%\main_pyqt.py" "%TARGET%\main_pyqt.py" >nul 2>&1
if exist "%BACKUP%\robot_brain\personality_store.py" copy /Y "%BACKUP%\robot_brain\personality_store.py" "%TARGET%\robot_brain\personality_store.py" >nul 2>&1
if exist "%BACKUP%\robot_brain\personality_studio.py" copy /Y "%BACKUP%\robot_brain\personality_studio.py" "%TARGET%\robot_brain\personality_studio.py" >nul 2>&1
if exist "%BACKUP%\bx1_services\dottts_service\app.py" copy /Y "%BACKUP%\bx1_services\dottts_service\app.py" "%TARGET%\bx1_services\dottts_service\app.py" >nul 2>&1
if exist "%BACKUP%\VERSION.txt" copy /Y "%BACKUP%\VERSION.txt" "%TARGET%\VERSION.txt" >nul 2>&1
if exist "%BACKUP%\CHANGELOG_V2.md" copy /Y "%BACKUP%\CHANGELOG_V2.md" "%TARGET%\CHANGELOG_V2.md" >nul 2>&1
if exist "%BACKUP%\README_START_HERE_V2.md" copy /Y "%BACKUP%\README_START_HERE_V2.md" "%TARGET%\README_START_HERE_V2.md" >nul 2>&1
echo Restore complete. See the error above.
pause
exit /b 1
