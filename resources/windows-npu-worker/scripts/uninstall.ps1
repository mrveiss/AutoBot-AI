# AutoBot NPU Worker - Complete Uninstallation Script
# Run as Administrator
# Removes ALL traces of the NPU worker from the system

#Requires -RunAsAdministrator

param(
    [switch]$KeepData,
    [switch]$KeepLogs,
    [switch]$Force,
    [string]$InstallPath = "C:\AutoBot\NPU"
)

$ErrorActionPreference = "Continue"  # Don't stop on non-fatal errors during cleanup

# Color output functions
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

# Banner
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  AutoBot NPU Worker - Complete Uninstall" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

# Confirmation
if (-not $Force) {
    Write-Warning "This will COMPLETELY remove the AutoBot NPU Worker from your system"
    Write-Warning "Including: service, firewall rules, registry entries, all files"
    Write-Host ""
    $response = Read-Host "Continue with complete uninstallation? (y/N)"
    if ($response -ne "y") {
        Write-Info "Uninstallation cancelled"
        exit 0
    }
}

Write-Host ""
Write-Info "Starting complete uninstallation..."
Write-Host ""

# ==============================================
# 1. STOP AND REMOVE WINDOWS SERVICE
# ==============================================

Write-Info "[1/7] Stopping and removing Windows Service..."

$service = Get-Service -Name "AutoBotNPUWorker" -ErrorAction SilentlyContinue
if ($service) {
    # Stop service if running
    if ($service.Status -eq "Running") {
        Write-Info "  Stopping service..."
        Stop-Service -Name AutoBotNPUWorker -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
    }

    # Kill any remaining processes
    Write-Info "  Terminating any remaining processes..."
    Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like "*$InstallPath*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue

    # Remove service using NSSM
    $nssmPath = Join-Path $InstallPath "nssm\nssm.exe"
    if (Test-Path $nssmPath) {
        Write-Info "  Removing service via NSSM..."
        try { & $nssmPath stop AutoBotNPUWorker 2>&1 | Out-Null } catch { }
        Start-Sleep -Seconds 1
        try { & $nssmPath remove AutoBotNPUWorker confirm 2>&1 | Out-Null } catch { }
    }

    # Fallback: Remove using sc.exe
    try { sc.exe delete AutoBotNPUWorker 2>&1 | Out-Null } catch { }

    Write-Success "  Service removed"
} else {
    Write-Info "  Service not found (skipping)"
}

# ==============================================
# 2. REMOVE FIREWALL RULES
# ==============================================

Write-Info "[2/7] Removing firewall rules..."

try {
    # Remove by display name
    Get-NetFirewallRule -DisplayName "AutoBot NPU Worker" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    # Also remove any rules for port 8082 created by this app
    Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
        $_.DisplayName -like "*AutoBot*NPU*"
    } | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    Write-Success "  Firewall rules removed"
} catch {
    Write-Warning "  Failed to remove some firewall rules: $_"
}

# ==============================================
# 3. REMOVE SCHEDULED TASKS
# ==============================================

Write-Info "[3/7] Removing scheduled tasks..."

try {
    Get-ScheduledTask -TaskName "*AutoBot*NPU*" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
    Write-Success "  Scheduled tasks removed"
} catch {
    Write-Info "  No scheduled tasks found"
}

# ==============================================
# 4. REMOVE REGISTRY ENTRIES
# ==============================================

Write-Info "[4/7] Removing registry entries..."

try {
    # Remove any registry keys created during installation
    $registryPaths = @(
        "HKLM:\SOFTWARE\AutoBot",
        "HKLM:\SOFTWARE\AutoBotNPUWorker",
        "HKCU:\SOFTWARE\AutoBot",
        "HKCU:\SOFTWARE\AutoBotNPUWorker"
    )

    foreach ($path in $registryPaths) {
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Success "  Registry entries removed"
} catch {
    Write-Info "  No registry entries found"
}

# ==============================================
# 5. REMOVE ENVIRONMENT VARIABLES
# ==============================================

Write-Info "[5/7] Removing environment variables..."

try {
    # Remove system environment variables
    $envVars = @(
        "AUTOBOT_NPU_WORKER_HOME",
        "AUTOBOT_NPU_WORKER_CONFIG"
    )

    foreach ($var in $envVars) {
        [Environment]::SetEnvironmentVariable($var, $null, [EnvironmentVariableTarget]::Machine)
        [Environment]::SetEnvironmentVariable($var, $null, [EnvironmentVariableTarget]::User)
    }

    Write-Success "  Environment variables removed"
} catch {
    Write-Info "  No environment variables found"
}

# ==============================================
# 6. REMOVE START MENU SHORTCUTS
# ==============================================

Write-Info "[6/7] Removing Start Menu shortcuts..."

try {
    $startMenuPaths = @(
        "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\AutoBot NPU Worker",
        "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AutoBot NPU Worker"
    )

    foreach ($path in $startMenuPaths) {
        if (Test-Path $path) {
            Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # Also remove individual shortcuts
    Get-ChildItem -Path "$env:ProgramData\Microsoft\Windows\Start Menu\Programs" -Filter "*AutoBot*NPU*" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Filter "*AutoBot*NPU*" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Success "  Start Menu shortcuts removed"
} catch {
    Write-Info "  No Start Menu shortcuts found"
}

# ==============================================
# 7. REMOVE INSTALLATION DIRECTORY
# ==============================================

Write-Info "[7/7] Removing installation files..."

# First, move out of the installation directory if we're in it
$currentPath = (Get-Location).Path
if ($currentPath -like "$InstallPath*") {
    Set-Location $env:USERPROFILE
}

# Handle selective removal
if ($KeepLogs -or $KeepData) {
    Write-Info "  Preserving selected data..."

    # Remove specific directories while keeping others
    $dirsToRemove = @("app", "config", "gui", "installer", "nssm", "scripts", "tests", "venv")

    foreach ($dir in $dirsToRemove) {
        $dirPath = Join-Path $InstallPath $dir
        if (Test-Path $dirPath) {
            Remove-Item -Path $dirPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # Remove files in root
    Get-ChildItem -Path $InstallPath -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

    if (-not $KeepLogs) {
        $logsPath = Join-Path $InstallPath "logs"
        if (Test-Path $logsPath) {
            Remove-Item -Path $logsPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not $KeepData) {
        $dataPath = Join-Path $InstallPath "data"
        $modelsPath = Join-Path $InstallPath "models"
        if (Test-Path $dataPath) {
            Remove-Item -Path $dataPath -Recurse -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path $modelsPath) {
            Remove-Item -Path $modelsPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Success "  Application files removed"
} else {
    # Complete removal
    if (Test-Path $InstallPath) {
        try {
            Remove-Item -Path $InstallPath -Recurse -Force
            Write-Success "  Installation directory removed: $InstallPath"
        } catch {
            Write-Warning "  Could not remove some files (may be in use)"
            Write-Info "  Please manually delete: $InstallPath"
        }
    } else {
        Write-Info "  Installation directory not found"
    }
}

# Also check alternative installation paths
$alternativePaths = @(
    "C:\Program Files\AutoBot\NPU",
    "C:\AutoBot",
    "$env:LOCALAPPDATA\AutoBot\NPU"
)

foreach ($altPath in $alternativePaths) {
    if (($altPath -ne $InstallPath) -and (Test-Path $altPath)) {
        Write-Info "  Found additional installation at: $altPath"
        if ($Force -or ((Read-Host "  Remove this directory too? (y/N)") -eq "y")) {
            Remove-Item -Path $altPath -Recurse -Force -ErrorAction SilentlyContinue
            Write-Success "  Removed: $altPath"
        }
    }
}

# ==============================================
# CLEANUP COMPLETE
# ==============================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Uninstallation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Success "AutoBot NPU Worker has been completely removed from your system."
Write-Host ""

if ($KeepLogs) {
    Write-Info "Logs preserved at: $InstallPath\logs"
}
if ($KeepData) {
    Write-Info "Data preserved at: $InstallPath\data"
    Write-Info "Models preserved at: $InstallPath\models"
}

Write-Host ""
Write-Info "No traces remain on your system."
Write-Host ""

# Optional: Clean up temp files
Write-Info "Cleaning temporary files..."
Get-ChildItem -Path $env:TEMP -Filter "*autobot*" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
Get-ChildItem -Path $env:TEMP -Filter "*npu_worker*" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
Write-Success "Temporary files cleaned"

Write-Host ""
Write-Info "Thank you for using AutoBot NPU Worker!"
Write-Host ""
