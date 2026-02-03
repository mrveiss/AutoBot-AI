# AutoBot Scaling Strategy

**Last Updated**: 2025-12-21
**Related Issue**: [#251](https://github.com/mrveiss/AutoBot-AI/issues/251)
**Classification**: Operations Critical

This document provides scaling strategies and playbooks for AutoBot's distributed VM infrastructure.

---

## Scaling Philosophy

AutoBot's 6-VM architecture enables independent scaling of each component. This document covers:
- **Vertical Scaling**: Adding more resources (CPU, RAM, storage) to existing VMs
- **Horizontal Scaling**: Adding more VM instances for load distribution

---

## Current Resource Allocations

| VM | IP | vCPUs | RAM | Storage | Purpose |
|----|-----|-------|-----|---------|---------|
| Main (WSL) | 172.16.168.20 | 4 | 8 GB | 50 GB | Backend API + VNC |
| VM1 Frontend | 172.16.168.21 | 2 | 4 GB | 20 GB | Web interface |
| VM2 NPU Worker | 172.16.168.22 | 4 | 8 GB | 30 GB | Hardware AI |
| VM3 Redis | 172.16.168.23 | 2 | 8 GB | 50 GB | Data layer |
| VM4 AI Stack | 172.16.168.24 | 4 | 16 GB | 100 GB | LLM models |
| VM5 Browser | 172.16.168.25 | 2 | 4 GB | 20 GB | Playwright |

---

## Scaling Triggers

### When to Scale

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| API Response Time | > 500ms | > 2s | Scale Backend |
| LLM Response Time | > 10s | > 30s | Scale AI Stack |
| Redis Memory | > 70% | > 90% | Scale Redis |
| CPU Usage (sustained) | > 70% | > 90% | Scale affected VM |
| Embedding Queue Depth | > 100 | > 500 | Scale NPU Worker |
| Concurrent Users | > 10 | > 50 | Scale Frontend + Backend |

---

## VM1: Frontend Scaling

### Current Load Capacity
- ~20 concurrent users with dev server
- ~100 concurrent users with production build + nginx

### Vertical Scaling

**When**: Response times > 200ms, high CPU on VM1

```powershell
# On Hyper-V host - Stop VM first
Stop-VM -Name "AutoBot-Frontend"

# Increase resources
Set-VMProcessor -VMName "AutoBot-Frontend" -Count 4
Set-VMMemory -VMName "AutoBot-Frontend" -DynamicMemoryEnabled $false -StartupBytes 8GB

# Start VM
Start-VM -Name "AutoBot-Frontend"
```

**Post-scaling verification**:
```bash
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21
free -h  # Verify RAM
nproc    # Verify CPUs
```

### Horizontal Scaling

**When**: Need > 100 concurrent users or high availability

**Architecture**:
```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (nginx/HAProxy)│
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ Frontend A  │   │ Frontend B  │   │ Frontend C  │
    │ 172.16.168.21│   │ 172.16.168.26│   │ 172.16.168.27│
    └─────────────┘   └─────────────┘   └─────────────┘
```

**Steps**:

1. **Clone Frontend VM**
   ```powershell
   # Export existing VM
   Export-VM -Name "AutoBot-Frontend" -Path "C:\VMs\Exports"

   # Import as new VM with different name
   Import-VM -Path "C:\VMs\Exports\AutoBot-Frontend\..." -Copy -GenerateNewId
   ```

2. **Configure new VM**
   ```bash
   # Set new static IP (e.g., 172.16.168.26)
   sudo nano /etc/netplan/00-installer-config.yaml
   sudo netplan apply
   ```

3. **Setup Load Balancer** (on main machine or dedicated VM)
   ```nginx
   # /etc/nginx/conf.d/frontend-lb.conf
   upstream frontend_pool {
       least_conn;
       server 172.16.168.21:5173;
       server 172.16.168.26:5173;
   }

   server {
       listen 80;
       location / {
           proxy_pass http://frontend_pool;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

---

## VM2: NPU Worker Scaling

### Current Load Capacity
- ~50 embeddings/second with Intel NPU
- Fallback to cloud when saturated

### Vertical Scaling

**When**: Embedding queue depth > 100, NPU utilization > 80%

**Option 1: Upgrade NPU Hardware**
- Requires physical hardware change
- Consider Intel Core Ultra with better NPU

**Option 2: Add GPU Support**
```bash
# If GPU available, configure OpenVINO for GPU
python3 -c "from openvino.runtime import Core; print(Core().available_devices)"
# Should show: ['CPU', 'GPU', 'NPU']
```

### Horizontal Scaling

**When**: Need > 100 embeddings/second

**Architecture**:
```
                    ┌─────────────────┐
                    │  Backend API    │
                    │ (Load Balancer) │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ NPU Worker A│   │ NPU Worker B│   │ Cloud API   │
    │ 172.16.168.22│   │ 172.16.168.28│   │ (Fallback)  │
    └─────────────┘   └─────────────┘   └─────────────┘
```

**Backend Configuration**:
```python
# In backend/core/config.py
NPU_WORKERS = [
    "http://172.16.168.22:8081",
    "http://172.16.168.28:8081",
]

# Round-robin or least-connections load balancing
```

---

## VM3: Redis Scaling

### Current Load Capacity
- ~10,000 ops/second
- 8 GB RAM = ~4-6 GB usable for data

### Vertical Scaling

**When**: Memory usage > 70%, slow queries detected

```powershell
# Increase RAM (Redis benefits most from RAM)
Stop-VM -Name "AutoBot-Redis"
Set-VMMemory -VMName "AutoBot-Redis" -DynamicMemoryEnabled $false -StartupBytes 16GB
Start-VM -Name "AutoBot-Redis"
```

**Configure Redis for new memory**:
```bash
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23

# Update Redis config
sudo nano /etc/redis-stack.conf
# Set: maxmemory 12gb

sudo systemctl restart redis-stack-server
```

### Horizontal Scaling (Redis Cluster)

**When**: Need > 50,000 ops/second or > 32 GB data

**Architecture**:
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Redis Node 1│  │  Redis Node 2│  │  Redis Node 3│
│  (Primary)   │  │  (Primary)   │  │  (Primary)   │
│ Slots 0-5460 │  │ Slots 5461-10922│ │ Slots 10923-16383│
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐
│  Redis Node 4│  │  Redis Node 5│  │  Redis Node 6│
│  (Replica)   │  │  (Replica)   │  │  (Replica)   │
└──────────────┘  └──────────────┘  └──────────────┘
```

**Steps**:

1. **Create Redis VMs** (minimum 6 for production cluster)

2. **Configure cluster mode**:
   ```bash
   # On each node, edit redis.conf
   cluster-enabled yes
   cluster-config-file nodes.conf
   cluster-node-timeout 5000
   ```

3. **Initialize cluster**:
   ```bash
   redis-cli --cluster create \
     172.16.168.23:6379 172.16.168.29:6379 172.16.168.30:6379 \
     172.16.168.31:6379 172.16.168.32:6379 172.16.168.33:6379 \
     --cluster-replicas 1
   ```

4. **Update application**:
   ```python
   from redis.cluster import RedisCluster

   redis = RedisCluster(
       host="172.16.168.23",
       port=6379,
       decode_responses=True
   )
   ```

---

## VM4: AI Stack Scaling

### Current Load Capacity
- ~5 concurrent LLM requests (depends on model size)
- Bottleneck is typically GPU/CPU for inference

### Vertical Scaling

**When**: LLM response time > 10s, queue depth increasing

**Option 1: Add RAM** (for larger models)
```powershell
Stop-VM -Name "AutoBot-AI"
Set-VMMemory -VMName "AutoBot-AI" -DynamicMemoryEnabled $false -StartupBytes 32GB
Start-VM -Name "AutoBot-AI"
```

**Option 2: Add GPU** (significant speedup)
```powershell
# GPU passthrough to VM
Add-VMGpuPartitionAdapter -VMName "AutoBot-AI"
Set-VMGpuPartitionAdapter -VMName "AutoBot-AI" -MinPartitionVRAM 2GB
```

### Horizontal Scaling

**When**: Need > 10 concurrent LLM requests

**Architecture**:
```
                    ┌─────────────────┐
                    │  Backend API    │
                    │ (LLM Router)    │
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ Ollama A    │   │ Ollama B    │   │ Cloud LLM   │
    │ 172.16.168.24│   │ 172.16.168.34│   │ (Overflow)  │
    └─────────────┘   └─────────────┘   └─────────────┘
```

**Load Balancer Configuration**:
```python
# In LLM interface
OLLAMA_ENDPOINTS = [
    "http://172.16.168.24:8080",
    "http://172.16.168.34:8080",
]

async def get_available_ollama():
    """Return least loaded Ollama instance"""
    for endpoint in OLLAMA_ENDPOINTS:
        if await check_health(endpoint):
            return endpoint
    return CLOUD_FALLBACK
```

---

## VM5: Browser Automation Scaling

### Current Load Capacity
- ~5 concurrent browser sessions
- Limited by RAM (each Chromium instance uses ~200-500 MB)

### Vertical Scaling

**When**: Browser operations queuing, high memory usage

```powershell
Stop-VM -Name "AutoBot-Browser"
Set-VMProcessor -VMName "AutoBot-Browser" -Count 4
Set-VMMemory -VMName "AutoBot-Browser" -DynamicMemoryEnabled $false -StartupBytes 8GB
Start-VM -Name "AutoBot-Browser"
```

### Horizontal Scaling (Browser Pool)

**When**: Need > 10 concurrent browser sessions

**Architecture**:
```
                    ┌─────────────────┐
                    │  Backend API    │
                    │ (Browser Router)│
                    └────────┬────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
    ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ Browser A   │   │ Browser B   │   │ Browser C   │
    │ 172.16.168.25│   │ 172.16.168.35│   │ 172.16.168.36│
    └─────────────┘   └─────────────┘   └─────────────┘
```

**Pool Manager**:
```python
BROWSER_POOL = [
    "http://172.16.168.25:3000",
    "http://172.16.168.35:3000",
    "http://172.16.168.36:3000",
]

async def get_browser_session():
    """Get available browser from pool"""
    for browser in BROWSER_POOL:
        sessions = await get_active_sessions(browser)
        if sessions < MAX_SESSIONS_PER_VM:
            return browser
    raise BrowserPoolExhausted()
```

---

## Main Backend Scaling

### Current Load Capacity
- ~100 concurrent API requests
- Limited by CPU and async worker count

### Vertical Scaling

**When**: API response time > 500ms, high CPU

```bash
# WSL memory adjustment (in .wslconfig)
[wsl2]
memory=16GB
processors=8
```

**Increase Uvicorn workers**:
```bash
# In run_autobot.sh
uvicorn backend.main:app --host 0.0.0.0 --port 8001 --workers 8
```

### Horizontal Scaling

**When**: Need > 500 concurrent API requests

Deploy multiple backend instances behind load balancer. Requires:
- Session affinity or shared session store (Redis)
- Shared file storage for uploads
- Load balancer (nginx, HAProxy, or cloud LB)

---

## Monitoring for Scaling Decisions

### Key Metrics to Watch

```bash
#!/bin/bash
# scaling_metrics.sh - Run every 5 minutes

# API Response Time
curl -w "%{time_total}\n" -o /dev/null -s http://localhost:8001/api/health

# Redis Memory
redis-cli -h 172.16.168.23 INFO memory | grep used_memory_human

# Ollama Queue
curl -s http://172.16.168.24:8080/api/ps | jq '.models | length'

# VM CPU Usage
ssh autobot@172.16.168.21 "top -bn1 | grep 'Cpu(s)'"
ssh autobot@172.16.168.24 "top -bn1 | grep 'Cpu(s)'"
```

### Alerting Thresholds

Configure alerts in monitoring system for:
- Response time > warning threshold for 5 minutes
- Memory usage > 80% for 10 minutes
- CPU usage > 90% for 5 minutes
- Queue depth > critical threshold

---

## Scaling Checklist

Before scaling any component:

- [ ] Verify current resource usage and bottleneck
- [ ] Document current state
- [ ] Schedule maintenance window if needed
- [ ] Take VM snapshot before changes
- [ ] Test in non-production first if possible
- [ ] Update monitoring for new capacity
- [ ] Document new resource allocation
- [ ] Verify application health after scaling

---

## Related Documentation

- [ADR-001: Distributed VM Architecture](../adr/001-distributed-vm-architecture.md)
- [Disaster Recovery](disaster-recovery.md)
- [Infrastructure Deployment](../developer/INFRASTRUCTURE_DEPLOYMENT.md)

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
