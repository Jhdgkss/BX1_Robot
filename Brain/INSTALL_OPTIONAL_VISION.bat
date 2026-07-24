@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Robot Brain Optional YOLO Vision

echo ============================================================
echo  Robot Brain - Optional YOLO / OpenCV Vision
echo ============================================================
echo This is not required for the main GUI, camera frames or Dot.TTS.
echo.

if not exist ".venv\Scripts\python.exe" (
    call scripts\INSTALL_CORE.bat
    if errorlevel 1 goto :FAIL
)

".venv\Scripts\python.exe" -m pip install "opencv-python==4.10.0.84" "ultralytics>=8.3.0"
if errorlevel 1 goto :FAIL

echo.
echo Optional object detection is ready.
pause
exit /b 0

:FAIL
echo.
echo Optional vision installation failed. The main Robot Brain remains usable.
pause
exit /b 1
