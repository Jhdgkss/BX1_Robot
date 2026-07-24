$ErrorActionPreference = "Continue"
Write-Host "Robot Brain - Dot.TTS WSL2 Diagnostics" -ForegroundColor Cyan
Write-Host ""
Write-Host "WSL status:" -ForegroundColor White
& wsl.exe --status
Write-Host ""
Write-Host "Installed distributions:" -ForegroundColor White
& wsl.exe --list --verbose
$Distros = (& wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() }
$Distro = $Distros | Where-Object { $_ -match "Ubuntu" } | Select-Object -First 1
if (-not $Distro) { $Distro = $Distros | Where-Object { $_ -match "Debian" } | Select-Object -First 1 }
if ($Distro) { $Distro = $Distro.Trim() }
Write-Host ""
Write-Host "Linux and NVIDIA visibility:" -ForegroundColor White
if (-not $Distro) {
    Write-Host "No Ubuntu or Debian distribution found." -ForegroundColor Red
    exit 1
}
& wsl.exe -d $Distro -- bash -lc "uname -a; echo; if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; elif test -x /usr/lib/wsl/lib/nvidia-smi; then /usr/lib/wsl/lib/nvidia-smi; else echo 'nvidia-smi is not visible inside WSL.'; fi"
Write-Host ""
Write-Host "Dot.TTS environment:" -ForegroundColor White
$ProjectWindows = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectWsl = (& wsl.exe -d $Distro -- wslpath -a -u $ProjectWindows).Trim()
$LinuxHome = (& wsl.exe -d $Distro -- bash -c 'printf %s "$HOME"').Trim()
$Python = "$LinuxHome/.robot_brain_dottts_venv/bin/python"
& wsl.exe -d $Distro -- test -x $Python
if ($LASTEXITCODE -eq 0) {
    & wsl.exe -d $Distro -- $Python "$ProjectWsl/scripts/check_dottts_runtime.py"
} else {
    Write-Host "Not installed: run INSTALL_DOT_TTS.bat" -ForegroundColor Yellow
}
