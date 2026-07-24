$ErrorActionPreference = "Continue"
try {
    $distros = (& wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() }
    $distro = $distros | Where-Object { $_ -match "Ubuntu" } | Select-Object -First 1
    if (-not $distro) {
        $distro = $distros | Where-Object { $_ -match "Debian" } | Select-Object -First 1
    }
    if (-not $distro) {
        Write-Host "No Ubuntu/Debian WSL distribution found. Stop Dot.TTS manually if it is still running."
        exit 0
    }
    $distro = $distro.Trim()
    & wsl.exe -d $distro -- bash -lc 'pkill -f "[b]x1_services/dottts_service/app.py" >/dev/null 2>&1 || true'
    Start-Sleep -Seconds 2
    Write-Host "Stopped old Dot.TTS processes in $distro"
    exit 0
} catch {
    Write-Host "Could not stop Dot.TTS automatically: $($_.Exception.Message)"
    Write-Host "Use Stop Voice Service in Robot Brain before restarting Dot.TTS."
    exit 0
}
