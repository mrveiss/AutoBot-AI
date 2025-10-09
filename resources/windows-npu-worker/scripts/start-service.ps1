# AutoBot NPU Worker - Start Service Script

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "Starting AutoBot NPU Worker service..."

try {
    Start-Service -Name AutoBotNPUWorker
    Start-Sleep -Seconds 2

    $service = Get-Service -Name AutoBotNPUWorker
    if ($service.Status -eq "Running") {
        Write-Success "Service started successfully"
        Write-Host "  Status: $($service.Status)"
        Write-Host "  Health endpoint: http://localhost:8082/health"
    } else {
        Write-Error "Service failed to start (Status: $($service.Status))"
        Write-Info "Check logs: .\scripts\view-logs.ps1"
        exit 1
    }
} catch {
    Write-Error "Failed to start service: $_"
    exit 1
}
