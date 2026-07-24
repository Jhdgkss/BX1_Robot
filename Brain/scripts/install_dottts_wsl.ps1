$ErrorActionPreference = "Stop"

function Stop-WithGuidance([string]$Message) {
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    exit 1
}

Write-Host "Checking Windows Subsystem for Linux..." -ForegroundColor Cyan
try {
    & wsl.exe --status | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "WSL status failed" }
} catch {
    Write-Host "WSL2 is not installed yet." -ForegroundColor Yellow
    Write-Host "Open PowerShell as Administrator and run:" -ForegroundColor White
    Write-Host "  wsl.exe --install -d Ubuntu" -ForegroundColor Green
    Write-Host "Restart Windows if requested, open Ubuntu once to create its user, then rerun INSTALL_DOT_TTS.bat."
    exit 2
}

$Distros = (& wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() }
if (-not $Distros) {
    Stop-WithGuidance "WSL is enabled but no Linux distribution is installed. Run: wsl.exe --install -d Ubuntu"
}

Write-Host "Installed WSL distributions: $($Distros -join ', ')" -ForegroundColor DarkGray
$Distro = $Distros | Where-Object { $_ -match "Ubuntu" } | Select-Object -First 1
if (-not $Distro) { $Distro = $Distros | Where-Object { $_ -match "Debian" } | Select-Object -First 1 }
if (-not $Distro) { Stop-WithGuidance "No Ubuntu or Debian WSL distribution was found. Run: wsl.exe --install -d Ubuntu" }
$Distro = $Distro.Trim()
Write-Host "Using WSL distribution: $Distro" -ForegroundColor Cyan
Write-Host "Updating WSL..." -ForegroundColor Cyan
& wsl.exe --update

$ProjectWindows = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectWsl = (& wsl.exe -d $Distro -- wslpath -a -u $ProjectWindows).Trim()
if (-not $ProjectWsl) { Stop-WithGuidance "Could not translate the Robot Brain project path into a WSL path." }

Write-Host "Installing Dot.TTS inside WSL2..." -ForegroundColor Cyan
Write-Host "Linux environment: ~/.robot_brain_dottts_venv" -ForegroundColor DarkGray
& wsl.exe -d $Distro -- bash "$ProjectWsl/scripts/install_dottts_wsl.sh"
if ($LASTEXITCODE -ne 0) { Stop-WithGuidance "The Linux-side Dot.TTS installation failed. Run CHECK_DOT_TTS_WSL.bat for diagnostics." }

Write-Host ""
Write-Host "Dot.TTS is ready." -ForegroundColor Green
Write-Host "Next: run START_DOT_TTS_MF.bat and leave its window open."
exit 0
