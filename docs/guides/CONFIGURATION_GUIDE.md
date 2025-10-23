# AutoBot Configuration Guide

## 🎯 Overview

AutoBot uses a comprehensive environment-driven configuration system that allows you to customize hosts, ports, and protocols for all services without modifying code.

## 🔧 Environment Variables

### Host Configuration
```bash
# Service Hosts (where each service runs)
AUTOBOT_OLLAMA_HOST=127.0.0.2          # Ollama AI service
AUTOBOT_LM_STUDIO_HOST=127.0.0.2       # LM Studio service
AUTOBOT_BACKEND_HOST=127.0.0.3         # AutoBot backend
AUTOBOT_FRONTEND_HOST=127.0.0.3        # Frontend dev server
AUTOBOT_REDIS_HOST=127.0.0.7           # Redis database
AUTOBOT_PLAYWRIGHT_HOST=127.0.0.4      # Playwright VNC
AUTOBOT_NPU_WORKER_HOST=127.0.0.5      # NPU worker
AUTOBOT_AI_STACK_HOST=127.0.0.6        # AI stack
AUTOBOT_LOG_VIEWER_HOST=127.0.0.8      # Centralized logging
```

### Port Configuration
```bash
# Service Ports
AUTOBOT_BACKEND_PORT=8001              # Backend API
AUTOBOT_FRONTEND_PORT=5173             # Frontend dev
AUTOBOT_OLLAMA_PORT=11434              # Ollama API
AUTOBOT_LM_STUDIO_PORT=1234            # LM Studio
AUTOBOT_REDIS_PORT=6379                # Redis
AUTOBOT_PLAYWRIGHT_API_PORT=3000       # Playwright API
AUTOBOT_PLAYWRIGHT_VNC_PORT=6080       # VNC web interface
AUTOBOT_NPU_WORKER_PORT=8081           # NPU worker
AUTOBOT_AI_STACK_PORT=8080             # AI stack
AUTOBOT_LOG_VIEWER_PORT=5341           # Log viewer
AUTOBOT_FLUENTD_PORT=24224             # Log collection
AUTOBOT_CHROME_DEBUG_PORT=9222         # Chrome debugging
```

### Protocol Configuration
```bash
# Protocols (http/https, ws/wss, etc.)
AUTOBOT_HTTP_PROTOCOL=http             # Can be https for SSL
AUTOBOT_WS_PROTOCOL=ws                 # Can be wss for secure WebSocket
AUTOBOT_REDIS_PROTOCOL=redis           # Redis connection protocol
```

## 🚀 Common Configuration Scenarios

### Development Setup
```bash
# .env file for development
AUTOBOT_BACKEND_PORT=8001
AUTOBOT_FRONTEND_PORT=5173
AUTOBOT_OLLAMA_HOST=127.0.0.2
AUTOBOT_REDIS_HOST=127.0.0.7
```

### Avoiding Port Conflicts
```bash
# If default ports are in use
export AUTOBOT_BACKEND_PORT=8002
export AUTOBOT_FRONTEND_PORT=3000
export AUTOBOT_REDIS_PORT=6380
./run_agent.sh
```

### Remote Services
```bash
# Ollama on remote server
export AUTOBOT_OLLAMA_HOST=192.168.1.100
export AUTOBOT_OLLAMA_PORT=11434

# Redis on separate machine
export AUTOBOT_REDIS_HOST=192.168.1.200
export AUTOBOT_REDIS_PORT=6379
```

### SSL/HTTPS Production
```bash
# Enable HTTPS and secure WebSockets
export AUTOBOT_HTTP_PROTOCOL=https
export AUTOBOT_WS_PROTOCOL=wss
export AUTOBOT_BACKEND_PORT=443
```

### Docker Deployment
```bash
# Custom Docker ports
export AUTOBOT_REDIS_PORT=6380
export AUTOBOT_BACKEND_PORT=8002
docker-compose up  # Uses custom ports automatically
```

## 📁 Configuration Files

### Environment Template
Copy `.env.example` to `.env` and customize:
```bash
cp .env.example .env
# Edit .env with your values
```

### Backend Settings
The backend automatically uses environment variables in `backend/config/settings.json`:
```json
{
  "backend": {
    "api_endpoint": "${AUTOBOT_API_BASE_URL}",
    "server_port": "${AUTOBOT_BACKEND_PORT}"
  }
}
```

### Frontend Configuration
Frontend uses Vite environment variables:
```javascript
// Automatically constructed from environment
BASE_URL: import.meta.env.VITE_API_BASE_URL ||
  `${AUTOBOT_HTTP_PROTOCOL}://${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT}`
```

## 🧪 Testing Configuration

Run the configuration validator:
```bash
python scripts/validate_configuration.py
```

Test specific scenarios:
```bash
# Test custom ports
AUTOBOT_BACKEND_PORT=8002 python scripts/validate_configuration.py

# Test HTTPS
AUTOBOT_HTTP_PROTOCOL=https python scripts/validate_configuration.py
```

## 🐳 Docker Integration

All Docker Compose files automatically use environment variables:

```yaml
# docker-compose.yml
services:
  autobot-redis:
    ports:
      - "${AUTOBOT_REDIS_PORT:-6379}:6379"

  autobot-backend:
    ports:
      - "${AUTOBOT_BACKEND_PORT:-8001}:8001"
```

## 🔍 Troubleshooting

### Check Current Configuration
```bash
python -c "from src.config import *; print(f'Backend: {API_BASE_URL}'); print(f'Ollama: {OLLAMA_URL}')"
```

### Verify Environment Variables
```bash
env | grep AUTOBOT_
```

### Test Docker Configuration
```bash
docker-compose -f docker/compose/docker-compose.hybrid.yml config
```

### Reset to Defaults
```bash
unset $(env | grep AUTOBOT_ | cut -d= -f1)
```

## 📝 Best Practices

1. **Use .env files** for persistent configuration
2. **Test changes** with the validation script
3. **Document custom setups** for your team
4. **Use meaningful ports** that don't conflict
5. **Secure protocols** in production (HTTPS/WSS)
6. **Backup configurations** before major changes

## 🎯 Advanced Usage

### Multiple Environments
```bash
# development.env
AUTOBOT_HTTP_PROTOCOL=http
AUTOBOT_BACKEND_PORT=8001

# production.env
AUTOBOT_HTTP_PROTOCOL=https
AUTOBOT_BACKEND_PORT=443

# Load specific environment
source production.env && ./run_agent.sh
```

### Service Discovery Integration
```bash
# Dynamic service discovery
export AUTOBOT_OLLAMA_HOST=$(consul-template -template="{{service \"ollama\"}}")
export AUTOBOT_REDIS_HOST=$(kubectl get service redis -o jsonpath='{.spec.clusterIP}')
```

---

This configuration system provides maximum flexibility while maintaining simplicity. All services can be moved, scaled, and configured independently without code changes! 🎉
