# Windows NPU Worker - Quick Start Guide

**Two deployment options available:**
- 🎯 **Installer Package** (Recommended) - Professional Windows installer with automatic setup
- 🔧 **Manual Installation** (Advanced) - Virtual environment with manual configuration

---

## 🎯 Method 1: Installer Package (Recommended)

### 5-Minute Installation

#### Step 1: Download Installer
Get `AutoBot-NPU-Worker-Setup-1.0.0.exe` from releases

#### Step 2: Run Installer
```powershell
# Double-click to run, or from PowerShell:
.\AutoBot-NPU-Worker-Setup-1.0.0.exe
```

#### Step 3: Follow Installation Wizard
- ✅ Accept license agreement
- ✅ Choose installation location (default: `C:\Program Files\AutoBot\NPU\`)
- ✅ Select components:
  - Install as Windows Service (recommended)
  - Configure firewall (recommended)
  - Start automatically (recommended)
- ✅ Click "Install"

**Installation automatically:**

- Installs all dependencies (Python, ONNX Runtime DirectML, etc.)
- Configures Windows Firewall (port 8082)
- Installs and starts Windows Service
- Registers with AutoBot backend

**Installation time:** 5-10 minutes

#### Step 4: Verify Installation
```powershell
# Check service status
Get-Service AutoBotNPUWorker

# Check health endpoint
curl http://localhost:8082/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "worker_id": "windows_npu_worker_abc12345",
  "npu_available": true,
  "platform": "windows"
}
```

### Daily Usage (Installer)

```powershell
# Start Programs → AutoBot NPU Worker → [command]

# Or use PowerShell:
Start-Service AutoBotNPUWorker     # Start
Stop-Service AutoBotNPUWorker      # Stop
Restart-Service AutoBotNPUWorker   # Restart
Get-Service AutoBotNPUWorker       # Status

# Health check
curl http://localhost:8082/health

# View logs
Get-Content "C:\Program Files\AutoBot\NPU\logs\service.log" -Tail 50
```

---

## 🔧 Method 2: Manual Installation (Advanced)

### 10-Minute Setup

#### Step 1: Extract Package
```powershell
# Extract to C:\AutoBot\NPU\
Expand-Archive -Path AutoBot-NPU-Worker.zip -DestinationPath C:\AutoBot\NPU\
cd C:\AutoBot\NPU
```

#### Step 2: Run Installer Script (as Administrator)
```powershell
.\scripts\install.ps1
```

**Installation will automatically:**

- ✅ Create Python virtual environment
- ✅ Install all dependencies (ONNX Runtime DirectML, FastAPI, Redis, etc.)
- ✅ Download NSSM service manager
- ✅ Configure Windows Firewall (port 8082)
- ✅ Install and start Windows Service
- ✅ Run health check validation

**Expected time**: 5-10 minutes (depends on internet speed)

#### Step 3: Verify Installation
```powershell
.\scripts\check-health.ps1
```

**Expected output:**
```
========================================
  AutoBot NPU Worker - Health Check
========================================

✓ Service Status: Running
✓ HTTP Endpoint: Responding
✓ Worker ID: windows_npu_worker_abc12345
✓ NPU Available: true
✓ Backend: Reachable (172.16.168.20:8001)
✓ Redis: Reachable (172.16.168.23:6379)

Health check: PASSED
```

### Daily Usage (Manual)

```powershell
# Service management
.\scripts\start-service.ps1      # Start
.\scripts\stop-service.ps1       # Stop
.\scripts\restart-service.ps1    # Restart
.\scripts\check-health.ps1       # Health check
.\scripts\view-logs.ps1          # View logs

# Or use Windows service commands:
Get-Service AutoBotNPUWorker
Start-Service AutoBotNPUWorker
Stop-Service AutoBotNPUWorker
```

---

## 📋 Common Operations (Both Methods)

### Service Management
```powershell
# Start
Start-Service AutoBotNPUWorker

# Stop
Stop-Service AutoBotNPUWorker

# Restart
Restart-Service AutoBotNPUWorker

# Status
Get-Service AutoBotNPUWorker
```

### Health Monitoring
```powershell
# Quick health check
curl http://localhost:8082/health

# Detailed stats
curl http://localhost:8082/stats

# Performance benchmark
curl http://localhost:8082/performance/benchmark
```

### Logs
```powershell
# Installer path
Get-Content "C:\Program Files\AutoBot\NPU\logs\service.log" -Tail 50

# Manual installation path
Get-Content "C:\AutoBot\NPU\logs\service.log" -Tail 50

# Or use provided script (if manual installation)
C:\AutoBot\NPU\scripts\view-logs.ps1
```

---

## 🔧 Troubleshooting

### Service Not Running?
```powershell
# Check service status
Get-Service AutoBotNPUWorker

# View recent logs (adjust path based on installation method)
Get-Content "C:\Program Files\AutoBot\NPU\logs\service.log" -Tail 50

# Restart service
Restart-Service AutoBotNPUWorker
```

### Health Check Fails?
```powershell
# Test HTTP endpoint
curl http://localhost:8082/health

# Check network connectivity
Test-NetConnection -ComputerName 172.16.168.20 -Port 8001
Test-NetConnection -ComputerName 172.16.168.23 -Port 6379

# Restart service
Restart-Service AutoBotNPUWorker
```

### NPU Not Detected?
```powershell
# Installer path
& "C:\Program Files\AutoBot\NPU\python\python.exe" -c "import onnxruntime as ort; print(f'ONNX Runtime {ort.__version__}')"

# Manual installation path
& C:\AutoBot\NPU\venv\Scripts\python.exe -c "import onnxruntime as ort; print(f'ONNX Runtime {ort.__version__}')"

# Check available execution providers
& python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

### Port Conflict?
```powershell
# Find process using port 8082
netstat -ano | findstr :8082

# Change port in config (installer path)
notepad "C:\Program Files\AutoBot\NPU\config\npu_worker.yaml"

# Or manual installation path
notepad C:\AutoBot\NPU\config\npu_worker.yaml

# Update firewall for new port
New-NetFirewallRule -DisplayName "AutoBot NPU Worker" -Direction Inbound -Protocol TCP -LocalPort <NEW_PORT> -Action Allow

# Restart service
Restart-Service AutoBotNPUWorker
```

---

## ⚙️ Configuration

### Main Config File
**Installer**: `C:\Program Files\AutoBot\NPU\config\npu_worker.yaml`
**Manual**: `C:\AutoBot\NPU\config\npu_worker.yaml`

**Key settings to customize:**
```yaml
service:
  port: 8082  # Change if port conflict

backend:
  host: "172.16.168.20"  # Your backend IP
  port: 8001

redis:
  host: "172.16.168.23"  # Your Redis IP
  port: 6379

logging:
  level: "INFO"  # DEBUG for troubleshooting
```

**After changes, restart:**
```powershell
Restart-Service AutoBotNPUWorker
```

---

## 🗑️ Uninstallation

### Installer Package
1. **Settings** → **Apps** → **Installed apps**
2. Find **AutoBot NPU Worker**
3. Click **Uninstall**
4. Choose whether to keep data directories
5. Click **Uninstall** to confirm

### Manual Installation
```powershell
# Complete removal
C:\AutoBot\NPU\scripts\uninstall.ps1

# Keep data/logs
C:\AutoBot\NPU\scripts\uninstall.ps1 -KeepData -KeepLogs
```

---

## 📊 Performance Testing

### Run Benchmark
```powershell
curl http://localhost:8082/performance/benchmark
```

**Expected results (with NPU):**
- **Embedding Generation**: 10-30ms per text
- **Semantic Search**: 5-20ms for 1000 documents

**CPU Fallback (without NPU):**
- **Embedding Generation**: 50-200ms per text
- **Semantic Search**: 20-100ms for 1000 documents

---

## 🔗 API Access

### Health Endpoint
```powershell
curl http://localhost:8082/health
```

### Generate Embeddings
```powershell
curl -X POST http://localhost:8082/embedding/generate `
  -H "Content-Type: application/json" `
  -d '{
    "texts": ["test text 1", "test text 2"],
    "model_name": "nomic-embed-text"
  }'
```

### Semantic Search
```powershell
curl -X POST http://localhost:8082/search/semantic `
  -H "Content-Type: application/json" `
  -d '{
    "query_text": "find relevant documents",
    "document_embeddings": [...],
    "document_metadata": [...],
    "top_k": 10
  }'
```

---

## 📚 Documentation

### Installation Methods
- **[INSTALLATION.md](INSTALLATION.md)** - Complete installation guide (both methods)
- **[BUILDING.md](BUILDING.md)** - Build installer from source

### Reference
- **[README.md](README.md)** - Overview and features
- **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** - Technical architecture
- **[QUICK_START.md](QUICK_START.md)** - This guide

---

## ✅ System Requirements

- ✅ Windows 10/11 (64-bit)
- ✅ Administrator rights
- ✅ Intel CPU with NPU support (Core Ultra series) - optional, CPU fallback available
- ✅ 8GB RAM minimum (16GB recommended)
- ✅ 2GB free disk space
- ✅ Network access to AutoBot backend and Redis

---

## 🎯 What's Next?

### For All Users
1. **Verify Health**: `curl http://localhost:8082/health`
2. **Check Logs**: Review service logs
3. **Test Performance**: Run benchmark endpoint
4. **Monitor**: Worker auto-registers with AutoBot backend

### Installer Package Users
- Access shortcuts from Start Menu
- Check health via browser: `http://localhost:8082/health`
- Configure via: `C:\Program Files\AutoBot\NPU\config\npu_worker.yaml`

### Manual Installation Users
- Use provided PowerShell scripts in `scripts/` directory
- Update via: `.\scripts\update.ps1`
- Configure via: `C:\AutoBot\NPU\config\npu_worker.yaml`

---

## 📖 Quick Reference Card

### Installer Package
```
INSTALLATION:        Run AutoBot-NPU-Worker-Setup-1.0.0.exe
HEALTH CHECK:        curl http://localhost:8082/health
SERVICE CONTROL:     Start Menu → AutoBot NPU Worker
CONFIG FILE:         C:\Program Files\AutoBot\NPU\config\npu_worker.yaml
LOG DIRECTORY:       C:\Program Files\AutoBot\NPU\logs\
UNINSTALL:           Settings → Apps → AutoBot NPU Worker
```

### Manual Installation
```
INSTALLATION:        .\scripts\install.ps1
HEALTH CHECK:        .\scripts\check-health.ps1
START SERVICE:       .\scripts\start-service.ps1
STOP SERVICE:        .\scripts\stop-service.ps1
RESTART SERVICE:     .\scripts\restart-service.ps1
VIEW LOGS:           .\scripts\view-logs.ps1
UPDATE:              .\scripts\update.ps1
UNINSTALL:           .\scripts\uninstall.ps1

CONFIG FILE:         C:\AutoBot\NPU\config\npu_worker.yaml
LOG DIRECTORY:       C:\AutoBot\NPU\logs\
SERVICE NAME:        AutoBotNPUWorker
```

### Common (Both Methods)
```
HEALTH URL:          http://localhost:8082/health
STATS URL:           http://localhost:8082/stats
BENCHMARK URL:       http://localhost:8082/performance/benchmark
SERVICE NAME:        AutoBotNPUWorker
DEFAULT PORT:        8082
```

---

**Version**: 1.0.0 | **Build**: 2025-10-04 | **Platform**: Windows 10/11

**Choose your deployment method and get started in minutes! 🚀**
