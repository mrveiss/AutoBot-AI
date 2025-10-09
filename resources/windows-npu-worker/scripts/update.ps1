# AutoBot NPU Worker - Update Script

#Requires -RunAsAdministrator

param(
    [string]$InstallPath = "C:\AutoBot\NPU",
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AutoBot NPU Worker - Update" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if installed
if (-not (Test-Path $InstallPath)) {
    Write-Error "Installation not found at: $InstallPath"
    exit 1
}

# Backup current installation
if (-not $SkipBackup) {
    Write-Info "Creating backup..."
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = "$InstallPath.backup.$timestamp"

    try {
        Copy-Item -Path $InstallPath -Destination $backupPath -Recurse -Force
        Write-Success "Backup created: $backupPath"
    } catch {
        Write-Warning "Backup failed: $_"
        $response = Read-Host "Continue without backup? (y/N)"
        if ($response -ne "y") {
            exit 1
        }
    }
}

# Stop service
Write-Info "Stopping service..."
Stop-Service -Name AutoBotNPUWorker -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Update Python dependencies
Write-Info "Updating Python dependencies..."
$pipExe = Join-Path $InstallPath "venv\Scripts\pip.exe"

try {
    # Upgrade pip
    & $pipExe install --upgrade pip | Out-Null

    # Update requirements
    & $pipExe install --upgrade -r (Join-Path $InstallPath "requirements.txt")
    Write-Success "Dependencies updated"
} catch {
    Write-Error "Failed to update dependencies: $_"
    Write-Info "Restoring from backup..."
    if (-not $SkipBackup -and (Test-Path $backupPath)) {
        Remove-Item -Path $InstallPath -Recurse -Force
        Copy-Item -Path $backupPath -Destination $InstallPath -Recurse -Force
    }
    exit 1
}

# Start service
Write-Info "Starting service..."
Start-Service -Name AutoBotNPUWorker
Start-Sleep -Seconds 3

# Verify
$service = Get-Service -Name AutoBotNPUWorker
if ($service.Status -eq "Running") {
    Write-Success "Service started successfully"

    # Health check
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8082/health" -Method Get -TimeoutSec 10
        Write-Success "Health check: PASSED"
    } catch {
        Write-Warning "Health check failed (service may need more time to initialize)"
    }
} else {
    Write-Error "Service failed to start"
    Write-Info "Check logs: .\scripts\view-logs.ps1"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Update Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
