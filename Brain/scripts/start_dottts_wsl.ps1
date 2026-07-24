param(
    [ValidateSet("mf", "soar")]
    [string]$Model = "mf",
    [ValidateRange(1024, 65535)]
    [int]$Port = 8092,
    [string]$Profile = "shared"
)
$ErrorActionPreference = "Stop"

$ProjectWindows = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
try {
    $Distros = (& wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() }
    $Distro = $Distros | Where-Object { $_ -match "Ubuntu" } | Select-Object -First 1
    if (-not $Distro) { $Distro = $Distros | Where-Object { $_ -match "Debian" } | Select-Object -First 1 }
    if (-not $Distro) { throw "No Ubuntu or Debian WSL distribution found" }
    $Distro = $Distro.Trim()
    $ProjectWsl = (& wsl.exe -d $Distro -- wslpath -a -u $ProjectWindows).Trim()
} catch {
    Write-Host "WSL2 is not ready. Run INSTALL_DOT_TTS.bat first." -ForegroundColor Red
    exit 1
}
if (-not $ProjectWsl) {
    Write-Host "Could not locate this project inside WSL2." -ForegroundColor Red
    exit 1
}

Write-Host "Starting Dot.TTS $($Model.ToUpper()) in WSL2..." -ForegroundColor Cyan
Write-Host "Mode: standard compatibility mode (torch.compile disabled)" -ForegroundColor Yellow
Write-Host "English Voice Lab: http://127.0.0.1:$Port/lab" -ForegroundColor Green
Write-Host "Shared GPU service: robot profiles keep separate reference voices." -ForegroundColor Yellow
Write-Host "Leave it running for fast subsequent starts; use Stop Voice Service when needed." -ForegroundColor Yellow
Write-Host ""

$LinuxHome = (& wsl.exe -d $Distro -- bash -c 'printf %s "$HOME"').Trim()
$Python = "$LinuxHome/.robot_brain_dottts_venv/bin/python"
& wsl.exe -d $Distro -- test -x $Python
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dot.TTS is not installed. Run INSTALL_DOT_TTS.bat first." -ForegroundColor Red
    exit 2
}

$ServiceArgs = @(
    "$ProjectWsl/bx1_services/dottts_service/app.py",
    "--host", "0.0.0.0",
    "--port", "$Port",
    "--model", "$Model",
    "--profile", "$Profile",
    "--no-optimize"
)
& wsl.exe -d $Distro -- $Python @ServiceArgs
exit $LASTEXITCODE
