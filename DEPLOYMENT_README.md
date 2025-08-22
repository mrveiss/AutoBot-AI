# AutoBot Deployment & Monitoring System

## 🚀 Complete Service Registry & Distributed Deployment Solution

This document covers the comprehensive deployment and monitoring system implemented for AutoBot, featuring dynamic service discovery, multiple deployment modes, and real-time health monitoring.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Deployment Modes](#deployment-modes)
- [Service Registry](#service-registry)
- [Deployment Automation](#deployment-automation)
- [Monitoring & Health Checks](#monitoring--health-checks)
- [CLI Tools](#cli-tools)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## 🏃‍♂️ Quick Start

### 1. **Default Deployment (Recommended)**
```bash
# Start with hybrid local + Docker mode (default)
./deploy.sh

# Or manually:
./run_agent.sh
```

### 2. **Full Docker Deployment**
```bash
# Deploy everything in Docker containers
./deploy.sh --mode docker_local --build
```

### 3. **Distributed Deployment**
```bash
# Deploy across multiple machines
./deploy.sh --mode distributed --config config/deployment/production.yml
```

### 4. **Monitor Services**
```bash
# Web dashboard (recommended)
python scripts/monitor_services.py --web --port 8080

# CLI monitoring
python scripts/monitor_services.py --cli --interval 10

# One-time status check
python -m src.utils.service_registry_cli health
```

## 🏗️ Deployment Modes

### **Local Mode (Default - Recommended)**
- **Backend & Frontend**: Run on host machine
- **Services**: Redis, AI Stack, NPU Worker run in Docker
- **Best for**: Development and most production deployments
- **Benefits**: Easy debugging, optimal performance

```bash
./deploy.sh --mode local
```

### **Docker Local Mode**
- **All services**: Run in Docker containers on single machine
- **Best for**: Consistent environments, easy deployment
- **Benefits**: Full containerization, isolation

```bash
./deploy.sh --mode docker_local --build
```

### **Distributed Mode**
- **Services**: Spread across multiple machines
- **Best for**: High availability, load distribution
- **Benefits**: Scalability, fault tolerance

```bash
./deploy.sh --mode distributed --config production.yml
```

### **Kubernetes Mode**
- **Services**: Managed by Kubernetes
- **Best for**: Enterprise deployments
- **Benefits**: Auto-scaling, orchestration, resilience

```bash
./deploy.sh --mode kubernetes --namespace autobot-prod --build
```

## 🔧 Service Registry

### **Dynamic Service Discovery**
The Service Registry automatically resolves service URLs based on deployment mode:

```python
from src.utils.service_registry import get_service_url

# Automatically resolves to correct URL based on deployment
redis_url = get_service_url("redis")
backend_url = get_service_url("backend", "/api/health")
```

### **Supported Services**
- **redis**: Database and caching
- **ai-stack**: Ollama LLM services
- **npu-worker**: NPU acceleration worker
- **backend**: Main API server
- **frontend**: Vue.js web interface
- **playwright-vnc**: Browser automation

### **Configuration Files**
Service configurations are in `config/deployment/`:
- `local.yml` - Default hybrid mode
- `docker_local.yml` - Full Docker mode
- `distributed.yml` - Multi-machine deployment
- `kubernetes.yml` - Kubernetes cluster

## ⚙️ Deployment Automation

### **Deployment Script (`deploy.sh`)**

```bash
# Basic deployment
./deploy.sh

# Full Docker with image building
./deploy.sh --mode docker_local --build

# Distributed with custom config
./deploy.sh --mode distributed --config my-config.yml

# Kubernetes deployment
./deploy.sh --mode kubernetes --namespace production

# Cleanup deployment
./deploy.sh --cleanup --mode local
```

### **Python Deployment Tool**

```bash
# Advanced deployment with Python script
python scripts/deploy_autobot.py --mode local
python scripts/deploy_autobot.py --mode docker_local --build
python scripts/deploy_autobot.py --mode distributed --config production.yml
python scripts/deploy_autobot.py --cleanup
```

### **Available Options**
- `--mode`: Deployment mode (local, docker_local, distributed, kubernetes)
- `--config`: Custom configuration file
- `--namespace`: Kubernetes namespace
- `--build`: Build Docker images
- `--cleanup`: Remove deployment
- `--no-wait`: Don't wait for health checks

## 📊 Monitoring & Health Checks

### **Web Dashboard**
Real-time web dashboard with auto-refresh:

```bash
python scripts/monitor_services.py --web --port 8080
```

Features:
- ✅ Real-time service health status
- 📈 Response time metrics
- 📊 Overall system health percentage
- 🔄 Auto-refresh every 30 seconds
- 📱 Responsive design

### **CLI Monitoring**
Terminal-based continuous monitoring:

```bash
python scripts/monitor_services.py --cli --interval 10
```

### **JSON Reports**
Generate detailed reports:

```bash
# Output to console
python scripts/monitor_services.py --json

# Save to file
python scripts/monitor_services.py --json --output report.json
```

## 🛠️ CLI Tools

### **Service Registry CLI**

```bash
# Service status overview
python -m src.utils.service_registry_cli status

# Health check all services
python -m src.utils.service_registry_cli health

# Get specific service URL
python -m src.utils.service_registry_cli url redis

# Test specific service
python -m src.utils.service_registry_cli test backend

# Test all services with JSON output
python -m src.utils.service_registry_cli test-all --json
```

### **Service-Specific Commands**

```bash
# Get service configuration
python -m src.utils.service_registry_cli config redis

# Show deployment information
python -m src.utils.service_registry_cli deploy
```

## 🔧 Configuration

### **Environment Variables**
Override service locations with environment variables:

```bash
# Service-specific overrides
export REDIS_HOST=my-redis-server
export REDIS_PORT=6380
export BACKEND_HOST=api.mydomain.com

# Deployment mode override
export AUTOBOT_DEPLOYMENT_MODE=distributed
export AUTOBOT_DISTRIBUTED=true
```

### **Configuration File Structure**

```yaml
# config/deployment/custom.yml
deployment_mode: distributed
domain: production.autobot.com

services:
  redis:
    host: redis.internal
    port: 6379
    scheme: redis
    health_endpoint: "/"
    timeout: 5
    circuit_breaker_threshold: 3

  backend:
    host: api.internal
    port: 8001
    scheme: https
    health_endpoint: /api/health
    timeout: 10
    circuit_breaker_threshold: 5
```

### **Docker Compose Files**
Located in `docker/compose/`:
- `docker-compose.hybrid.yml` - Default hybrid mode
- `docker-compose.full.yml` - Full Docker deployment
- `docker-compose.redis.yml` - Redis only
- `docker-compose.ai-stack.yml` - AI services only
- `docker-compose.npu-worker.yml` - NPU worker only

## 🚨 Troubleshooting

### **Common Issues**

**1. Services Not Starting**
```bash
# Check service health
python -m src.utils.service_registry_cli health

# Check Docker containers
docker ps -a

# Check logs
docker logs autobot-redis
```

**2. Connection Refused Errors**
```bash
# Verify service URLs
python -m src.utils.service_registry_cli status

# Test connectivity
python -m src.utils.service_registry_cli test redis
```

**3. API Timeouts**
```bash
# Monitor response times
python scripts/monitor_services.py --cli --interval 5

# Check specific service
python -m src.utils.service_registry_cli test backend
```

### **Debug Mode**
Enable detailed logging:

```bash
export AUTOBOT_DEBUG=true
export AUTOBOT_LOG_LEVEL=DEBUG
```

### **Health Check Endpoints**
Each service provides health endpoints:
- Redis: Port availability check
- Backend: `GET /api/health`
- Frontend: `GET /` (200 response)
- AI Stack: `GET /api/tags`
- NPU Worker: `GET /health`

### **Performance Optimization**

**Chat List Performance Issue - FIXED**
- **Problem**: `/api/chats` endpoint was taking 30+ seconds
- **Cause**: Decrypting every chat file for metadata
- **Solution**: Implemented `list_sessions_fast()` using file timestamps
- **Result**: Reduced from 30s to <1s response time

**Frontend PointerEvent Bug - FIXED**
- **Problem**: `[object PointerEvent]` sent instead of chat IDs
- **Cause**: Event object passed to delete function
- **Solution**: Added parameter validation in `deleteSpecificChat()`
- **Result**: Eliminated error logs and improved reliability

## 📁 File Structure

```
AutoBot/
├── deploy.sh                    # Quick deployment wrapper
├── scripts/
│   ├── deploy_autobot.py       # Advanced deployment automation
│   └── monitor_services.py     # Service monitoring dashboard
├── src/utils/
│   ├── service_registry.py     # Core service discovery
│   └── service_registry_cli.py # CLI management tool
├── config/deployment/          # Deployment configurations
│   ├── local.yml
│   ├── docker_local.yml
│   ├── distributed.yml
│   └── kubernetes.yml
├── docker/compose/             # Docker Compose files
│   ├── docker-compose.hybrid.yml
│   ├── docker-compose.full.yml
│   ├── docker-compose.redis.yml
│   ├── docker-compose.ai-stack.yml
│   └── docker-compose.npu-worker.yml
└── tests/
    └── test_distributed_deployment.py
```

## 🎯 Next Steps

1. **Start with default deployment**: `./deploy.sh`
2. **Monitor services**: `python scripts/monitor_services.py --web`
3. **Check health**: `python -m src.utils.service_registry_cli health`
4. **Scale as needed**: Use distributed or Kubernetes modes

## 📚 Additional Resources

- **Service Registry Documentation**: See `src/utils/service_registry.py`
- **Deployment Examples**: Check `scripts/deploy_autobot.py --help`
- **Monitoring Guide**: Run `python scripts/monitor_services.py --help`
- **Docker Documentation**: Review `docker/compose/` files

---

🚀 **The AutoBot deployment system is now fully automated and production-ready!**
