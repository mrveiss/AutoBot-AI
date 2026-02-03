<#
.SYNOPSIS
    AutoBot NPU Worker - Build Automation Script

.DESCRIPTION
    Automates the complete build process:
    1. Validates prerequisites (Python, PyInstaller, Inno Setup)
    2. Installs dependencies
    3. Builds executable with PyInstaller
    4. Creates Windows installer with Inno Setup
    5. Packages final distribution

.PARAMETER Clean
    Clean build directories before building

.PARAMETER SkipDependencies
    Skip dependency installation

.PARAMETER SkipPyInstaller
    Skip PyInstaller build (use existing dist)

.PARAMETER SkipInnoSetup
    Skip Inno Setup installer creation

.PARAMETER OutputDir
    Override output directory for final installer

.EXAMPLE
    .\build.ps1
    Full build with all steps

.EXAMPLE
    .\build.ps1 -Clean
    Clean build from scratch

.EXAMPLE
    .\build.ps1 -SkipDependencies
    Build without reinstalling dependencies
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipDependencies,
    [switch]$SkipPyInstaller,
    [switch]$SkipInnoSetup,
    [string]$OutputDir = ".\output"
)

# Script configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Paths
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$InstallerDir = $ScriptRoot
$SpecFile = Join-Path $InstallerDir "npu_worker.spec"
$IssFile = Join-Path $InstallerDir "installer.iss"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

# Build info
$BuildVersion = "1.0.0"
$BuildDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AutoBot NPU Worker - Build Script" -ForegroundColor Cyan
Write-Host "Version: $BuildVersion" -ForegroundColor Cyan
Write-Host "Build Date: $BuildDate" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Prerequisites check
Write-Host "[1/7] Checking prerequisites..." -ForegroundColor Yellow

# Check Python
Write-Host "  - Checking Python..." -NoNewline
try {
    $pythonVersion = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK ($pythonVersion)" -ForegroundColor Green
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "Error: Python 3.10+ is required. Please install from https://www.python.org/" -ForegroundColor Red
    exit 1
}

# Check pip
Write-Host "  - Checking pip..." -NoNewline
try {
    $pipVersion = & python -m pip --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        throw "pip not found"
    }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "Error: pip is required. Please ensure Python is properly installed." -ForegroundColor Red
    exit 1
}

# Check PyInstaller
if (-not $SkipPyInstaller) {
    Write-Host "  - Checking PyInstaller..." -NoNewline
    try {
        $pyinstallerVersion = & python -m PyInstaller --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK (v$pyinstallerVersion)" -ForegroundColor Green
        } else {
            Write-Host " NOT FOUND - will install" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " NOT FOUND - will install" -ForegroundColor Yellow
    }
}

# Check Inno Setup
if (-not $SkipInnoSetup) {
    Write-Host "  - Checking Inno Setup..." -NoNewline
    $innoSetupPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $innoSetupPath) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " NOT FOUND" -ForegroundColor Red
        Write-Host "Error: Inno Setup 6 is required. Please install from https://jrsoftware.org/isinfo.php" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# Step 2: Clean build directories
if ($Clean) {
    Write-Host "[2/7] Cleaning build directories..." -ForegroundColor Yellow

    if (Test-Path $DistDir) {
        Write-Host "  - Removing $DistDir..." -NoNewline
        Remove-Item -Path $DistDir -Recurse -Force
        Write-Host " OK" -ForegroundColor Green
    }

    if (Test-Path $BuildDir) {
        Write-Host "  - Removing $BuildDir..." -NoNewline
        Remove-Item -Path $BuildDir -Recurse -Force
        Write-Host " OK" -ForegroundColor Green
    }

    if (Test-Path $OutputDir) {
        Write-Host "  - Removing $OutputDir..." -NoNewline
        Remove-Item -Path $OutputDir -Recurse -Force
        Write-Host " OK" -ForegroundColor Green
    }

    Write-Host ""
} else {
    Write-Host "[2/7] Skipping clean (use -Clean to clean build directories)" -ForegroundColor Gray
    Write-Host ""
}

# Step 3: Install dependencies
if (-not $SkipDependencies) {
    Write-Host "[3/7] Installing dependencies..." -ForegroundColor Yellow

    Write-Host "  - Installing PyInstaller..." -NoNewline
    & python -m pip install pyinstaller --upgrade --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        exit 1
    }

    Write-Host "  - Installing application dependencies..." -NoNewline
    if (Test-Path $RequirementsFile) {
        & python -m pip install -r $RequirementsFile --upgrade --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK" -ForegroundColor Green
        } else {
            Write-Host " FAILED" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host " SKIPPED (requirements.txt not found)" -ForegroundColor Yellow
    }

    Write-Host ""
} else {
    Write-Host "[3/7] Skipping dependency installation (use without -SkipDependencies to install)" -ForegroundColor Gray
    Write-Host ""
}

# Step 4: Build with PyInstaller
if (-not $SkipPyInstaller) {
    Write-Host "[4/7] Building executable with PyInstaller..." -ForegroundColor Yellow

    if (-not (Test-Path $SpecFile)) {
        Write-Host "Error: Spec file not found at $SpecFile" -ForegroundColor Red
        exit 1
    }

    Write-Host "  - Running PyInstaller..." -NoNewline
    $pyinstallerOutput = & python -m PyInstaller $SpecFile --noconfirm --clean 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green

        # Verify output
        $exePath = Join-Path $DistDir "AutoBotNPUWorker\AutoBotNPUWorker.exe"
        if (Test-Path $exePath) {
            $exeSize = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
            Write-Host "  - Executable created: $exeSize MB" -ForegroundColor Green
        } else {
            Write-Host "  - Warning: Executable not found at expected location" -ForegroundColor Yellow
        }
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "PyInstaller output:" -ForegroundColor Red
        Write-Host $pyinstallerOutput -ForegroundColor Red
        exit 1
    }

    Write-Host ""
} else {
    Write-Host "[4/7] Skipping PyInstaller build (use without -SkipPyInstaller to build)" -ForegroundColor Gray
    Write-Host ""
}

# Step 5: Prepare installer resources
Write-Host "[5/7] Preparing installer resources..." -ForegroundColor Yellow

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "  - Created output directory: $OutputDir" -ForegroundColor Green
}

# Download NSSM if not present
$nssmDir = Join-Path $InstallerDir "resources\nssm"
$nssmExe = Join-Path $nssmDir "nssm.exe"

if (-not (Test-Path $nssmExe)) {
    Write-Host "  - Downloading NSSM..." -NoNewline
    New-Item -ItemType Directory -Path $nssmDir -Force | Out-Null

    try {
        $nssmZip = Join-Path $env:TEMP "nssm.zip"
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $nssmZip
        Expand-Archive -Path $nssmZip -DestinationPath (Join-Path $env:TEMP "nssm") -Force
        Copy-Item -Path (Join-Path $env:TEMP "nssm\nssm-2.24\win64\nssm.exe") -Destination $nssmExe -Force
        Remove-Item -Path $nssmZip -Force
        Remove-Item -Path (Join-Path $env:TEMP "nssm") -Recurse -Force
        Write-Host " OK" -ForegroundColor Green
    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "Error downloading NSSM: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  - NSSM already present" -ForegroundColor Green
}

Write-Host ""

# Step 6: Create installer with Inno Setup
if (-not $SkipInnoSetup) {
    Write-Host "[6/7] Creating Windows installer with Inno Setup..." -ForegroundColor Yellow

    if (-not (Test-Path $IssFile)) {
        Write-Host "Error: Inno Setup script not found at $IssFile" -ForegroundColor Red
        exit 1
    }

    Write-Host "  - Compiling installer..." -NoNewline
    $innoSetupOutput = & $innoSetupPath $IssFile "/O$OutputDir" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green

        # Find the created installer
        $installerFiles = Get-ChildItem -Path $OutputDir -Filter "AutoBot-NPU-Worker-Setup-*.exe"
        if ($installerFiles.Count -gt 0) {
            $installerSize = [math]::Round($installerFiles[0].Length / 1MB, 2)
            Write-Host "  - Installer created: $($installerFiles[0].Name) ($installerSize MB)" -ForegroundColor Green
        }
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "Inno Setup output:" -ForegroundColor Red
        Write-Host $innoSetupOutput -ForegroundColor Red
        exit 1
    }

    Write-Host ""
} else {
    Write-Host "[6/7] Skipping Inno Setup installer creation (use without -SkipInnoSetup to create)" -ForegroundColor Gray
    Write-Host ""
}

# Step 7: Build summary
Write-Host "[7/7] Build Summary" -ForegroundColor Yellow
Write-Host "  - Build version: $BuildVersion" -ForegroundColor White
Write-Host "  - Build date: $BuildDate" -ForegroundColor White

if (Test-Path $OutputDir) {
    $outputFiles = Get-ChildItem -Path $OutputDir -Recurse
    $totalSize = [math]::Round(($outputFiles | Measure-Object -Property Length -Sum).Sum / 1MB, 2)
    Write-Host "  - Output directory: $OutputDir" -ForegroundColor White
    Write-Host "  - Total output size: $totalSize MB" -ForegroundColor White
    Write-Host "  - Files created:" -ForegroundColor White
    $outputFiles | ForEach-Object {
        $fileSize = [math]::Round($_.Length / 1MB, 2)
        Write-Host "    - $($_.Name) ($fileSize MB)" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Test the installer on a clean Windows system" -ForegroundColor White
Write-Host "2. Verify service installation and startup" -ForegroundColor White
Write-Host "3. Check health endpoint: http://localhost:8082/health" -ForegroundColor White
Write-Host "4. Review logs in: C:\Program Files\AutoBot\NPU\logs" -ForegroundColor White
Write-Host ""
