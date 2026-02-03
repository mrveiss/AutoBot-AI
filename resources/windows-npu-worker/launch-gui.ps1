# AutoBot NPU Worker GUI Launcher (PowerShell)
# Starts the PySide6 GUI application with dependency checks

param(
    [switch]$Debug,
    [switch]$InstallDeps
)

Write-Host "AutoBot NPU Worker GUI Launcher" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Check if venv exists
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "ERROR: Python virtual environment not found." -ForegroundColor Red
    Write-Host "Please run install.ps1 first to set up the NPU worker." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if GUI requirements are installed
Write-Host "Checking GUI dependencies..." -ForegroundColor Yellow

$pyside6Installed = & "venv\Scripts\python.exe" -c "import PySide6; print('installed')" 2>$null

if (-not $pyside6Installed -or $InstallDeps) {
    Write-Host "Installing GUI dependencies..." -ForegroundColor Yellow
    & "venv\Scripts\pip.exe" install -r requirements-gui.txt

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install GUI dependencies." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host "GUI dependencies installed successfully." -ForegroundColor Green
}

# Launch GUI
Write-Host "Launching AutoBot NPU Worker GUI..." -ForegroundColor Green

if ($Debug) {
    # Debug mode: show console output
    & "venv\Scripts\python.exe" "gui\main.py"
} else {
    # Normal mode: no console window
    Start-Process -FilePath "venv\Scripts\pythonw.exe" -ArgumentList "gui\main.py" -WindowStyle Hidden
    Write-Host "GUI launched successfully!" -ForegroundColor Green
    Write-Host "Check system tray for the NPU Worker icon." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Start-Sleep -Seconds 2
