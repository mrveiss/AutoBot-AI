# AutoBot NPU Worker - Restart Service Script

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "Restarting AutoBot NPU Worker service..."

try {
    Restart-Service -Name AutoBotNPUWorker -Force
    Start-Sleep -Seconds 3

    $service = Get-Service -Name AutoBotNPUWorker
    if ($service.Status -eq "Running") {
        Write-Success "Service restarted successfully"
        Write-Host "  Status: $($service.Status)"
        Write-Host "  Health endpoint: http://localhost:8082/health"
    } else {
        Write-Error "Service failed to restart (Status: $($service.Status))"
        Write-Info "Check logs: .\scripts\view-logs.ps1"
        exit 1
    }
} catch {
    Write-Error "Failed to restart service: $_"
    exit 1
}
