# AutoBot NPU Worker - Build Instructions

Complete guide for building the Windows NPU Worker installer from source.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Build](#quick-build)
- [Detailed Build Process](#detailed-build-process)
- [Build Options](#build-options)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

1. **Python 3.10+**
   - Download: https://www.python.org/downloads/
   - Ensure "Add Python to PATH" is checked during installation
   - Verify: `python --version`

2. **PyInstaller**
   - Will be installed automatically by build script
   - Manual install: `pip install pyinstaller`
   - Verify: `pyinstaller --version`

3. **Inno Setup 6**
   - Download: https://jrsoftware.org/isdl.php
   - Install to default location: `C:\Program Files (x86)\Inno Setup 6\`
   - Verify: Check `ISCC.exe` exists at above path

4. **Git** (optional, for development)
   - Download: https://git-scm.com/downloads
   - Used for cloning repository and version control

### System Requirements

- Windows 10/11 (64-bit)
- 4GB RAM minimum (8GB recommended for faster builds)
- 5GB free disk space (for build artifacts and dependencies)
- Administrator rights (for building installer)
- Internet connection (for downloading dependencies)

---

## Quick Build

### One-Command Build

```powershell
# Navigate to installer directory
cd deployment\windows-npu-worker\installer

# Run build script with all steps
.\build.ps1
```

This performs:
1. ✅ Prerequisite validation
2. ✅ Dependency installation
3. ✅ PyInstaller executable build
4. ✅ Inno Setup installer creation
5. ✅ Final package assembly

**Build Time:** 10-15 minutes (first build)

### Output

Build creates:
```
installer/output/
└── AutoBot-NPU-Worker-Setup-1.0.0.exe  (~100-150 MB)
```

---

## Detailed Build Process

### Step 1: Prepare Build Environment

```powershell
# Clone repository (if not already done)
git clone https://github.com/autobot/autobot.git
cd autobot/deployment/windows-npu-worker

# Create clean build environment
.\installer\build.ps1 -Clean
```

### Step 2: Install Dependencies

```powershell
# Install all required Python packages
pip install -r requirements.txt

# Install PyInstaller specifically
pip install pyinstaller --upgrade
```

**Key Dependencies:**
- `fastapi>=0.104.0` - Web framework
- `uvicorn[standard]>=0.24.0` - ASGI server
- `openvino>=2023.2.0` - NPU acceleration
- `openvino-dev>=2023.2.0` - OpenVINO development tools
- `numpy>=1.24.0` - Scientific computing
- `scikit-learn>=1.3.0` - Machine learning utilities
- `redis>=5.0.0` - Redis client
- `pydantic>=2.5.0` - Data validation
- `pyyaml>=6.0.1` - YAML configuration

### Step 3: Build Executable with PyInstaller

```powershell
# Build using spec file
pyinstaller installer\npu_worker.spec --noconfirm --clean
```

**What happens:**
1. Analyzes `app/npu_worker.py` and dependencies
2. Collects OpenVINO libraries and binaries
3. Bundles FastAPI, Uvicorn, and all runtime dependencies
4. Creates standalone executable in `dist/AutoBotNPUWorker/`

**PyInstaller Spec File Highlights:**
```python
# Hidden imports for proper bundling
hiddenimports = [
    'openvino', 'openvino.runtime',
    'fastapi', 'uvicorn',
    'numpy', 'sklearn',
    # ... and more
]

# Data files to include
datas = [
    ('config/*.yaml', 'config'),
    # OpenVINO data files
    # FastAPI templates
]

# Binaries to include
binaries = [
    # OpenVINO DLLs
    # System libraries
]
```

**Output Structure:**
```
dist/AutoBotNPUWorker/
├── AutoBotNPUWorker.exe    # Main executable
├── config/                 # Configuration files
├── _internal/              # Dependencies and DLLs
│   ├── openvino/          # OpenVINO libraries
│   ├── numpy/             # NumPy binaries
│   └── ...                # Other dependencies
└── ...
```

### Step 4: Create Windows Installer

```powershell
# Build installer with Inno Setup
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\installer.iss /O"installer\output"
```

**Inno Setup Configuration:**

**[Setup] Section:**
- Application metadata (name, version, publisher)
- Installation paths and registry keys
- Compression: LZMA2/max for smallest size
- Wizard style: Modern UI
- Architecture: x64 only

**[Files] Section:**
- Bundles PyInstaller output
- Includes configuration templates
- Adds PowerShell management scripts
- Packages documentation

**[Run] Section:**
- Downloads NSSM service manager
- Installs VC++ redistributables
- Configures Windows Firewall
- Registers and starts Windows service

**[Code] Section (Pascal scripting):**
- Custom data directory handling
- Service installation logic
- Uninstall confirmation dialogs

### Step 5: Verify Build

```powershell
# Check output
Get-ChildItem installer\output\

# Should show:
# AutoBot-NPU-Worker-Setup-1.0.0.exe
```

**Verify installer integrity:**
```powershell
# Check file size (should be 100-150 MB)
(Get-Item installer\output\AutoBot-NPU-Worker-Setup-1.0.0.exe).Length / 1MB

# Test installer on clean VM (recommended)
```

---

## Build Options

### Clean Build

Remove all build artifacts before building:
```powershell
.\installer\build.ps1 -Clean
```

Removes:
- `dist/` - PyInstaller output
- `build/` - PyInstaller cache
- `installer/output/` - Previous installers

### Skip Dependency Installation

Use existing dependencies (faster rebuilds):
```powershell
.\installer\build.ps1 -SkipDependencies
```

### Skip PyInstaller

Use existing executable (only rebuild installer):
```powershell
.\installer\build.ps1 -SkipPyInstaller
```

### Skip Inno Setup

Only build executable (no installer):
```powershell
.\installer\build.ps1 -SkipInnoSetup
```

### Custom Output Directory

Specify output location:
```powershell
.\installer\build.ps1 -OutputDir "C:\Builds\AutoBot"
```

### Combined Options

```powershell
# Clean build, skip dependencies, custom output
.\installer\build.ps1 -Clean -SkipDependencies -OutputDir "C:\Release"
```

---

## Customization

### Modify Application Icon

1. Create/replace `installer/assets/icon.ico`
2. Rebuild installer:
   ```powershell
   .\installer\build.ps1 -SkipPyInstaller
   ```

### Change Version Number

Edit version in multiple files:

**1. Build script (`installer/build.ps1`):**
```powershell
$BuildVersion = "1.1.0"  # Update here
```

**2. Inno Setup script (`installer/installer.iss`):**
```iss
#define MyAppVersion "1.1.0"  ; Update here
```

**3. Configuration (`config/npu_worker.yaml`):**
```yaml
# Update version in comments/metadata
```

### Add Custom Dependencies

**1. Update requirements.txt:**
```
# Add new package
your-package>=1.0.0
```

**2. Update PyInstaller spec:**
```python
# In installer/npu_worker.spec
hidden_imports = [
    'your_package',
    # ... existing imports
]
```

**3. Rebuild:**
```powershell
.\installer\build.ps1 -Clean
```

### Modify Service Configuration

Edit Inno Setup script (`installer/installer.iss`):

```iss
[Run]
; Customize service settings
Filename: "{app}\nssm\nssm.exe"; Parameters: "set {#MyServiceName} Start SERVICE_DEMAND_START"; Flags: runhidden; Tasks: installservice
; Change to manual start instead of automatic
```

### Bundle Python Interpreter

To include embedded Python (larger package, no external Python needed):

**1. Download Python embedded:**
```powershell
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip" -OutFile "python-embed.zip"
Expand-Archive python-embed.zip -DestinationPath installer\resources\python-embed\
```

**2. Update Inno Setup script:**
```iss
[Files]
Source: ".\resources\python-embed\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
```

**3. Update service configuration to use bundled Python**

---

## Troubleshooting

### Build Errors

#### PyInstaller Import Errors

**Error:** `ModuleNotFoundError: No module named 'X'`

**Solution:**
1. Install missing module:
   ```powershell
   pip install X
   ```

2. Add to hidden imports in `npu_worker.spec`:
   ```python
   hiddenimports = [
       'X',
       # ... existing
   ]
   ```

3. Rebuild:
   ```powershell
   .\installer\build.ps1 -Clean
   ```

#### OpenVINO Bundling Issues

**Error:** OpenVINO libraries not found

**Solution:**
1. Verify OpenVINO installation:
   ```powershell
   python -c "import openvino; print(openvino.__version__)"
   ```

2. Manually collect OpenVINO files:
   ```python
   # In npu_worker.spec
   from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
   openvino_datas = collect_data_files('openvino')
   openvino_binaries = collect_dynamic_libs('openvino')
   ```

3. Check PyInstaller warnings for missing files

#### Large Executable Size

**Issue:** Executable > 500 MB

**Solutions:**
1. Enable UPX compression:
   ```python
   # In npu_worker.spec
   exe = EXE(..., upx=True, ...)
   ```

2. Exclude unnecessary packages:
   ```python
   excludes = ['matplotlib', 'tkinter', 'IPython', 'jupyter']
   ```

3. Use `--onefile` for single executable (slower startup)

### Installer Build Errors

#### Inno Setup Compiler Errors

**Error:** Cannot find ISCC.exe

**Solution:**
1. Verify Inno Setup installation:
   ```powershell
   Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
   ```

2. Reinstall Inno Setup from official site
3. Update path in build script if custom location

#### File Not Found Errors

**Error:** Source file not found

**Solution:**
1. Verify PyInstaller output exists:
   ```powershell
   Test-Path dist\AutoBotNPUWorker\AutoBotNPUWorker.exe
   ```

2. Rebuild with PyInstaller:
   ```powershell
   .\installer\build.ps1 -Clean
   ```

3. Check file paths in `installer.iss` are correct

### Runtime Issues

#### Missing DLL Errors

**Error:** Application fails to start, missing DLL

**Solution:**
1. Identify missing DLL from error message
2. Add to PyInstaller spec binaries:
   ```python
   binaries = [
       ('C:\\path\\to\\missing.dll', '.'),
       # ... existing
   ]
   ```

3. Rebuild and test

#### Service Won't Install

**Error:** NSSM service installation fails

**Solution:**
1. Verify NSSM downloaded:
   ```powershell
   Test-Path installer\resources\nssm\nssm.exe
   ```

2. Download manually if missing:
   ```powershell
   Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "nssm.zip"
   ```

3. Rebuild installer

---

## Advanced Topics

### Signing the Installer

For production releases, sign the installer:

```powershell
# Sign with code signing certificate
signtool sign /f "certificate.pfx" /p "password" /t http://timestamp.digicert.com "installer\output\AutoBot-NPU-Worker-Setup-1.0.0.exe"
```

### Automated Builds

Create CI/CD pipeline:

```yaml
# GitHub Actions example
name: Build Installer
on: [push]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install Inno Setup
        run: choco install innosetup
      - name: Build
        run: .\deployment\windows-npu-worker\installer\build.ps1
      - uses: actions/upload-artifact@v3
        with:
          name: installer
          path: deployment/windows-npu-worker/installer/output/*.exe
```

### Creating MSI Package

Alternative to Inno Setup, use WiX Toolset for MSI:

1. Install WiX: https://wixtoolset.org/
2. Create WiX configuration (.wxs)
3. Build MSI: `candle.exe config.wxs && light.exe config.wixobj`

---

## Build Checklist

Before releasing:

- [ ] Updated version numbers in all files
- [ ] Tested PyInstaller build on clean system
- [ ] Verified all dependencies bundled correctly
- [ ] Tested installer on Windows 10 and 11
- [ ] Verified service installation works
- [ ] Checked health endpoint responds
- [ ] Confirmed NPU detection (on supported hardware)
- [ ] Tested uninstaller preserves data option
- [ ] Reviewed and updated documentation
- [ ] Signed installer (for production)

---

## Additional Resources

- **PyInstaller Documentation**: https://pyinstaller.org/en/stable/
- **Inno Setup Documentation**: https://jrsoftware.org/ishelp/
- **NSSM Documentation**: https://nssm.cc/usage
- **OpenVINO Documentation**: https://docs.openvino.ai/

---

**Happy Building! 🔨**

For questions or issues, refer to the main AutoBot documentation or create an issue in the repository.
