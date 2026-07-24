$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8092"
$health = Invoke-RestMethod -Uri "$base/health" -TimeoutSec 5
$health | ConvertTo-Json -Depth 6

$body = @{
    text = "Hello John. The Robot Brain Dot TTS service is online."
    num_steps = 4
    guidance_scale = 1.2
    language = "EN"
} | ConvertTo-Json

$result = Invoke-RestMethod -Uri "$base/speak" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600
$result | ConvertTo-Json -Depth 6
if ($result.ok -and $result.audio_url) {
    Start-Process $result.audio_url
}
