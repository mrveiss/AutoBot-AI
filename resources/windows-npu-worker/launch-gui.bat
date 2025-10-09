@echo off
REM AutoBot NPU Worker GUI Launcher
REM Starts the PySide6 GUI application

echo Starting AutoBot NPU Worker GUI...

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    echo Please run install.ps1 first to set up the NPU worker.
    pause
    exit /b 1
)

REM Check if GUI requirements are installed
venv\Scripts\python.exe -c "import PySide6" 2>nul
if errorlevel 1 (
    echo Installing GUI dependencies...
    venv\Scripts\pip.exe install -r requirements-gui.txt
    if errorlevel 1 (
        echo ERROR: Failed to install GUI dependencies.
        pause
        exit /b 1
    )
)

REM Launch GUI (pythonw.exe for no console window)
start "" venv\Scripts\pythonw.exe gui\main.py

echo GUI launched successfully.
timeout /t 2 /nobreak >nul
