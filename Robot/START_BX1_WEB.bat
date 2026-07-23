@echo off
setlocal
cd /d "%~dp0python"
start "" "http://127.0.0.1:8088"
python main.py --standalone
pause
