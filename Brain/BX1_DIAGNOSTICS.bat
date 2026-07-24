@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Robot Brain V2.8.1 Diagnostics

echo ============================================================
echo  Robot Brain V2.8.1 - Diagnostics
echo ============================================================
echo Folder: %CD%
echo.

if exist VERSION.txt type VERSION.txt
echo.

echo Checking Windows Python environment...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version
    ".venv\Scripts\python.exe" -c "import PyQt6, requests, edge_tts, pygame; print('GUI and Edge fallback: OK')" 2^>^&1
) else (
    echo .venv missing. Run START_BX1_BRAIN.bat once.
)
echo.

echo Checking Ollama...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 3; Write-Host ('Ollama: OK HTTP '+$r.StatusCode) } catch { Write-Host ('Ollama: OFFLINE - '+$_.Exception.Message) }"
echo.

echo Checking Robot Brain API on 8765...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/status -TimeoutSec 3; Write-Host ('Brain API: OK HTTP '+$r.StatusCode) } catch { Write-Host ('Brain API: not running - '+$_.Exception.Message) }"
echo.

echo Checking Dot.TTS on 8092...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod http://127.0.0.1:8092/health -TimeoutSec 4; Write-Host ('Dot.TTS: OK model=' + $r.model + ' loaded=' + $r.loaded) } catch { Write-Host ('Dot.TTS: not running - '+$_.Exception.Message) }"
echo.

echo Running detailed WSL2 voice diagnostics...
call CHECK_DOT_TTS_WSL.bat
