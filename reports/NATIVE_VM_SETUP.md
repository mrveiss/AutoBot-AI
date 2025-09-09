# AutoBot Native VM Deployment - Single Startup Procedure

This document provides the complete procedure for starting and managing AutoBot in native VM deployment mode.

## Prerequisites

Before running AutoBot Native VM, ensure:

1. **All VMs are running and accessible:**
   - VM1 (172.16.168.21) - Frontend
   - VM2 (172.16.168.22) - NPU Worker  
   - VM3 (172.16.168.23) - Redis Stack
   - VM4 (172.16.168.24) - AI Stack
   - VM5 (172.16.168.25) - Browser Service

2. **SSH connectivity is configured:**
   - SSH key exists at `~/.ssh/autobot_key`
   - All VMs can be accessed as `autobot@<vm_ip>` using the key
   - Passwordless sudo is configured on all VMs

3. **Services are deployed on VMs:**
   - Initial deployment has been completed
   - All SystemD services are installed and configured

## Quick Start

### Start AutoBot
```bash
./start_autobot_native.sh
```

### Check Status
```bash
./status_autobot_native.sh
```

### Stop AutoBot
```bash
./stop_autobot_native.sh
```

## Detailed Usage

### Starting AutoBot Native

The start script will:
1. ✅ Check prerequisites (SSH key, configuration)
2. 🔗 Test connectivity to all VMs
3. 🚀 Start all VM services (parallel by default)
4. 🔧 Start WSL backend
5. 🏥 Verify service health
6. 🌐 Launch browser (optional)

```bash
# Standard startup (recommended)
./start_autobot_native.sh

# Start without auto-launching browser
./start_autobot_native.sh --no-browser

# Start services sequentially (slower but safer)
./start_autobot_native.sh --sequential

# Show help
./start_autobot_native.sh --help
```

**Example output:**
```
🚀 AutoBot Native VM - Single Startup Procedure
=================================================

🔍 Checking Prerequisites...
✅ SSH key found
✅ Configuration found

🔗 Testing VM Connectivity...
  Testing frontend (172.16.168.21)... ✅ Connected
  Testing npu-worker (172.16.168.22)... ✅ Connected
  Testing redis (172.16.168.23)... ✅ Connected
  Testing ai-stack (172.16.168.24)... ✅ Connected
  Testing browser (172.16.168.25)... ✅ Connected
✅ All VMs are accessible

🚀 Starting all VM services in parallel...
🚀 Starting frontend service...
✅ frontend service started successfully
🚀 Starting npu-worker service...
✅ npu-worker service started successfully
🚀 Starting redis service...
✅ redis service started successfully
🚀 Starting ai-stack service...
✅ ai-stack service started successfully
🚀 Starting browser service...
✅ browser service started successfully
✅ All VM services start commands completed

🔧 Starting WSL Backend...
Using optimized backend startup...
✅ WSL Backend started (PID: 12345)
Waiting for backend to be ready... ✅ Ready!

🏥 Testing service health (waiting for initialization)...

📊 Final Service Health Status:
  frontend health check... ✅ Healthy
  npu-worker health check... ✅ Healthy
  redis health check... ✅ Healthy
  ai-stack health check... ✅ Healthy
  browser health check... ✅ Healthy
  WSL Backend health check... ✅ Healthy

🌐 Launching browser...
✅ Firefox launched

🎉 AutoBot Native VM Deployment Started Successfully!
🌐 Access Points:
  Frontend:   http://172.16.168.21/
  Backend:    http://172.16.168.20:8001/
  AI Stack:   http://172.16.168.24:8080/health
  NPU Worker: http://172.16.168.22:8081/health
  Browser:    http://172.16.168.25:3000/health
```

### Checking Status

Monitor all services across VMs:

```bash
# Quick status check
./status_autobot_native.sh

# Detailed status with service info
./status_autobot_native.sh --detailed

# Status without health endpoint checks
./status_autobot_native.sh --no-health
```

### Stopping AutoBot Native

The stop script will:
1. 🛑 Stop WSL backend gracefully
2. 🛑 Stop all VM services (parallel by default)
3. ✅ Verify all services are stopped

```bash
# Standard shutdown (recommended)
./stop_autobot_native.sh

# Force shutdown (kill processes if needed)
./stop_autobot_native.sh --force

# Stop services sequentially
./stop_autobot_native.sh --sequential
```

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                AUTOBOT NATIVE VM ARCHITECTURE                │
├─────────────────────────────────────────────────────────────┤
│  WSL Backend (172.16.168.20:8001) ←→ Native VM Services     │
│         ↑                                                   │
│    User Interface                                           │
│         ↓                                                   │
│  Frontend VM1 (172.16.168.21) ────────── Nginx + Vue.js    │
│  NPU Worker VM2 (172.16.168.22:8081) ──── Hardware Detection│
│  Redis Stack VM3 (172.16.168.23:6379) ─── Data & Cache     │
│  AI Stack VM4 (172.16.168.24:8080) ────── AI Processing    │
│  Browser VM5 (172.16.168.25:3000) ──────── Web Automation  │
└─────────────────────────────────────────────────────────────┘
```

## Access Points

After starting AutoBot Native:

- **🌐 Frontend Interface**: http://172.16.168.21/
- **🔧 Backend API**: http://172.16.168.20:8001/
- **🧠 AI Stack**: http://172.16.168.24:8080/health
- **🚀 NPU Worker**: http://172.16.168.22:8081/health  
- **🌍 Browser Service**: http://172.16.168.25:3000/health

## Troubleshooting

### VM Not Accessible
```bash
# Check if VM is running in Hyper-V Manager
# Test manual SSH connection:
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21
```

### Service Won't Start
```bash
# Check service status on specific VM:
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 'sudo systemctl status nginx'

# Check service logs:
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 'sudo journalctl -u nginx -n 20'
```

### Backend Connection Issues
```bash
# Test backend health directly:
curl http://127.0.0.1:8001/api/health

# Check backend logs:
# Backend logs are shown in the start script output
```

### Health Check Failures
```bash
# Test specific service health:
curl http://172.16.168.22:8081/health
curl http://172.16.168.24:8080/health
curl http://172.16.168.25:3000/health

# Test Redis connectivity:
echo "PING" | nc -w 2 172.16.168.23 6379
```

## Configuration Files

- **`.env.native-vm`**: Native VM environment configuration
- **`~/.ssh/autobot_key`**: SSH key for VM access
- **`ansible/inventory/production.yml`**: VM inventory configuration

## Scripts Overview

- **`start_autobot_native.sh`**: Complete startup procedure
- **`stop_autobot_native.sh`**: Complete shutdown procedure
- **`status_autobot_native.sh`**: Status monitoring
- **`validate_native_deployment.sh`**: Comprehensive health validation

## Best Practices

1. **Always check status before starting**: `./status_autobot_native.sh`
2. **Use parallel operations for speed**: Default behavior, use `--sequential` only if issues occur
3. **Monitor logs**: Backend logs are shown during startup
4. **Graceful shutdown**: Always use the stop script, avoid killing processes manually
5. **Health validation**: Run `./validate_native_deployment.sh` periodically

## Performance Notes

- **VM Services**: Continue running independently even after stopping WSL backend
- **Startup Time**: ~30-60 seconds for complete startup (depends on VM performance)
- **Resource Usage**: Each service isolated on its own VM with dedicated resources
- **Network Latency**: Sub-5ms response times between VMs in same network