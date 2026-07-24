$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8765"
Write-Host "Checking $base/api/status"
$status = Invoke-RestMethod -Method Get -Uri "$base/api/status" -TimeoutSec 10
$status | ConvertTo-Json -Depth 6

Write-Host "Requesting a spoken Robot Brain reply..."
$body = @{
    message = "Reply with one short sentence confirming the robot voice bridge is working."
    source = "diagnostic"
    return_audio = $true
} | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "$base/api/chat" -ContentType "application/json" -Body $body -TimeoutSec 600
$result | ConvertTo-Json -Depth 8
if ($result.ok -and $result.audio_url) {
    Write-Host "PASS: Robot audio URL returned:" $result.audio_url
} else {
    throw "Robot Brain did not return an audio URL."
}
