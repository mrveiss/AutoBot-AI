# AutoBot NPU Worker - View Logs Script

param(
    [int]$Lines = 50,
    [switch]$Follow,
    [switch]$Error,
    [string]$InstallPath = "C:\AutoBot\NPU"
)

$ErrorActionPreference = "SilentlyContinue"

function Write-Info { Write-Host $args -ForegroundColor Cyan }

$logPath = if ($Error) {
    Join-Path $InstallPath "logs\error.log"
} else {
    Join-Path $InstallPath "logs\service.log"
}

if (-not (Test-Path $logPath)) {
    Write-Host "Log file not found: $logPath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Available log files:" -ForegroundColor Cyan
    Get-ChildItem (Join-Path $InstallPath "logs") -Filter "*.log" | ForEach-Object {
        Write-Host "  $($_.Name)"
    }
    exit 1
}

Write-Info "Viewing log: $logPath"
Write-Host ""

if ($Follow) {
    Get-Content $logPath -Tail $Lines -Wait
} else {
    Get-Content $logPath -Tail $Lines
}
