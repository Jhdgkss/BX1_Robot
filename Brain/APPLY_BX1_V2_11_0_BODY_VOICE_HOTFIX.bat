@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

echo ============================================================
echo  BX1 Robot Brain V2.11.0 - Body Voice Library Hotfix
echo ============================================================
echo.

set "PATCH_ROOT=%~dp0"
set "SOURCE=%PATCH_ROOT%payload\bx1_modules\body_voice_library.py"
set "TARGET=%~1"

if not defined TARGET (
    if exist "%CD%\main_pyqt.py" (
        set "TARGET=%CD%"
    ) else (
        echo Enter the Robot Brain project folder containing main_pyqt.py.
        echo Example:
        echo C:\Git WorkSpace\LLM\Local LLM\Robot V2\Robot_Brain_Professional_V2_9-0
        echo.
        set /p "TARGET=Project folder: "
    )
)

rem Remove surrounding quotation marks, then resolve to a full path.
set "TARGET=%TARGET:"=%"
for %%I in ("%TARGET%") do set "TARGET=%%~fI"

echo.
echo Project: %TARGET%
echo.

if not exist "%TARGET%\main_pyqt.py" (
    echo ERROR: main_pyqt.py was not found in:
    echo        %TARGET%
    echo.
    pause
    exit /b 1
)

if not exist "%SOURCE%" (
    echo ERROR: Hotfix payload is missing:
    echo        %SOURCE%
    echo.
    pause
    exit /b 1
)

if not exist "%TARGET%\bx1_modules" mkdir "%TARGET%\bx1_modules" >nul 2>&1

if exist "%TARGET%\bx1_modules\body_voice_library.py" (
    copy /Y "%TARGET%\bx1_modules\body_voice_library.py" "%TARGET%\bx1_modules\body_voice_library.py.before_v2_11_0_hotfix.bak" >nul
)

copy /Y "%SOURCE%" "%TARGET%\bx1_modules\body_voice_library.py" >nul
if errorlevel 1 goto :failed

set "PYTHON=%TARGET%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_FALLBACK set "PYTHON_FALLBACK=%%P"
    if defined PYTHON_FALLBACK (
        set "PYTHON=%PYTHON_FALLBACK%"
    ) else (
        echo ERROR: Python was not found in the project virtual environment or PATH.
        goto :failed
    )
)

set "BX1_HOTFIX_TARGET=%TARGET%"
"%PYTHON%" -m py_compile "%TARGET%\bx1_modules\body_voice_library.py" "%TARGET%\main_pyqt.py"
if errorlevel 1 goto :failed

"%PYTHON%" -c "import os,sys; sys.path.insert(0, os.environ['BX1_HOTFIX_TARGET']); import bx1_modules.body_voice_library as m; print('Import check OK:', m.BodyVoiceLibrary.__name__)"
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  Hotfix installed successfully
echo ============================================================
echo.
echo The missing file has been installed:
echo %TARGET%\bx1_modules\body_voice_library.py
echo.
echo Start Robot Brain normally.
echo.
pause
exit /b 0

:failed
echo.
echo ERROR: The hotfix or validation failed.
echo Check the error shown above. The original project was not otherwise changed.
echo.
pause
exit /b 1
