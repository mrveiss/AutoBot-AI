# VM Service States Documentation

**Author**: mrveiss
**Issue**: #432
**Last Updated**: 2025-12-23

This document describes the expected states of VM services in the AutoBot infrastructure,
including graceful degradation behavior and how to manage service availability.

---

## Overview

AutoBot uses a distributed VM infrastructure with 5 VMs plus the main WSL machine. Not all
services need to be running at all times - the system is designed to gracefully handle
offline services through circuit breakers and intelligent log suppression.

---

## Service Categories

### Critical Services (Required for Core Functionality)

| Service | VM | IP:Port | Description |
|---------|-----|---------|-------------|
| **Backend API** | Main (WSL) | 172.16.168.20:8443 | Core backend - must always be running |
| **Redis** | VM3 | 172.16.168.23:6379 | Data layer - required for caching, sessions, queues |

**If these are offline**: System will not function properly. Immediate attention required.

### Optional Services (Enhanced Features)

| Service | VM | IP:Port | Description | When Offline |
|---------|-----|---------|-------------|--------------|
| **Frontend** | VM1 | 172.16.168.21:5173 | Web interface | Use backend API directly |
| **NPU Worker** | VM2 | 172.16.168.22:8081 | Hardware AI acceleration | Falls back to CPU inference |
| **AI Stack** | VM4 | 172.16.168.24:8080 | AI processing stack | Limited AI features |
| **Ollama** | VM4 | 172.16.168.24:11434 | Local LLM inference | Uses fallback LLM providers |
| **Browser Automation** | VM5 | 172.16.168.25:3000 | Playwright automation | Web scraping unavailable |

**If these are offline**: System continues with reduced functionality. Non-urgent.

---

## Expected States by Environment

### Development Environment

During active development, it's normal to have:

- ✅ **Backend API** - Always running
- ✅ **Redis** - Always running (or using local Redis)
- ⚠️ **Frontend** - Running when working on UI
- ❌ **NPU Worker** - Often offline unless testing AI acceleration
- ❌ **AI Stack** - Often offline unless testing AI features
- ❌ **Browser Automation** - Often offline unless testing web scraping

### Production Environment

In production, all services should ideally be running:

- ✅ All services should be online
- Circuit breakers will handle temporary failures
- Monitoring will alert on extended outages

---

## Service States

The VM service registry tracks the following states:

| State | Description | Log Behavior |
|-------|-------------|--------------|
| `ONLINE` | Service responding normally | No error logs |
| `OFFLINE` | Service not responding | Error logged (with suppression) |
| `DEGRADED` | Service responding with issues | Warning logged |
| `UNKNOWN` | Service never checked | Debug logged |
| `INTENTIONALLY_OFFLINE` | Marked as intentionally stopped | No error logs |

---

## Log Suppression (Issue #432)

To prevent log spam when services are known to be offline, the system implements
intelligent log suppression:

### Suppression Rules

1. **First 3 failures**: All errors are logged
2. **After 3 consecutive failures**: Log suppression begins
3. **During suppression (5 minutes)**: One log every 60 seconds with summary
4. **After suppression period**: Log once, then restart suppression

### Example Log Output

```
# First failure
WARNING: VM service NPU Worker (npu_worker) is offline: Cannot connect to 172.16.168.22:8081

# Second failure
WARNING: VM service NPU Worker (npu_worker) is offline: Cannot connect to 172.16.168.22:8081

# Third failure
WARNING: VM service NPU Worker (npu_worker) is offline: Cannot connect to 172.16.168.22:8081

# Fourth failure (suppression begins)
WARNING: VM service NPU Worker (npu_worker) is offline: Cannot connect to 172.16.168.22:8081

# Next 60 seconds of failures: no logs

# After 60 seconds
WARNING: VM service NPU Worker (npu_worker) is offline: Cannot connect to 172.16.168.22:8081 (47 similar errors suppressed)
```

---

## Circuit Breaker Integration

Each VM service has a dedicated circuit breaker that:

1. **Tracks failures**: Opens after 5 consecutive failures
2. **Prevents hammering**: Stops health checks to failing service
3. **Allows recovery**: Half-opens after timeout to test recovery
4. **Reports state**: Available via API for monitoring

### Circuit States

| State | Description |
|-------|-------------|
| `CLOSED` | Normal operation, requests allowed |
| `OPEN` | Service failing, requests blocked |
| `HALF_OPEN` | Testing recovery, limited requests |

---

## API Endpoints

### Get All Service Status

```bash
curl http://localhost:8001/api/vm-services/status
```

**Response**:
```json
{
  "timestamp": "2025-12-23T10:30:00Z",
  "summary": {
    "total": 6,
    "online": 3,
    "offline": 3,
    "critical_offline": 0,
    "health_status": "degraded"
  },
  "services": {
    "frontend": {"status": "online", ...},
    "npu_worker": {"status": "offline", ...},
    "redis": {"status": "online", ...},
    "ai_stack": {"status": "offline", ...},
    "browser": {"status": "offline", ...},
    "ollama": {"status": "offline", ...}
  }
}
```

### Check Specific Service

```bash
curl http://localhost:8001/api/vm-services/status/npu_worker
```

### Trigger Health Check

```bash
curl -X POST http://localhost:8001/api/vm-services/check/redis
```

### Mark Service as Intentionally Offline

Use this when you intentionally stop a service to prevent error logging:

```bash
curl -X POST http://localhost:8001/api/vm-services/mark-offline/npu_worker \
  -H "Content-Type: application/json" \
  -d '{"reason": "Maintenance"}'
```

### Get Available Services Only

```bash
curl http://localhost:8001/api/vm-services/available
```

### Get Critical Services Status

```bash
curl http://localhost:8001/api/vm-services/critical
```

---

## Troubleshooting

### Service Won't Come Online

1. **Check VM is running**: `ssh autobot@172.16.168.XX "hostname"`
2. **Check service is started**: SSH in and check service status
3. **Check port is listening**: `netstat -tlnp | grep <port>`
4. **Check firewall rules**: Ensure port is accessible

### Too Many Error Logs

1. **Mark service as intentionally offline** if you know it's stopped
2. **Check circuit breaker state** - may need manual reset
3. **Adjust suppression settings** if needed (in vm_service_registry.py)

### Circuit Breaker Won't Close

1. **Service may still be failing** - check actual service health
2. **Wait for recovery timeout** (default: 3x service timeout)
3. **Trigger manual health check** via API

---

## Configuration

### Default Service Timeouts

| Service | Timeout |
|---------|---------|
| Frontend | 10s |
| NPU Worker | 15s |
| Redis | 5s |
| AI Stack | 20s |
| Browser | 10s |
| Ollama | 10s |

### Suppression Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Threshold | 3 failures | Failures before suppression starts |
| Duration | 300s (5min) | How long suppression lasts |
| Log interval | 60s | How often to log during suppression |

---

## Related Documentation

- [Infrastructure Deployment](../developer/INFRASTRUCTURE_DEPLOYMENT.md) - VM setup and deployment
- [System State](../system-state.md) - Current system status
- [Troubleshooting Guide](../troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md) - Problem resolution
