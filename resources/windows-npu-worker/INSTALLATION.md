# AutoBot NPU Worker - Installation Guide

Complete step-by-step installation guide for the AutoBot NPU Worker on Windows systems.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
  - [Method 1: Installer Package (Recommended)](#method-1-installer-package-recommended)
  - [Method 2: Manual Installation (Advanced)](#method-2-manual-installation-advanced)
- [Post-Installation](#post-installation)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **Operating System**: Windows 10 (64-bit) or Windows 11
- **Processor**: Intel CPU with NPU support (Core Ultra series or newer recommended)
- **RAM**: Minimum 8GB, Recommended 16GB
- **Disk Space**: 2GB for installation + additional space for models
- **Permissions**: Administrator rights for installation

### Network Requirements

- Access to AutoBot backend server (172.16.168.20:8001)
- Access to Redis server (172.16.168.23:6379)
- Port 8082 available for NPU worker service
- Internet access during installation (for downloading dependencies)

### Software Requirements

- ✅ **Automatically Installed by Installer Package:**
  - Python 3.10+ (embedded)
  - Visual C++ Redistributables
  - NSSM Service Manager
  - All Python dependencies

- ⚠️ **For Manual Installation:**
  - Python 3.10 or higher
  - Git (optional, for development)

---

## Installation Methods

### Method 1: Installer Package (Recommended)

The installer package provides a professional Windows installation experience with automatic configuration.

#### Step 1: Download Installer

Download the latest installer:
```
AutoBot-NPU-Worker-Setup-1.0.0.exe
```

#### Step 2: Run Installer

1. **Launch installer** by double-clicking `AutoBot-NPU-Worker-Setup-1.0.0.exe`
2. **Windows SmartScreen** may appear:
   - Click "More info"
   - Click "Run anyway"

#### Step 3: Installation Wizard

1. **Welcome Screen**
   - Read the welcome message
   - Click "Next"

2. **License Agreement**
   - Review the license terms
   - Accept and click "Next"

3. **Installation Location**
   - Default: `C:\Program Files\AutoBot\NPU\`
   - Change if needed
   - Click "Next"

4. **Select Components** (all recommended):
   - ✅ Install as Windows Service
   - ✅ Start service automatically at Windows startup
   - ✅ Configure Windows Firewall
   - ✅ Desktop icon (optional)
   - Click "Next"

5. **Ready to Install**
   - Review settings
   - Click "Install"

#### Step 4: Installation Progress

The installer will:
1. Copy application files
2. Install Visual C++ Redistributables (if needed)
3. Download and configure NSSM service manager
4. Configure Windows Firewall rule
5. Install and start Windows service
6. Create shortcuts

#### Step 5: Completion

1. ✅ Check "Open README file" to view documentation
2. ✅ Check "Check NPU Worker Health" to verify installation
3. Click "Finish"

**Installation Time:** 5-10 minutes (depending on internet speed)

---

### Method 2: Manual Installation (Advanced)

For advanced users who prefer manual configuration.

#### Step 1: Extract Package

Extract the deployment package to desired location:
```powershell
# Example: Extract to C:\AutoBot\NPU\
Expand-Archive -Path AutoBot-NPU-Worker.zip -DestinationPath C:\AutoBot\NPU\
cd C:\AutoBot\NPU
```

#### Step 2: Install Python (if not present)

1. Download Python 3.10+ from https://www.python.org/
2. Install with "Add Python to PATH" checked
3. Verify installation:
   ```powershell
   python --version
   ```

#### Step 3: Create Virtual Environment

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

#### Step 4: Install Dependencies

```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

This will install:
- FastAPI and Uvicorn (web framework)
- ONNX Runtime with DirectML (NPU/GPU acceleration)
- HuggingFace Transformers (model loading)
- Redis client
- NumPy, scikit-learn (scientific computing)
- Additional dependencies

**Installation time:** 3-7 minutes

#### Step 5: Configure Settings

Edit `config\npu_worker.yaml`:

```yaml
# Service Configuration
service:
  host: "0.0.0.0"
  port: 8082

# Backend Integration
backend:
  host: "172.16.168.20"
  port: 8001

# Redis Configuration
redis:
  host: "172.16.168.23"
  port: 6379
```

#### Step 6: Install as Windows Service (Optional)

```powershell
# Run installation script as Administrator
.\scripts\install.ps1
```

Or manually using NSSM:

```powershell
# Download NSSM
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\nssm.zip"
Expand-Archive -Path "$env:TEMP\nssm.zip" -DestinationPath "$env:TEMP\nssm"
Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" -Destination ".\nssm\"

# Install service
.\nssm\nssm.exe install AutoBotNPUWorker "C:\AutoBot\NPU\venv\Scripts\python.exe" "C:\AutoBot\NPU\app\npu_worker.py"
.\nssm\nssm.exe set AutoBotNPUWorker DisplayName "AutoBot NPU Worker (Windows)"
.\nssm\nssm.exe set AutoBotNPUWorker Start SERVICE_AUTO_START
.\nssm\nssm.exe start AutoBotNPUWorker
```

#### Step 7: Configure Firewall

```powershell
# Create firewall rule (as Administrator)
New-NetFirewallRule -DisplayName "AutoBot NPU Worker" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8082 `
  -Action Allow `
  -Profile Any
```

---

## Post-Installation

### 1. Verify Service Status

```powershell
# Check service status
Get-Service AutoBotNPUWorker

# Should show:
# Status   Name               DisplayName
# ------   ----               -----------
# Running  AutoBotNPUWorker   AutoBot NPU Worker (Windows)
```

### 2. Check Health Endpoint

Open browser or use curl:
```powershell
curl http://localhost:8082/health
```

Expected response:
```json
{
  "status": "healthy",
  "worker_id": "windows_npu_worker_abc12345",
  "platform": "windows",
  "port": 8082,
  "npu_available": true,
  "loaded_models": ["nomic-embed-text", "llama3.2:1b-instruct-q4_K_M"],
  "stats": { ... },
  "npu_metrics": { ... }
}
```

### 3. Review Logs

```powershell
# View service logs
Get-Content C:\Program Files\AutoBot\NPU\logs\service.log -Tail 50

# Or use the provided script
C:\Program Files\AutoBot\NPU\scripts\view-logs.ps1
```

### 4. Backend Integration

Verify worker registration with backend:
```powershell
curl http://172.16.168.20:8001/api/system/health
```

Look for Windows NPU worker in the response.

---

## Verification

### Quick Health Check

Use the provided health check script:
```powershell
C:\Program Files\AutoBot\NPU\scripts\check-health.ps1
```

This checks:
- ✅ Windows service status
- ✅ HTTP endpoint responsiveness
- ✅ NPU hardware detection
- ✅ Model loading capability
- ✅ Network connectivity (backend, Redis)
- ✅ Performance metrics

### Detailed Validation

1. **Service Status:**
   ```powershell
   Get-Service AutoBotNPUWorker | Format-List *
   ```

2. **Network Connectivity:**
   ```powershell
   Test-NetConnection -ComputerName 172.16.168.20 -Port 8001
   Test-NetConnection -ComputerName 172.16.168.23 -Port 6379
   ```

3. **NPU Detection (ONNX Runtime providers):**
   ```powershell
   C:\Program Files\AutoBot\NPU\venv\Scripts\python.exe -c "import onnxruntime as ort; print(ort.get_available_providers())"
   ```

4. **Performance Benchmark:**
   ```powershell
   curl http://localhost:8082/performance/benchmark
   ```

---

## Troubleshooting

### Installation Issues

#### Issue: Installer won't run
**Solution:**
- Right-click installer → Properties → Unblock → Apply
- Run as Administrator
- Disable antivirus temporarily

#### Issue: VC++ Redistributables fail to install
**Solution:**
- Download manually from: https://aka.ms/vs/17/release/vc_redist.x64.exe
- Install manually before running installer
- Reboot and retry

#### Issue: Firewall rule creation fails
**Solution:**
- Open PowerShell as Administrator
- Run manually:
  ```powershell
  New-NetFirewallRule -DisplayName "AutoBot NPU Worker" -Direction Inbound -Protocol TCP -LocalPort 8082 -Action Allow -Profile Any
  ```

### Service Issues

#### Issue: Service won't start
**Solution:**
1. Check logs:
   ```powershell
   Get-Content C:\Program Files\AutoBot\NPU\logs\service.log
   ```

2. Verify Python installation:
   ```powershell
   C:\Program Files\AutoBot\NPU\venv\Scripts\python.exe --version
   ```

3. Test manual startup:
   ```powershell
   C:\Program Files\AutoBot\NPU\venv\Scripts\python.exe C:\Program Files\AutoBot\NPU\app\npu_worker.py
   ```

#### Issue: NPU not detected

**Solution:**

1. Verify ONNX Runtime DirectML installation:
   ```powershell
   C:\Program Files\AutoBot\NPU\venv\Scripts\python.exe -c "import onnxruntime as ort; print(f'ONNX Runtime {ort.__version__}')"
   ```

2. Check available execution providers:
   ```powershell
   C:\Program Files\AutoBot\NPU\venv\Scripts\python.exe -c "import onnxruntime as ort; print(ort.get_available_providers())"
   ```

3. For DirectML NPU support, ensure Windows 11 24H2+ and Intel AI Boost drivers are installed

### Network Issues

#### Issue: Cannot connect to backend/Redis
**Solution:**
1. Check network connectivity:
   ```powershell
   Test-NetConnection -ComputerName 172.16.168.20 -Port 8001
   Test-NetConnection -ComputerName 172.16.168.23 -Port 6379
   ```

2. Verify firewall allows outbound connections
3. Check backend/Redis services are running
4. Verify configuration in `config\npu_worker.yaml`

#### Issue: Port 8082 already in use
**Solution:**
1. Find process using port:
   ```powershell
   netstat -ano | findstr :8082
   ```

2. Stop conflicting process or change port in `config\npu_worker.yaml`
3. Update firewall rule for new port
4. Restart service

### Performance Issues

#### Issue: High CPU/Memory usage
**Solution:**
1. Check loaded models:
   ```powershell
   curl http://localhost:8082/stats
   ```

2. Reduce batch size in `config\npu_worker.yaml`:
   ```yaml
   npu:
     optimization:
       batch_size: 16  # Reduce from 32
   ```

3. Restart service:
   ```powershell
   Restart-Service AutoBotNPUWorker
   ```

#### Issue: Slow inference
**Solution:**
1. Verify NPU is being used (not CPU fallback)
2. Pre-optimize models:
   ```powershell
   curl -X POST http://localhost:8082/model/optimize -H "Content-Type: application/json" -d "{\"model_name\": \"nomic-embed-text\", \"optimization_level\": \"speed\"}"
   ```

3. Check NPU utilization in health metrics

---

## Additional Resources

### Documentation
- **README.md**: Overview and quick start
- **DEPLOYMENT_SUMMARY.md**: Technical deployment details
- **BUILDING.md**: Build instructions for developers

### Support
- Check logs: `C:\Program Files\AutoBot\NPU\logs\`
- Run health check: `.\scripts\check-health.ps1`
- View statistics: `curl http://localhost:8082/stats`
- AutoBot documentation: `/home/kali/Desktop/AutoBot/docs/`

### Useful Commands

```powershell
# Service management
Get-Service AutoBotNPUWorker
Start-Service AutoBotNPUWorker
Stop-Service AutoBotNPUWorker
Restart-Service AutoBotNPUWorker

# Health monitoring
curl http://localhost:8082/health
curl http://localhost:8082/stats
curl http://localhost:8082/performance/benchmark

# Logs
Get-Content C:\Program Files\AutoBot\NPU\logs\service.log -Tail 50 -Wait
```

---

## Uninstallation

### Using Installer

1. Open **Settings** → **Apps** → **Installed apps**
2. Find **AutoBot NPU Worker**
3. Click **Uninstall**
4. Choose whether to keep data directories
5. Click **Uninstall** to confirm

### Manual Uninstallation

```powershell
# Stop and remove service
Stop-Service AutoBotNPUWorker
.\nssm\nssm.exe remove AutoBotNPUWorker confirm

# Remove firewall rule
Remove-NetFirewallRule -DisplayName "AutoBot NPU Worker"

# Remove installation directory
Remove-Item -Path "C:\Program Files\AutoBot\NPU" -Recurse -Force
```

---

**Installation complete! Your AutoBot NPU Worker is ready to provide hardware-accelerated AI processing.**

For questions or issues, consult the troubleshooting section above or review the comprehensive documentation in the `docs/` directory.
