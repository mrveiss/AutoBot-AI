# AutoBot NPU Worker - Uninstallation Script
# Run as Administrator

#Requires -RunAsAdministrator

param(
    [switch]$KeepData,
    [switch]$KeepLogs,
    [switch]$Force,
    [string]$InstallPath = "C:\AutoBot\NPU"
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  AutoBot NPU Worker - Uninstall" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

# Confirmation
if (-not $Force) {
    Write-Warning "This will remove the AutoBot NPU Worker service"
    $response = Read-Host "Continue with uninstallation? (y/N)"
    if ($response -ne "y") {
        Write-Info "Uninstallation cancelled"
        exit 0
    }
}

# Check if service exists
$service = Get-Service -Name "AutoBotNPUWorker" -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Warning "AutoBot NPU Worker service not found"
} else {
    # Stop service
    Write-Info "Stopping service..."
    if ($service.Status -eq "Running") {
        Stop-Service -Name AutoBotNPUWorker -Force
        Start-Sleep -Seconds 2
    }
    Write-Success "Service stopped"

    # Remove service using NSSM
    $nssmPath = Join-Path $InstallPath "nssm\nssm.exe"
    if (Test-Path $nssmPath) {
        Write-Info "Removing Windows Service..."
        & $nssmPath remove AutoBotNPUWorker confirm
        Write-Success "Service removed"
    } else {
        # Fallback to sc.exe
        Write-Info "Removing service (fallback method)..."
        sc.exe delete AutoBotNPUWorker
    }
}

# Remove firewall rule
Write-Info "Removing firewall rule..."
try {
    Get-NetFirewallRule -DisplayName "AutoBot NPU Worker" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Success "Firewall rule removed"
} catch {
    Write-Warning "Failed to remove firewall rule: $_"
}

# Clean up logs
if (-not $KeepLogs) {
    Write-Info "Cleaning up logs..."
    $logsPath = Join-Path $InstallPath "logs"
    if (Test-Path $logsPath) {
        Remove-Item -Path $logsPath -Recurse -Force
        Write-Success "Logs removed"
    }
}

# Clean up data
if (-not $KeepData) {
    Write-Info "Cleaning up data..."
    $dataPath = Join-Path $InstallPath "data"
    $modelsPath = Join-Path $InstallPath "models"

    if (Test-Path $dataPath) {
        Remove-Item -Path $dataPath -Recurse -Force
    }
    if (Test-Path $modelsPath) {
        Remove-Item -Path $modelsPath -Recurse -Force
    }
    Write-Success "Data removed"
}

# Ask about complete removal
if (-not $Force) {
    Write-Host ""
    $response = Read-Host "Remove entire installation directory? (y/N)"
    if ($response -eq "y") {
        Write-Info "Removing installation directory: $InstallPath"
        Set-Location $env:USERPROFILE  # Move out of installation directory
        Remove-Item -Path $InstallPath -Recurse -Force
        Write-Success "Installation directory removed"
    } else {
        Write-Info "Installation directory preserved: $InstallPath"
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Uninstallation Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($KeepLogs) {
    Write-Info "Logs preserved in: $InstallPath\logs"
}
if ($KeepData) {
    Write-Info "Data preserved in: $InstallPath\data and $InstallPath\models"
}

Write-Host ""
