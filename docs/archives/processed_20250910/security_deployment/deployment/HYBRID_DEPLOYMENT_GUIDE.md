# AutoBot Hybrid Deployment Guide
## WSL2 + Windows NPU Worker + Docker Services

This guide shows how to deploy AutoBot with optimal hardware utilization:
- **WSL2**: Main system, GPU workloads, orchestration
- **Windows Host**: Native NPU worker for fast inference
- **Docker**: Containerized services (Playwright, Knowledge Base, etc.)

## 🏗️ Architecture Overview

```
┌─────────────── WINDOWS HOST ────────────────┐
│  ┌─────────────────┐    ┌──────────────────┐ │
│  │   NPU Worker    │    │   Docker Desktop │ │
│  │  (Port 8080)    │    │                  │ │
│  │                 │    │  ┌─────────────┐ │ │
│  │ • Chat (1B)     │    │  │ Research    │ │ │
│  │ • Embeddings    │    │  │ (Playwright)│ │ │
│  │ • Classification│    │  └─────────────┘ │ │
│  └─────────────────┘    └──────────────────┘ │
│           │                       │           │
│ ┌─────────────────────────────────────────── │
│ │                WSL2                        │
│ │  ┌─────────────────────────────────────┐  │
│ │  │           AutoBot Main              │  │
│ │  │                                     │  │
│ │  │ • Orchestrator (Coordinator)       │  │
│ │  │ • FastAPI Backend (8001)           │  │
│ │  │ • Vue Frontend (5173)              │  │
│ │  │ • Redis (Task Queue)               │  │
│ │  │ • GPU Agents (RAG, Large Models)   │  │
│ │  │ • System Commands                  │  │
│ │  └─────────────────────────────────────┘  │
│ └─────────────────────────────────────────── │
└───────────────────────────────────────────────┘
```

## 📋 Prerequisites

### Windows Host Requirements
- Windows 11 (for Intel NPU driver support)
- Intel Core Ultra processor with NPU
- 16GB+ RAM
- Docker Desktop
- Python 3.10+

### WSL2 Requirements
- Ubuntu 20.04+ or similar
- NVIDIA GPU with CUDA support
- Python 3.10+
- Docker access from WSL2

## 🚀 Deployment Steps

### Step 1: Setup Windows NPU Worker

#### 1.1 Install Intel NPU Drivers
```powershell
# Download and install Intel NPU drivers from Intel website
# Or use Windows Update to get latest drivers for Core Ultra

# Verify NPU detection
Get-WmiObject -Class Win32_PnPEntity | Where-Object {$_.Name -like "*NPU*"}
```

#### 1.2 Install OpenVINO with NPU Support
```powershell
# Install OpenVINO
pip install openvino openvino-dev[pytorch,tensorflow]

# Install NPU-specific plugins
pip install openvino-npu --upgrade

# Test NPU availability
python -c "from openvino.runtime import Core; print(Core().available_devices)"
```

#### 1.3 Deploy NPU Worker
```powershell
# Copy npu_worker.py to Windows
# Install dependencies
pip install fastapi uvicorn redis aiohttp

# Start NPU worker (pointing to WSL2 Redis)
python npu_worker.py --host 0.0.0.0 --port 8080 --redis-host <WSL2_IP>
```

#### 1.4 Create Windows Service (Optional)
```powershell
# Create service for auto-start
nssm install "AutoBot NPU Worker" "python" "C:\path\to\npu_worker.py"
nssm set "AutoBot NPU Worker" AppParameters "--host 0.0.0.0 --port 8080 --redis-host 172.16.0.1"
nssm start "AutoBot NPU Worker"
```

### Step 2: Configure WSL2 Main System

#### 2.1 Network Configuration
```bash
# Allow Redis connections from Windows host
# Edit Redis config or update docker-compose.yml
sudo ufw allow from 172.16.0.0/12 to any port 6379
```

#### 2.2 Update AutoBot Configuration
```bash
# Add NPU worker client to src/config.py
cat >> src/config.yaml << EOF
npu_worker:
  enabled: true
  host: $(ip route | grep default | awk '{print $3}')
  port: 8080
  task_types:
    - chat_inference
    - embedding_generation
    - text_classification
EOF
```

#### 2.3 Install Dependencies
```bash
# Install additional packages for hybrid mode
pip install aiohttp redis

# Verify GPU optimization
source gpu_env_config.sh
python3 system_monitor.py
```

### Step 3: Deploy Docker Services

#### 3.1 Start Containerized Services
```bash
# Build and start Docker services
docker-compose up -d

# Verify services
docker-compose ps
docker-compose logs research-agent
```

#### 3.2 Verify Playwright in Docker
```bash
# Test Playwright container
docker exec autobot-research-agent playwright --version
docker exec autobot-research-agent python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

### Step 4: Start Main AutoBot System

#### 4.1 Apply Optimizations
```bash
# Source GPU configuration
source gpu_env_config.sh

# Apply NPU environment (if needed for fallback)
source npu_env_config.sh

# Start AutoBot with hybrid configuration
./run_agent.sh
```

#### 4.2 Verify Hybrid Operation
```bash
# Check comprehensive status
python3 system_monitor.py

# Test NPU worker connection
curl http://$(ip route | grep default | awk '{print $3}'):8080/health
```

## 📊 Monitoring and Verification

### System Health Check
```bash
# Comprehensive system check
python3 system_monitor.py --continuous 10
```

### Performance Testing
```bash
# Test inference performance comparison
python3 system_monitor.py --test

# Monitor resource usage
watch -n 1 "nvidia-smi; echo '---'; curl -s http://localhost:8001/api/monitoring/status | jq '.gpu_status, .npu_status'"
```

## 🔧 Task Distribution Logic

### NPU Worker Handles:
- **Chat conversations** (1B model) → 0.5-1.5s response
- **Text embeddings** → 10-50ms per text
- **System commands** → Fast NLP processing
- **Text classification** → <100ms processing

### WSL2 GPU Handles:
- **Document analysis (RAG)** → Complex reasoning
- **Web research** → Playwright + large models
- **Code generation** → 3B+ models
- **Multi-document synthesis** → Memory-intensive

### Docker Containers Handle:
- **Research Agent** → Isolated Playwright environment
- **Knowledge Base** → ChromaDB vector operations
- **Frontend** → Vue.js web interface
- **Redis** → Data persistence and task queuing

## 🚨 Troubleshooting

### NPU Worker Issues
```powershell
# Check NPU driver status
Get-Device | Where-Object {$_.Name -like "*NPU*"}

# Verify OpenVINO
python -c "from openvino.runtime import Core; c=Core(); print('NPU devices:', [d for d in c.available_devices if 'NPU' in d])"

# Check worker logs
# Look for NPU initialization messages
```

### WSL2 Connection Issues
```bash
# Find WSL2 IP
ip addr show eth0

# Test Redis connection from Windows
# From PowerShell: Test-NetConnection -ComputerName <WSL2_IP> -Port 6379

# Update firewall rules
sudo ufw allow from 172.16.0.0/12 to any port 6379
sudo ufw reload
```

### Docker Service Issues
```bash
# Check container logs
docker-compose logs research-agent
docker-compose logs knowledge-base

# Restart specific service
docker-compose restart research-agent

# Check resource usage
docker stats
```

## ⚡ Performance Optimization

### NPU Optimization
- Use INT8 quantization for NPU models
- Keep frequently used models loaded
- Batch small requests when possible
- Monitor thermal throttling

### GPU Optimization
- Reserve GPU memory efficiently
- Use tensor parallelism for large models
- Implement model swapping for memory management
- Monitor CUDA memory fragmentation

### Network Optimization
- Use Redis pipelining for task queues
- Implement connection pooling
- Monitor network latency between WSL2/Windows
- Use local caching for frequent requests

## 📈 Expected Performance

| Task Type | NPU Worker | WSL2 GPU | Improvement |
|-----------|------------|----------|-------------|
| Chat (1B) | 0.5-1.5s | 2-4s | 2-3x faster |
| Embeddings | 10-50ms | 100-200ms | 3-5x faster |
| RAG (3B) | N/A | 3-8s | GPU optimal |
| Research | N/A | 5-15s | Playwright isolated |
| Power Usage | 5-10W | 50-100W | 5-10x efficient |

## 🔐 Security Considerations

### Network Security
- Redis authentication enabled
- NPU worker API key authentication
- Firewall rules limiting access to WSL2 subnet
- Docker container isolation

### Data Security
- No sensitive data stored in NPU worker
- Encrypted Redis connections (optional)
- Container volume isolation
- Audit logging for all task processing

This hybrid deployment maximizes hardware utilization while maintaining security and performance optimization across the entire AutoBot system.
