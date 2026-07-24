@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    echo Place this file in the Robot_Brain_V1_7_0 folder beside main_pyqt.py.
    pause
    exit /b 2
)

".venv\Scripts\python.exe" "create_chatgpt_snapshot.py"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo Snapshot failed with error code %RC%.
) else (
    echo The ZIP is in the snapshots folder.
)
pause
exit /b %RC%
