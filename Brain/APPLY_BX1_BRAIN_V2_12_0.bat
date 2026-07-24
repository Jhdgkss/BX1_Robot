@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo  Robot Brain V2.12.0 - Runtime Workflow and Studios
echo ============================================================
echo.
echo This update simplifies the main GUI and makes Personality
echo Studio and Voice Lab the authoritative character editors.
echo It does not replace profiles, personalities, voices, memory,
echo documents, hardware settings or runtime data.
echo.
set "TARGET="
set /p "TARGET=Enter Robot Brain project folder: "
set "TARGET=%TARGET:"=%"

if not defined TARGET (
    echo.
    echo ERROR: No project folder was entered.
    pause
    exit /b 2
)

if not exist "%TARGET%\main_pyqt.py" (
    echo.
    echo ERROR: main_pyqt.py was not found in:
    echo %TARGET%
    pause
    exit /b 2
)

set "INSTALLER=%~dp0install_v2_12_0.py"
set "PAYLOAD=%~dp0payload_v2_12_0"

if exist "%TARGET%\.venv\Scripts\python.exe" (
    "%TARGET%\.venv\Scripts\python.exe" "%INSTALLER%" "%TARGET%" "%PAYLOAD%"
    set "RESULT=%ERRORLEVEL%"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 "%INSTALLER%" "%TARGET%" "%PAYLOAD%"
        set "RESULT=%ERRORLEVEL%"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo.
            echo ERROR: Python could not be found and the project .venv is missing.
            pause
            exit /b 2
        )
        python "%INSTALLER%" "%TARGET%" "%PAYLOAD%"
        set "RESULT=%ERRORLEVEL%"
    )
)

echo.
if not "%RESULT%"=="0" (
    echo Installation failed. The installer restored the previous files.
    pause
    exit /b %RESULT%
)

pause
exit /b 0
