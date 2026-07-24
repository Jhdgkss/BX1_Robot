@echo off
setlocal EnableExtensions
title BX1 Robot Brain - Stop

echo Stopping Dot.TTS gracefully if it is running...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8092/shutdown -Headers @{'X-Robot-Brain-Shutdown'='1'} -ContentType application/json -Body '{}' -TimeoutSec 3 ^| Out-Null; Write-Host 'Dot.TTS shutdown requested.' } catch { Write-Host 'Dot.TTS was not running on port 8092.' }"

echo Stopping the Robot Brain listener on port 8765...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$connections=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if(-not $connections){Write-Host 'Robot Brain was not running.'}; foreach($connection in $connections){$process=Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; if($process -and $process.ProcessName -match '^(python|pythonw)$'){Write-Host ('Stopping '+$process.ProcessName+' PID '+$process.Id); Stop-Process -Id $process.Id -Force}else{Write-Host 'Listener is not a Robot Brain Python process; it was left alone.'}}"

echo.
echo Ollama is left running deliberately.
pause
