# AutoBot NPU Worker - Windows Installation Script
# Run as Administrator
#
# Issue #640: Updated to use ONNX Runtime + DirectML for stable NPU/GPU inference
# Replaces raw OpenVINO which had silent crash issues on NPU

#Requires -RunAsAdministrator

param(
    [switch]$SkipPythonCheck,
    [switch]$SkipFirewall,
    [switch]$NoAutoStart,
    [switch]$Uninstall,
    [switch]$KeepData,
    [switch]$KeepLogs,
    [switch]$Force,
    [string]$InstallPath = "C:\AutoBot\NPU"
)

# Handle uninstall mode - delegate to uninstall.ps1
if ($Uninstall) {
    $uninstallScript = Join-Path $PSScriptRoot "uninstall.ps1"
    if (Test-Path $uninstallScript) {
        $uninstallArgs = @()
        if ($KeepData) { $uninstallArgs += "-KeepData" }
        if ($KeepLogs) { $uninstallArgs += "-KeepLogs" }
        if ($Force) { $uninstallArgs += "-Force" }
        $uninstallArgs += "-InstallPath"
        $uninstallArgs += $InstallPath
        & $uninstallScript @uninstallArgs
        exit $LASTEXITCODE
    } else {
        Write-Host "Uninstall script not found: $uninstallScript" -ForegroundColor Red
        exit 1
    }
}

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
$scriptRoot = Split-Path -Parent $PSScriptRoot  # Get parent of scripts directory

# Determine source directory (either current location or script's parent)
if (Test-Path (Join-Path $currentPath "app\npu_worker.py")) {
    $sourceDir = $currentPath
} elseif (Test-Path (Join-Path $scriptRoot "app\npu_worker.py")) {
    $sourceDir = $scriptRoot
} else {
    Write-Error "Cannot find NPU worker source files"
    Write-Info "Run this script from the NPU worker package directory"
    exit 1
}

if ($sourceDir -ne $InstallPath) {
    Write-Info "Copying files from $sourceDir to $InstallPath..."

    # Copy specific directories and files to avoid permission issues with symlinks
    $itemsToCopy = @("app", "config", "gui", "installer", "nssm", "scripts", "tests",
                     "requirements.txt", "README.md", "INSTALLATION.md", "QUICK_START.md",
                     "DEPLOYMENT_SUMMARY.md", "BUILDING.md", "LICENSE.txt",
                     "launch-gui.bat", "launch-gui.ps1")

    foreach ($item in $itemsToCopy) {
        $sourcePath = Join-Path $sourceDir $item
        if (Test-Path $sourcePath) {
            try {
                Copy-Item -Path $sourcePath -Destination $InstallPath -Recurse -Force -ErrorAction Stop
            } catch {
                Write-Warning "Could not copy $item : $_"
            }
        }
    }

    # Create empty directories if they don't exist
    $emptyDirs = @("logs", "models", "data")
    foreach ($dir in $emptyDirs) {
        $dirPath = Join-Path $InstallPath $dir
        if (-not (Test-Path $dirPath)) {
            New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
        }
    }

    Set-Location $InstallPath
    Write-Success "Files copied to installation directory"
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

# Verify PyTorch installation (required for model downloading and ONNX export)
Write-Info "Verifying PyTorch installation..."
$torchCheck = & $pythonExe -c "import torch; print(f'PyTorch {torch.__version__}')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "$torchCheck"
} else {
    Write-Warning "PyTorch verification failed - model downloading may not work"
    Write-Info "Try: pip install torch --index-url https://download.pytorch.org/whl/cpu"
}

# Verify sentence-transformers installation
Write-Info "Verifying sentence-transformers installation..."
$stCheck = & $pythonExe -c "import sentence_transformers; print(f'sentence-transformers {sentence_transformers.__version__}')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "$stCheck"
} else {
    Write-Warning "sentence-transformers verification failed - embedding models may not work"
}

# Verify ONNX Runtime installation (Issue #640: Uses OpenVINO EP for Intel NPU)
Write-Info "Verifying ONNX Runtime OpenVINO installation..."
$onnxCheck = & $pythonExe -c "import onnxruntime as ort; print(f'ONNX Runtime {ort.__version__}')" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Success "$onnxCheck"

    # Check available providers
    $providers = & $pythonExe -c "import onnxruntime as ort; print(', '.join(ort.get_available_providers()))" 2>&1
    Write-Info "Available providers: $providers"

    if ($providers -match "OpenVINOExecutionProvider") {
        Write-Success "OpenVINO Execution Provider available!"

        # Check for NPU device via OpenVINO Core
        try {
            $devices = & $pythonExe -c "from openvino import Core; print(', '.join(Core().available_devices))" 2>&1
            if ($LASTEXITCODE -eq 0 -and $devices -notmatch "Traceback") {
                Write-Info "OpenVINO devices: $devices"
                if ($devices -match "NPU") {
                    Write-Success "Intel NPU detected - NPU acceleration enabled!"
                } elseif ($devices -match "GPU") {
                    Write-Success "Intel GPU detected - GPU acceleration enabled"
                } else {
                    Write-Warning "No NPU/GPU detected in device list - will use CPU"
                }
            } else {
                Write-Info "OpenVINO device enumeration not available (EP will auto-select device)"
                Write-Info "OpenVINO EP will automatically use best available device: NPU > GPU > CPU"
            }
        } catch {
            Write-Info "OpenVINO device check skipped (EP will auto-select device)"
        }
    } elseif ($providers -match "DmlExecutionProvider") {
        Write-Warning "DirectML available (GPU only, Intel NPU not exposed via DirectML)"
        Write-Info "For full NPU support, ensure onnxruntime-openvino is installed"
    } else {
        Write-Warning "No acceleration providers available - will use CPU only"
        Write-Info "For NPU acceleration, ensure Windows 11 24H2+ and Intel AI Boost drivers"
    }
} else {
    Write-Warning "ONNX Runtime verification failed (may work in service mode)"
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

# Setup NSSM (bundled with installation package)
$arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
$nssmDir = Join-Path $InstallPath "nssm"
$nssmPath = Join-Path $nssmDir "nssm.exe"

# Check if NSSM is already in place
if (-not (Test-Path $nssmPath)) {
    Write-Info "Setting up NSSM (bundled)..."

    # NSSM is bundled in the installation package under nssm/win64 or nssm/win32
    $bundledNssmPath = Join-Path $InstallPath "nssm\$arch\nssm.exe"

    if (Test-Path $bundledNssmPath) {
        # Copy from bundled location to main nssm directory
        Copy-Item -Path $bundledNssmPath -Destination $nssmPath -Force
        Write-Success "NSSM configured from bundled package"
    } else {
        Write-Error "NSSM not found in bundled package at: $bundledNssmPath"
        Write-Info "The installation package appears to be incomplete."
        Write-Info "Please re-download the full NPU Worker package."
        exit 1
    }
} else {
    Write-Success "NSSM already configured"
}

# Install Windows Service
Write-Info "Installing Windows Service..."
$appPath = Join-Path $InstallPath "app\npu_worker.py"
$logPath = Join-Path $InstallPath "logs\service.log"

# Remove existing service if present (ignore errors if service doesn't exist)
Write-Info "  Checking for existing service..."
try {
    $existingService = Get-Service -Name "AutoBotNPUWorker" -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Info "  Removing existing service..."
        & $nssmPath stop AutoBotNPUWorker 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        & $nssmPath remove AutoBotNPUWorker confirm 2>&1 | Out-Null
        Start-Sleep -Seconds 1
    }
} catch {
    # Service doesn't exist, that's fine for fresh install
}

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
