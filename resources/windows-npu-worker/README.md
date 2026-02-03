# AutoBot NPU Worker - Windows Deployment Package

## Overview

This package provides a standalone NPU worker installation for Windows systems. It enables optional hardware-accelerated AI processing using ONNX Runtime with DirectML for stable NPU/GPU acceleration without interfering with the existing VM-based infrastructure.

> **Issue #640**: Replaced raw OpenVINO with ONNX Runtime + DirectML for more stable NPU inference. DirectML provides better error handling and automatic device fallback.

## Features

- Standalone Windows installation
- ONNX Runtime + DirectML for NPU/GPU acceleration
- Windows Service integration with auto-start
- Separate port (8082) to avoid conflicts with VM worker
- Easy enable/disable via service management
- Comprehensive health monitoring
- Automatic firewall configuration
- **Network information display on startup** - Shows all IP addresses and registration URLs
- **GUI Connection Info panel** - Easy backend integration with copy-to-clipboard
- **Platform detection** - Automatic NPU and system information display

## System Requirements

- **Operating System**: Windows 10/11 (64-bit)
- **Python**: 3.10 or higher (can be bundled with installation)
- **Hardware**: Intel CPU with NPU support (Core Ultra series or newer)
- **RAM**: Minimum 8GB, Recommended 16GB
- **Disk Space**: 2GB for installation + models
- **Network**: Access to AutoBot backend (172.16.168.20:8001) and Redis (172.16.168.23:6379)
- **Permissions**: Administrator rights for installation

## Quick Start

### 1. Installation

1. Extract this package to `C:\AutoBot\NPU\`
2. Open PowerShell as Administrator
3. Navigate to the installation directory:
   ```powershell
   cd C:\AutoBot\NPU
   ```
4. Run the installation script:
   ```powershell
   .\scripts\install.ps1
   ```

The installer will:
- Check prerequisites
- Install Python dependencies
- Configure Windows Service
- Set up firewall rules
- Start the NPU worker service

### 2. Verify Installation

Check service status:
```powershell
.\scripts\check-health.ps1
```

Or manually:
```powershell
Get-Service AutoBotNPUWorker
curl http://localhost:8082/health
```

### 3. View Logs

```powershell
.\scripts\view-logs.ps1
```

Or manually:
```powershell
Get-Content .\logs\service.log -Tail 50 -Wait
```

## Service Management

### Start Service
```powershell
.\scripts\start-service.ps1
```

### Stop Service
```powershell
.\scripts\stop-service.ps1
```

### Restart Service
```powershell
.\scripts\restart-service.ps1
```

### Check Status
```powershell
Get-Service AutoBotNPUWorker
```

## Configuration

Edit `config\npu_worker.yaml` to customize:

```yaml
# Service Configuration
service:
  host: "0.0.0.0"      # Bind to all interfaces
  port: 8082           # Windows worker port (VM uses 8081)

# Backend Integration
backend:
  host: "172.16.168.20"
  port: 8001

# Redis Configuration
redis:
  host: "172.16.168.23"
  port: 6379

# NPU Optimization
npu:
  precision: "INT8"     # INT8 for NPU optimization
  batch_size: 32
  num_streams: 2
  num_threads: 4

# Logging
logging:
  level: "INFO"
  directory: "logs"
  max_size_mb: 100
  backup_count: 5
```

After configuration changes, restart the service:
```powershell
.\scripts\restart-service.ps1
```

## Health Monitoring

### Check NPU Worker Health
```powershell
curl http://localhost:8082/health
```

Expected response:
```json
{
  "status": "healthy",
  "worker_id": "enhanced_npu_worker_xxxxxxxx",
  "npu_available": true,
  "loaded_models": ["nomic-embed-text", "llama3.2:1b-instruct-q4_K_M"],
  "stats": {
    "tasks_completed": 0,
    "tasks_failed": 0,
    "average_response_time_ms": 0
  },
  "npu_metrics": {
    "utilization_percent": 0,
    "temperature_c": 35,
    "power_usage_w": 1.5
  }
}
```

### Performance Benchmark
```powershell
curl http://localhost:8082/performance/benchmark
```

### Detailed Statistics
```powershell
curl http://localhost:8082/stats
```

## Firewall Configuration

The installer automatically creates a firewall rule. To manually configure:

```powershell
New-NetFirewallRule -DisplayName "AutoBot NPU Worker" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8082 `
  -Action Allow `
  -Profile Any
```

To remove:
```powershell
Remove-NetFirewallRule -DisplayName "AutoBot NPU Worker"
```

## Backend Integration

The NPU worker automatically registers with the AutoBot backend service registry. No manual configuration needed.

To verify integration:
```powershell
curl http://172.16.168.20:8001/api/system/health
```

Check for NPU worker in the response.

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```powershell
   .\scripts\view-logs.ps1
   ```

2. Verify Python installation:
   ```powershell
   .\venv\Scripts\python.exe --version
   ```

3. Test manual startup:
   ```powershell
   .\venv\Scripts\python.exe .\app\npu_worker.py
   ```

### NPU Not Detected

1. Verify ONNX Runtime DirectML installation:
   ```powershell
   .\venv\Scripts\python.exe -c "import onnxruntime as ort; print(f'ONNX Runtime {ort.__version__}')"
   ```

2. Check available execution providers:
   ```powershell
   .\venv\Scripts\python.exe -c "import onnxruntime as ort; print(ort.get_available_providers())"
   ```

3. For NPU support, ensure Windows 11 24H2+ and Intel AI Boost drivers are installed

### Cannot Connect to Backend/Redis

1. Check network connectivity:
   ```powershell
   Test-NetConnection -ComputerName 172.16.168.20 -Port 8001
   Test-NetConnection -ComputerName 172.16.168.23 -Port 6379
   ```

2. Verify firewall allows outbound connections

3. Check backend/Redis services are running

### High CPU/Memory Usage

1. Check loaded models:
   ```powershell
   curl http://localhost:8082/stats
   ```

2. Reduce batch size in `config\npu_worker.yaml`

3. Restart service after configuration changes

## Updating

To update the NPU worker:

```powershell
.\scripts\update.ps1
```

This will:
- Stop the service
- Update Python dependencies
- Update application code
- Restart the service

## Uninstallation

To completely remove the NPU worker:

```powershell
.\scripts\uninstall.ps1
```

This will:
- Stop and remove the Windows service
- Remove firewall rules
- Clean up logs (optional)
- Optionally remove the entire installation directory

## Directory Structure

```
C:\AutoBot\NPU\
├── app\                 # Application code
│   ├── npu_worker.py   # Main worker
│   └── config.py       # Configuration loader
├── config\             # Configuration files
│   ├── npu_worker.yaml # Main config
│   └── .env           # Environment variables
├── logs\              # Log files
│   ├── service.log    # Service logs
│   └── app.log        # Application logs
├── models\            # ONNX model cache
├── data\              # Runtime data
├── nssm\              # Service manager
│   └── nssm.exe
├── scripts\           # Management scripts
│   ├── install.ps1
│   ├── uninstall.ps1
│   ├── start-service.ps1
│   ├── stop-service.ps1
│   ├── restart-service.ps1
│   ├── check-health.ps1
│   ├── view-logs.ps1
│   └── update.ps1
├── venv\              # Python virtual environment
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

## Advanced Usage

### Custom Port Configuration

To use a different port:

1. Edit `config\npu_worker.yaml`:
   ```yaml
   service:
     port: 8083  # Your custom port
   ```

2. Update firewall rule:
   ```powershell
   New-NetFirewallRule -DisplayName "AutoBot NPU Worker Custom" `
     -Direction Inbound `
     -Protocol TCP `
     -LocalPort 8083 `
     -Action Allow
   ```

3. Restart service

### Development Mode

For development/testing:

1. Stop the service:
   ```powershell
   .\scripts\stop-service.ps1
   ```

2. Run manually with debug logging:
   ```powershell
   .\venv\Scripts\python.exe .\app\npu_worker.py --debug
   ```

### Model Optimization

Pre-optimize models for NPU:

```powershell
curl -X POST http://localhost:8082/model/optimize `
  -H "Content-Type: application/json" `
  -d '{"model_name": "nomic-embed-text", "optimization_level": "speed"}'
```

## API Endpoints

### Health Check
- **GET** `/health` - Service health and metrics

### Inference
- **POST** `/inference` - Run inference task
- **POST** `/embedding/generate` - Generate embeddings
- **POST** `/search/semantic` - Semantic search

### Management
- **GET** `/stats` - Detailed statistics
- **POST** `/model/optimize` - Optimize model
- **GET** `/performance/benchmark` - Performance benchmark

## Support

For issues or questions:
1. Check logs: `.\scripts\view-logs.ps1`
2. Review health status: `.\scripts\check-health.ps1`
3. Consult AutoBot documentation: `/home/kali/Desktop/AutoBot/docs/`
4. Report issues via AutoBot issue tracker

## License

This software is part of the AutoBot platform. See LICENSE.txt for details.

## Version

- Package Version: 1.0.0
- NPU Worker Version: 2.0.0
- Build Date: 2025-10-04
