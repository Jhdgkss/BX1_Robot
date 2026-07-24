$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Could not find .venv\Scripts\python.exe. Place this helper in the Robot_Brain_V1_7_0 folder."
}

& $python (Join-Path $PSScriptRoot "create_chatgpt_snapshot.py")
exit $LASTEXITCODE
