# AutoBot NPU Worker - Windows Installation Script
# Run as Administrator

#Requires -RunAsAdministrator

param(
    [switch]$SkipPythonCheck,
    [switch]$SkipFirewall,
    [switch]$NoAutoStart,
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
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AutoBot NPU Worker - Windows Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Info "Checking prerequisites..."

# Check Windows version
$osVersion = [System.Environment]::OSVersion.Version
if ($osVersion.Major -lt 10) {
    Write-Error "Error: Windows 10 or later required"
    exit 1
}
Write-Success "Windows version: OK ($($osVersion.Major).$($osVersion.Minor))"

# Check if already installed
if (Get-Service -Name "AutoBotNPUWorker" -ErrorAction SilentlyContinue) {
    Write-Warning "AutoBot NPU Worker service already exists"
    $response = Read-Host "Do you want to reinstall? (y/N)"
    if ($response -ne "y") {
        Write-Info "Installation cancelled"
        exit 0
    }
    Write-Info "Uninstalling existing service..."
    & "$PSScriptRoot\uninstall.ps1" -KeepData
}

# Check Python installation
if (-not $SkipPythonCheck) {
    Write-Info "Checking Python installation..."
    try {
        $pythonVersion = & python --version 2>&1
        if ($pythonVersion -match "Python 3\.(\d+)") {
            $minorVersion = [int]$matches[1]
            if ($minorVersion -ge 10) {
                Write-Success "Python version: OK ($pythonVersion)"
            } else {
                Write-Error "Error: Python 3.10 or later required (found: $pythonVersion)"
                Write-Info "Download Python from: https://www.python.org/downloads/"
                exit 1
            }
        } else {
            throw "Invalid Python version"
        }
    } catch {
        Write-Error "Error: Python 3.10+ not found in PATH"
        Write-Info "Download Python from: https://www.python.org/downloads/"
        Write-Info "Or run with -SkipPythonCheck to use embedded Python"
        exit 1
    }
}

# Create installation directory
Write-Info "Creating installation directory: $InstallPath"
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
}

# Copy files to installation directory if not already there
$currentPath = (Get-Location).Path
if ($currentPath -ne $InstallPath) {
    Write-Info "Copying files to installation directory..."
    Copy-Item -Path "$currentPath\*" -Destination $InstallPath -Recurse -Force
    Set-Location $InstallPath
}

# Create virtual environment
Write-Info "Creating Python virtual environment..."
$venvPath = Join-Path $InstallPath "venv"
if (Test-Path $venvPath) {
    Write-Info "Removing existing virtual environment..."
    Remove-Item -Path $venvPath -Recurse -Force
}
& python -m venv $venvPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create virtual environment"
    exit 1
}
Write-Success "Virtual environment created"

# Activate virtual environment and install dependencies
Write-Info "Installing Python dependencies (this may take several minutes)..."
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$pipExe = Join-Path $venvPath "Scripts\pip.exe"

# Upgrade pip
Write-Info "Upgrading pip..."
& $pipExe install --upgrade pip | Out-Null

# Install requirements
Write-Info "Installing requirements..."
& $pipExe install -r (Join-Path $InstallPath "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install Python dependencies"
    exit 1
}
Write-Success "Python dependencies installed"

# Verify OpenVINO installation
Write-Info "Verifying OpenVINO installation..."
$openvinoCheck = & $pythonExe -c "import openvino; print(openvino.__version__)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "OpenVINO version: $openvinoCheck"
} else {
    Write-Warning "OpenVINO verification failed (may work in service mode)"
}

# Create directories
Write-Info "Creating directory structure..."
$directories = @("logs", "models", "data")
foreach ($dir in $directories) {
    $dirPath = Join-Path $InstallPath $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    }
}
Write-Success "Directory structure created"

# Create configuration from template if needed
$configPath = Join-Path $InstallPath "config\npu_worker.yaml"
if (-not (Test-Path $configPath)) {
    Write-Error "Configuration file not found: $configPath"
    exit 1
}
Write-Success "Configuration file: OK"

# Configure Windows Firewall
if (-not $SkipFirewall) {
    Write-Info "Configuring Windows Firewall..."
    try {
        # Remove existing rule if present
        Get-NetFirewallRule -DisplayName "AutoBot NPU Worker" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

        # Create new rule
        New-NetFirewallRule -DisplayName "AutoBot NPU Worker" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort 8082 `
            -Action Allow `
            -Profile Any `
            -Description "AutoBot NPU Worker service access" | Out-Null

        Write-Success "Firewall rule created"
    } catch {
        Write-Warning "Failed to create firewall rule: $_"
        Write-Warning "You may need to manually allow port 8082"
    }
}

# Download NSSM if not present
$nssmPath = Join-Path $InstallPath "nssm\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Info "NSSM not found, downloading..."
    try {
        $nssmDir = Join-Path $InstallPath "nssm"
        if (-not (Test-Path $nssmDir)) {
            New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null
        }

        # Download NSSM (2.24)
        $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
        $nssmZip = Join-Path $env:TEMP "nssm.zip"

        Write-Info "Downloading NSSM from $nssmUrl..."
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing

        # Extract NSSM
        Write-Info "Extracting NSSM..."
        Expand-Archive -Path $nssmZip -DestinationPath $env:TEMP -Force

        # Copy appropriate architecture
        $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        $nssmExeSource = Join-Path $env:TEMP "nssm-2.24\$arch\nssm.exe"
        Copy-Item -Path $nssmExeSource -Destination $nssmPath -Force

        # Cleanup
        Remove-Item -Path $nssmZip -Force
        Remove-Item -Path (Join-Path $env:TEMP "nssm-2.24") -Recurse -Force

        Write-Success "NSSM downloaded and installed"
    } catch {
        Write-Error "Failed to download NSSM: $_"
        Write-Info "Please manually download NSSM from https://nssm.cc/ and place nssm.exe in: $nssmDir"
        exit 1
    }
}

# Install Windows Service
Write-Info "Installing Windows Service..."
$appPath = Join-Path $InstallPath "app\npu_worker.py"
$logPath = Join-Path $InstallPath "logs\service.log"

# Remove service if exists
& $nssmPath stop AutoBotNPUWorker 2>&1 | Out-Null
& $nssmPath remove AutoBotNPUWorker confirm 2>&1 | Out-Null

# Install service
& $nssmPath install AutoBotNPUWorker $pythonExe $appPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install service"
    exit 1
}

# Configure service
& $nssmPath set AutoBotNPUWorker DisplayName "AutoBot NPU Worker (Windows)"
& $nssmPath set AutoBotNPUWorker Description "AutoBot optional NPU worker for hardware-accelerated AI processing"
& $nssmPath set AutoBotNPUWorker Start SERVICE_AUTO_START
& $nssmPath set AutoBotNPUWorker AppStdout $logPath
& $nssmPath set AutoBotNPUWorker AppStderr $logPath
& $nssmPath set AutoBotNPUWorker AppDirectory $InstallPath
& $nssmPath set AutoBotNPUWorker AppRestartDelay 60000  # 60 seconds

# Set restart on failure
& $nssmPath set AutoBotNPUWorker AppExit Default Restart
& $nssmPath set AutoBotNPUWorker AppThrottle 10000  # 10 seconds

Write-Success "Windows Service installed"

# Start service if not disabled
if (-not $NoAutoStart) {
    Write-Info "Starting AutoBot NPU Worker service..."
    Start-Service -Name AutoBotNPUWorker
    Start-Sleep -Seconds 3

    $service = Get-Service -Name AutoBotNPUWorker
    if ($service.Status -eq "Running") {
        Write-Success "Service started successfully"
    } else {
        Write-Warning "Service failed to start (Status: $($service.Status))"
        Write-Info "Check logs: $logPath"
    }
}

# Health check
Write-Info "Performing health check..."
Start-Sleep -Seconds 5  # Give service time to fully initialize

try {
    $healthUrl = "http://localhost:8082/health"
    $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10

    Write-Success "Health check PASSED"
    Write-Host "  Worker ID: $($response.worker_id)"
    Write-Host "  NPU Available: $($response.npu_available)"
    Write-Host "  Status: $($response.status)"
} catch {
    Write-Warning "Health check failed: $_"
    Write-Info "The service may need more time to initialize"
    Write-Info "Check health manually: curl http://localhost:8082/health"
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Info "Installation directory: $InstallPath"
Write-Info "Service name: AutoBotNPUWorker"
Write-Info "Service port: 8082"
Write-Info "Health endpoint: http://localhost:8082/health"
Write-Host ""
Write-Info "Management commands:"
Write-Host "  Start:   .\scripts\start-service.ps1"
Write-Host "  Stop:    .\scripts\stop-service.ps1"
Write-Host "  Restart: .\scripts\restart-service.ps1"
Write-Host "  Status:  .\scripts\check-health.ps1"
Write-Host "  Logs:    .\scripts\view-logs.ps1"
Write-Host ""
Write-Info "For help, see README.md"
Write-Host ""
