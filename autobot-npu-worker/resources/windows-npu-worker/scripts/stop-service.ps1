# AutoBot NPU Worker - Stop Service Script

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "Stopping AutoBot NPU Worker service..."

try {
    $service = Get-Service -Name AutoBotNPUWorker
    if ($service.Status -eq "Running") {
        Stop-Service -Name AutoBotNPUWorker -Force
        Start-Sleep -Seconds 2
        Write-Success "Service stopped successfully"
    } else {
        Write-Info "Service is not running (Status: $($service.Status))"
    }
} catch {
    Write-Error "Failed to stop service: $_"
    exit 1
}
