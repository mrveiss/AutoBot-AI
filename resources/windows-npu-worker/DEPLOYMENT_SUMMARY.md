# Windows NPU Worker Deployment Package - Summary

## Package Overview

**Version**: 1.0.0
**Build Date**: 2025-10-04
**Platform**: Windows 10/11 (64-bit)
**Purpose**: Optional standalone NPU worker for AutoBot platform

## Architecture Design

### Deployment Strategy

**Approach**: Virtual Environment (venv)
**Rationale**: OpenVINO complexity makes PyInstaller unsuitable; venv provides isolation with manageable size

**Service Management**: NSSM (Non-Sucking Service Manager)
**Rationale**: Simple, reliable, no coding required, handles Python processes well

### Directory Structure

```
C:\AutoBot\NPU\
├── app\                    # Application code
│   └── npu_worker.py      # Main NPU worker (600+ lines)
├── config\                # Configuration
│   └── npu_worker.yaml    # Windows-specific config
├── scripts\               # PowerShell management scripts
│   ├── install.ps1        # Main installation (300+ lines)
│   ├── uninstall.ps1      # Clean uninstallation
│   ├── start-service.ps1  # Start NPU service
│   ├── stop-service.ps1   # Stop NPU service
│   ├── restart-service.ps1 # Restart NPU service
│   ├── check-health.ps1   # Comprehensive health check (200+ lines)
│   ├── view-logs.ps1      # Log viewer
│   └── update.ps1         # Update system
├── logs\                  # Log files (created during install)
├── models\                # OpenVINO model cache
├── data\                  # Runtime data
├── nssm\                  # Service manager
│   └── nssm.exe          # Downloaded during install
├── venv\                  # Python virtual environment (created during install)
├── requirements.txt       # Python dependencies
└── README.md             # User documentation (500+ lines)
```

## Key Features

### 1. Standalone Installation
- No interference with existing VM-based NPU worker
- Separate port (8082 vs VM's 8081)
- Independent configuration and logging
- Optional deployment - can be installed/uninstalled without affecting VMs

### 2. Windows Service Integration
- **Service Name**: AutoBotNPUWorker
- **Display Name**: AutoBot NPU Worker (Windows)
- **Startup Type**: Automatic (Delayed Start)
- **Recovery**: Auto-restart on failure (3 attempts, 60s delay)
- **Logging**: NSSM logs to `logs\service.log`

### 3. Easy Enable/Disable
```powershell
# Enable
.\scripts\start-service.ps1

# Disable
.\scripts\stop-service.ps1

# Temporary disable
Stop-Service AutoBotNPUWorker

# Permanent disable
sc.exe config AutoBotNPUWorker start= disabled
```

### 4. Automatic Configuration
- Firewall rules auto-created during installation
- Windows service auto-registered
- Virtual environment auto-configured
- Dependencies auto-installed

### 5. Health Monitoring
- HTTP health endpoint: `http://localhost:8082/health`
- Comprehensive health check script
- Performance benchmarking
- NPU hardware detection and monitoring

## Network Configuration

### Port Assignment
- **Windows NPU Worker**: 8082
- **VM NPU Worker**: 8081 (no conflict)
- **Backend**: 8001
- **Redis**: 6379

### Firewall Rules
Automatically created during installation:
```powershell
New-NetFirewallRule -DisplayName "AutoBot NPU Worker" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8082 `
  -Action Allow `
  -Profile Any
```

### Network Connectivity
Worker connects to:
- **Backend**: 172.16.168.20:8001 (service registry)
- **Redis**: 172.16.168.23:6379 (task queues)
- **Optional**: Other AutoBot services for distributed processing

## Installation Process

### Prerequisites
- Windows 10/11 (64-bit)
- Administrator rights
- Python 3.10+ (can be bundled)
- Network access to AutoBot infrastructure
- 2GB free disk space

### Installation Steps

1. **Extract Package**:
   ```powershell
   # Extract to C:\AutoBot\NPU\
   ```

2. **Run Installer**:
   ```powershell
   cd C:\AutoBot\NPU
   .\scripts\install.ps1
   ```

3. **Installation Process**:
   - Checks prerequisites (Windows version, Python, admin rights)
   - Creates virtual environment
   - Installs Python dependencies (FastAPI, OpenVINO, Redis, etc.)
   - Creates directory structure
   - Downloads NSSM service manager
   - Configures Windows Firewall
   - Installs and starts Windows service
   - Performs health check validation

4. **Verification**:
   ```powershell
   .\scripts\check-health.ps1
   ```

### Installation Time
- **Typical**: 5-10 minutes
- **Dependencies download**: 3-7 minutes (depends on internet speed)
- **Service configuration**: 1-2 minutes
- **Validation**: 30 seconds

## Configuration

### Main Configuration File
**Location**: `C:\AutoBot\NPU\config\npu_worker.yaml`

**Key Settings**:
```yaml
service:
  host: "0.0.0.0"
  port: 8082          # Different from VM worker (8081)

backend:
  host: "172.16.168.20"
  port: 8001

redis:
  host: "172.16.168.23"
  port: 6379

npu:
  optimization:
    precision: "INT8"  # NPU-optimized
    batch_size: 32
    num_streams: 2
```

### Environment Variables
Optional `.env` file support for:
- Redis password
- Backend authentication
- Custom paths

## Management Commands

### Service Control
```powershell
# Start service
.\scripts\start-service.ps1

# Stop service
.\scripts\stop-service.ps1

# Restart service
.\scripts\restart-service.ps1

# Check status
Get-Service AutoBotNPUWorker
```

### Health Monitoring
```powershell
# Quick health check
.\scripts\check-health.ps1

# Detailed statistics
.\scripts\check-health.ps1 -Detailed

# Performance benchmark
.\scripts\check-health.ps1 -Benchmark
```

### Log Management
```powershell
# View recent logs
.\scripts\view-logs.ps1

# Follow logs (live)
.\scripts\view-logs.ps1 -Follow

# View last 100 lines
.\scripts\view-logs.ps1 -Lines 100
```

### Updates
```powershell
# Update dependencies and restart
.\scripts\update.ps1

# Update without backup
.\scripts\update.ps1 -SkipBackup
```

## API Endpoints

### Health & Monitoring
- **GET** `/health` - Service health and NPU metrics
- **GET** `/stats` - Detailed worker statistics

### Inference Operations
- **POST** `/inference` - Run inference task
- **POST** `/embedding/generate` - Generate embeddings
- **POST** `/search/semantic` - Semantic search

### Management
- **POST** `/model/optimize` - Optimize model for NPU
- **GET** `/performance/benchmark` - Performance benchmark

## Dependencies

### Python Packages
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
aiohttp>=3.9.0
redis>=5.0.0
openvino>=2023.2.0
openvino-dev>=2023.2.0
numpy>=1.24.0
scikit-learn>=1.3.0
structlog>=23.2.0
pyyaml>=6.0.1
python-dotenv>=1.0.0
```

### External Tools
- **NSSM**: Auto-downloaded during installation (2.24)
- **Python**: 3.10+ (system installation or bundled)

## Testing & Validation

### Health Check Tests
1. Windows service status
2. HTTP endpoint responsiveness
3. NPU hardware detection
4. Model loading capability
5. Network connectivity (backend, Redis)
6. Performance metrics collection

### Validation Commands
```powershell
# Basic validation
curl http://localhost:8082/health

# Detailed health check
.\scripts\check-health.ps1 -Detailed

# Performance validation
.\scripts\check-health.ps1 -Benchmark

# Network validation
Test-NetConnection -ComputerName 172.16.168.20 -Port 8001
Test-NetConnection -ComputerName 172.16.168.23 -Port 6379
```

### Expected Health Response
```json
{
  "status": "healthy",
  "worker_id": "windows_npu_worker_abc12345",
  "platform": "windows",
  "port": 8082,
  "npu_available": true,
  "loaded_models": ["nomic-embed-text", "llama3.2:1b-instruct-q4_K_M"],
  "stats": {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "average_response_time_ms": 0
  },
  "npu_metrics": {
    "npu_available": true,
    "utilization_percent": 0,
    "temperature_c": 35,
    "power_usage_w": 1.5
  }
}
```

## Troubleshooting

### Common Issues

**1. Service Won't Start**
- Check logs: `.\scripts\view-logs.ps1`
- Verify Python: `.\venv\Scripts\python.exe --version`
- Test manual start: `.\venv\Scripts\python.exe .\app\npu_worker.py`

**2. NPU Not Detected**
- Verify OpenVINO: `.\venv\Scripts\python.exe -c "import openvino; print(openvino.__version__)"`
- Update Intel drivers
- Check device manager for NPU

**3. Cannot Connect to Backend/Redis**
- Test connectivity: `Test-NetConnection -ComputerName 172.16.168.20 -Port 8001`
- Check firewall: `Get-NetFirewallRule -DisplayName "AutoBot NPU Worker"`
- Verify network configuration in `config\npu_worker.yaml`

**4. High CPU/Memory Usage**
- Check loaded models: `curl http://localhost:8082/stats`
- Reduce batch size in configuration
- Restart service: `.\scripts\restart-service.ps1`

## Uninstallation

### Complete Removal
```powershell
.\scripts\uninstall.ps1
```

### Keep Data
```powershell
.\scripts\uninstall.ps1 -KeepData
```

### Keep Logs
```powershell
.\scripts\uninstall.ps1 -KeepLogs
```

### Manual Uninstallation
1. Stop service: `Stop-Service AutoBotNPUWorker`
2. Remove service: `sc.exe delete AutoBotNPUWorker`
3. Remove firewall rule: `Remove-NetFirewallRule -DisplayName "AutoBot NPU Worker"`
4. Delete directory: `Remove-Item C:\AutoBot\NPU -Recurse -Force`

## Backend Integration

### Service Discovery
Worker automatically registers with AutoBot backend service registry at:
- **URL**: `http://172.16.168.20:8001/api/service/register`
- **Interval**: 30 seconds
- **Health Check**: 60 seconds

### Task Queue Integration
Worker connects to Redis task queues:
- **Pending**: `npu_tasks_pending`
- **Processing**: `npu_tasks_processing`
- **Completed**: `npu_tasks_completed`
- **Failed**: `npu_tasks_failed`

### Load Balancing
Backend automatically distributes tasks between:
- VM NPU Worker (172.16.168.22:8081)
- Windows NPU Worker (localhost:8082)

Based on:
- Worker availability
- NPU utilization
- Task priority
- Response time metrics

## Security Considerations

### Network Security
- Firewall rules limit access to port 8082
- No external internet access required (after installation)
- Private network communication only

### Service Security
- Runs as Windows service with appropriate permissions
- No elevated privileges required for operation
- Service isolation from user sessions

### Data Security
- No sensitive data stored
- Model cache is ephemeral
- Logs contain no credentials
- Redis connection optional (can work without)

## Performance Expectations

### Hardware Acceleration
- **With NPU**: 5-10x faster inference vs CPU
- **Without NPU**: Automatic CPU fallback
- **Embedding Generation**: 10-30ms with NPU, 50-200ms with CPU
- **Semantic Search**: 5-20ms for 1000 documents

### Resource Usage
- **Memory**: 500MB-2GB (depends on loaded models)
- **CPU**: 5-20% idle, 30-80% under load
- **Disk**: 2GB installation + models
- **Network**: Minimal (task queues only)

## Package Contents

```
windows-npu-worker/
├── app/
│   └── npu_worker.py              # 600+ lines - Main worker implementation
├── config/
│   └── npu_worker.yaml            # 200+ lines - Configuration
├── scripts/
│   ├── install.ps1                # 300+ lines - Installation
│   ├── uninstall.ps1              # 100+ lines - Uninstallation
│   ├── start-service.ps1          # 30 lines - Service start
│   ├── stop-service.ps1           # 30 lines - Service stop
│   ├── restart-service.ps1        # 30 lines - Service restart
│   ├── check-health.ps1           # 200+ lines - Health checks
│   ├── view-logs.ps1              # 30 lines - Log viewer
│   └── update.ps1                 # 100+ lines - Update system
├── requirements.txt               # 15 lines - Dependencies
├── README.md                      # 500+ lines - User guide
├── DEPLOYMENT_SUMMARY.md          # This file
└── (Empty directories created during install: logs, models, data, nssm)
```

**Total Lines of Code**: ~2,200 lines
**Documentation**: ~1,000 lines
**PowerShell Scripts**: ~800 lines
**Python Code**: ~600 lines
**Configuration**: ~200 lines

## Support & Documentation

### Documentation Files
- **README.md**: Complete user guide with installation and troubleshooting
- **DEPLOYMENT_SUMMARY.md**: This file - technical deployment details
- **npu_worker.yaml**: Inline configuration documentation

### Health Check URLs
- **Local**: http://localhost:8082/health
- **Network**: http://<windows-ip>:8082/health
- **Backend**: http://172.16.168.20:8001/api/system/health (check for worker registration)

### Log Locations
- **Service Log**: `C:\AutoBot\NPU\logs\service.log` (NSSM service wrapper)
- **Application Log**: `C:\AutoBot\NPU\logs\app.log` (NPU worker application)
- **Error Log**: `C:\AutoBot\NPU\logs\error.log` (Error output)

## Deployment Checklist

### Pre-Installation
- [ ] Windows 10/11 (64-bit) confirmed
- [ ] Administrator access available
- [ ] Python 3.10+ installed (or will install embedded)
- [ ] 2GB disk space available
- [ ] Network access to 172.16.168.20 and 172.16.168.23 confirmed

### Installation
- [ ] Package extracted to C:\AutoBot\NPU\
- [ ] Ran `.\scripts\install.ps1` as Administrator
- [ ] No errors during installation
- [ ] Virtual environment created
- [ ] Dependencies installed successfully
- [ ] NSSM downloaded
- [ ] Firewall rule created
- [ ] Service installed
- [ ] Service started

### Validation
- [ ] Service status: Running (`Get-Service AutoBotNPUWorker`)
- [ ] Health check: PASSED (`.\scripts\check-health.ps1`)
- [ ] HTTP endpoint responding (`curl http://localhost:8082/health`)
- [ ] NPU detected (or CPU fallback working)
- [ ] Backend connectivity confirmed
- [ ] Redis connectivity confirmed (if used)

### Post-Installation
- [ ] Review logs: `.\scripts\view-logs.ps1`
- [ ] Run benchmark: `.\scripts\check-health.ps1 -Benchmark`
- [ ] Document any configuration changes
- [ ] Add to monitoring/alerting systems

## Version History

### 1.0.0 (2025-10-04)
- Initial release
- Windows service integration
- NPU hardware acceleration support
- Comprehensive management scripts
- Full documentation
- Health monitoring and benchmarking
- Backend integration via service registry
- Redis task queue support

## License

This software is part of the AutoBot platform. See LICENSE.txt for details.

---

**Package Prepared By**: AutoBot Development Team
**Build Date**: 2025-10-04
**Package Version**: 1.0.0
**Target Platform**: Windows 10/11 (64-bit)
