param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)
$ErrorActionPreference = "Stop"
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $Path,
    [ref]$tokens,
    [ref]$errors
)
if ($errors -and $errors.Count -gt 0) {
    foreach ($parseError in $errors) {
        Write-Error $parseError.Message
    }
    exit 1
}
Write-Host "PowerShell syntax check: OK"
exit 0
