# AutoBot Phase 5 - Developer Setup Guide
**Complete Developer Onboarding for Distributed Multi-Modal AI System**

Generated: `2025-09-10`  
Setup Time: **~25 minutes** (fully automated)  
Difficulty: **Intermediate** (automated scripts handle complexity)

## Quick Start (TL;DR)

For developers who just want to get started immediately:

```bash
# 1. Clone repository
git clone https://github.com/your-org/AutoBot.git
cd AutoBot

# 2. Run automated setup (handles everything)
bash setup.sh --full

# 3. Start development environment
scripts/start-services.sh start

# 4. Access development interface
# SLM Orchestration: https://172.16.168.19/orchestration
# User Frontend: https://172.16.168.21
# Backend API: https://172.16.168.20:8443/docs
# VNC Desktop: http://127.0.0.1:6080
```

**That's it!** Services are managed via SLM orchestration, CLI wrapper (scripts/start-services.sh), or systemctl. See [Service Management Guide](SERVICE_MANAGEMENT.md) for complete documentation.

## Prerequisites

### System Requirements

**Minimum Requirements**:
- **OS**: Windows 11 with WSL2 (Ubuntu 22.04 LTS)
- **CPU**: Intel 8-core (Intel Core Ultra 9 185H recommended for NPU)
- **RAM**: 16GB (32GB recommended)
- **Storage**: 100GB free space (SSD recommended)
- **Network**: Broadband internet for model downloads

**Optimal Hardware** (for best performance):
- **CPU**: Intel Core Ultra 9 185H (22 cores) with NPU (AI Boost)
- **GPU**: NVIDIA RTX 4070 (RTX series with 8GB+ VRAM)
- **RAM**: 32GB DDR5
- **Storage**: 500GB NVMe SSD
- **Network**: Gigabit ethernet for VM communication

### Software Prerequisites

```bash
# Install on WSL2 Ubuntu 22.04
sudo apt update && sudo apt install -y \
    git curl wget unzip \
    python3 python3-pip python3-venv \
    nodejs npm \
    docker.io docker-compose-v2 \
    redis-tools \
    nginx \
    openssh-server \
    ansible

# Install Python dependencies manager
pip3 install --user pipenv poetry

# Install Node.js LTS (if needed)
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installations
python3 --version  # Should be 3.10+
node --version     # Should be 18+
docker --version   # Should be 24+
```

## Understanding the Architecture

Before diving into setup, it's crucial to understand why AutoBot uses a distributed architecture:

### Why 6 Virtual Machines?

**Problem Solved**: Environment conflicts between Python/Node.js dependencies, GPU resource contention, and service isolation needs.

**Architecture Benefits**:
1. **Dependency Isolation**: Each VM has optimized environment for its specific role
2. **Resource Optimization**: GPU/NPU/CPU resources distributed optimally  
3. **Fault Tolerance**: One service failure doesn't cascade to others
4. **Scalability**: Each tier can be scaled independently
5. **Security**: Network-level isolation between services

```
Physical Host (WSL2)     ←→    VM1: Frontend (Vue.js)
├─ FastAPI Backend              ├─ Modern web interface
├─ Ollama LLM Service          └─ Real-time dashboard
├─ VNC Desktop Access
└─ System Integration    ←→    VM2: NPU Worker
                                ├─ Intel NPU acceleration  
                                ├─ GPU processing fallback
                                └─ Computer vision tasks

    VM3: Redis Stack     ←→    VM4: AI Orchestrator
    ├─ 11 specialized DBs       ├─ Multi-provider LLM routing
    ├─ 13,383 knowledge vectors ├─ Model caching & optimization
    └─ Session management       └─ Intelligent failover

                         ←→    VM5: Browser Automation
                                ├─ Playwright multi-browser
                                ├─ Screenshot & interaction
                                └─ Web automation tasks
```

## Automated Setup Process

### Step 1: Repository Setup

```bash
# Clone the repository
git clone https://github.com/your-org/AutoBot.git
cd AutoBot

# Verify you're in the right location
ls -la
# You should see: setup.sh, scripts/, docs/, etc.
```

### Step 2: Choose Setup Mode

The `setup.sh` script supports three modes:

```bash
# Full setup (recommended for first time)
bash setup.sh --full
# - Sets up all 6 VMs
# - Installs all dependencies
# - Downloads AI models (3-5GB)
# - Configures networking
# - Generates SSH keys
# - Sets up development environment

# Minimal setup (for quick testing)
bash setup.sh --minimal  
# - Core services only
# - Minimal dependencies
# - No model downloads
# - Basic configuration

# Distributed setup (for production)  
bash setup.sh --distributed
# - Production-ready configuration
# - Security hardening
# - Monitoring setup
# - Backup configuration
```

### Step 3: What Happens During Setup

The setup script performs these operations automatically:

```bash
echo "=== AutoBot Phase 5 Setup Process ==="

# 1. Environment Validation (2 min)
echo "Phase 1: Validating system requirements..."
- Check WSL2 version and features
- Verify hardware capabilities (CPU, RAM, GPU)
- Test internet connectivity
- Check available disk space

# 2. Dependency Installation (5 min)
echo "Phase 2: Installing core dependencies..."
- Python 3.10+ with virtual environments
- Node.js LTS with npm/yarn
- Docker with Docker Compose V2
- Redis tools and client libraries
- SSH server and key generation

# 3. VM Infrastructure Setup (8 min)
echo "Phase 3: Configuring distributed infrastructure..."
- Create VM network configuration (172.16.168.0/24)
- Generate SSH keys for inter-VM communication
- Configure firewall rules for security
- Set up VM-to-VM networking
- Install VM-specific dependencies

# 4. Service Configuration (5 min)  
echo "Phase 4: Configuring services..."
- Redis Stack with 11 databases
- Nginx reverse proxy setup
- VNC desktop configuration
- OpenVINO NPU driver setup (if available)
- GPU passthrough configuration

# 5. AI Model Setup (3-5 min)
echo "Phase 5: Downloading AI models..."
- Ollama model downloads (tinyllama, phi)
- Sentence transformer embeddings
- NPU-optimized models (if supported)
- Model cache initialization

# 6. Validation & Testing (2 min)
echo "Phase 6: Validating installation..."
- Test all VM connectivity
- Verify service health checks
- Run basic functionality tests
- Generate setup report

echo "Setup completed successfully!"
echo "Total setup time: ~25 minutes"
```

### Step 4: Post-Setup Verification

After setup completes, verify everything works:

```bash
# Check all services are running
scripts/start-services.sh status

# Or check individual services
systemctl status autobot-backend
systemctl status autobot-celery
systemctl status redis-stack-server
systemctl status ollama

# Or use SLM GUI
scripts/start-services.sh gui
# Visit: https://172.16.168.19/orchestration

# Expected services:
✓ Main Backend API      (https://172.16.168.20:8443)
✓ Celery Worker         (Background tasks)
✓ Frontend Service      (https://172.16.168.21)
✓ NPU Worker           (http://172.16.168.22:8081)
✓ Redis Stack          (tcp://172.16.168.23:6379)
✓ AI Orchestrator      (http://172.16.168.24:8080)
✓ Browser Service      (http://172.16.168.25:3000)
✓ Ollama LLM           (http://127.0.0.1:11434)

System Status: ALL SERVICES HEALTHY ✓
```

## Development Workflow

### Starting Development Environment

**Recommended: CLI Wrapper**
```bash
# Start all services
scripts/start-services.sh start

# Start specific service for development
scripts/start-services.sh start backend

# Stop services
scripts/start-services.sh stop

# Restart after code changes
scripts/start-services.sh restart backend

# Follow logs (live)
scripts/start-services.sh logs backend
```

**Alternative: Direct systemctl**
```bash
# Start service
sudo systemctl start autobot-backend

# Restart after code changes
sudo systemctl restart autobot-backend

# Follow logs
journalctl -u autobot-backend -f
```

**Alternative: SLM GUI (Best for operations)**
```bash
scripts/start-services.sh gui
# Or visit: https://172.16.168.19/orchestration
```

See [Service Management Guide](SERVICE_MANAGEMENT.md) for complete documentation.

### Development URLs

Once services are started, these URLs will be available:

```yaml
# Primary interfaces
SLM_Orchestration: "https://172.16.168.19/orchestration"  # Service management GUI
Frontend_UI: "https://172.16.168.21"                      # User interface (production)
Frontend_Dev: "http://172.16.168.21:5173"                 # Development server (if running)
Backend_API: "https://172.16.168.20:8443"                 # FastAPI backend (TLS)
API_Docs: "https://172.16.168.20:8443/docs"               # Interactive API documentation

# Administrative interfaces
VNC_Desktop: "http://127.0.0.1:6080"          # Full desktop access
Redis_Insight: "http://172.16.168.23:8002"   # Database management
System_Health: "https://172.16.168.21/health" # System monitoring

# Development tools (backend endpoints)
WebSocket_Test: "https://172.16.168.20:8443/ws-test"  # WebSocket testing
File_Manager: "https://172.16.168.20:8443/files"      # File browser
Log_Viewer: "https://172.16.168.20:8443/logs"         # Real-time logs
```

### Hot Reload Development

The development environment supports hot reloading for rapid iteration:

**Frontend (Vue.js)**:
```bash
# Frontend changes auto-reload in browser
cd autobot-vue
npm run dev  # Runs automatically with --dev flag

# Files watched for changes:
autobot-user-frontend/src/**/*.vue     # Vue components
autobot-user-frontend/src/**/*.ts      # TypeScript files  
autobot-user-frontend/src/**/*.js      # JavaScript files
autobot-user-frontend/src/**/*.css     # Stylesheets
```

**Backend (FastAPI)**:
```bash
# For development with hot reload, run in foreground
cd autobot-user-backend
source venv/bin/activate
python backend/main.py

# Or restart systemd service after changes
sudo systemctl restart autobot-backend

# Files watched for changes (if running in foreground):
backend/**/*.py              # Python source files
src/**/*.py                  # Core application files
config/**/*.yaml             # Configuration files
```

### Making Code Changes

**Frontend Development**:
```bash
# Navigate to frontend directory
cd autobot-vue

# Install new dependencies (if needed)
npm install new-package

# Common development tasks
npm run lint        # Check code style
npm run test        # Run unit tests
npm run build       # Build for production
```

**Backend Development**:  
```bash
# Navigate to backend directory
cd backend

# Work with Python virtual environment
source venv/bin/activate  # Activate if not already active

# Install new dependencies (if needed)
pip install new-package
pip freeze > requirements.txt  # Update requirements

# Common development tasks
python -m pytest tests/       # Run tests
black src/ backend/          # Format code
flake8 src/ backend/         # Check code style
```

**Database Development**:
```bash
# Connect to Redis for debugging
redis-cli -h 172.16.168.23 -p 6379

# Browse databases
SELECT 0  # Main application data
KEYS *    # List all keys
SELECT 8  # Vector embeddings
FT.INFO knowledge_idx  # Vector database info

# Redis Insight GUI
# Visit: http://172.16.168.23:8002
```

## Configuration Management

### Environment Variables

AutoBot uses a hierarchical configuration system:

```bash
# Configuration priority (highest to lowest):
1. .env.local                 # Local developer overrides  
2. .env.development           # Development environment
3. .env                       # Default configuration
4. config/config.yaml         # Structured configuration
```

**Key Environment Variables**:
```bash
# Core services
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8001
REDIS_HOST=172.16.168.23
REDIS_PORT=6379

# AI Configuration  
OPENAI_API_KEY=sk-...        # OpenAI API key
ANTHROPIC_API_KEY=sk-ant-... # Anthropic API key
OLLAMA_HOST=127.0.0.1
OLLAMA_PORT=11434

# Multi-modal AI
TF_USE_LEGACY_KERAS=1        # Fix Keras compatibility
KERAS_BACKEND=tensorflow
CUDA_VISIBLE_DEVICES=0

# Development
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_HOT_RELOAD=true
```

### Service Configuration

**VM Configuration** (`config/vm_config.yaml`):
```yaml
vms:
  frontend:
    host: "172.16.168.21"
    services: ["nginx", "vue-dev-server"]
    ports: [80, 443, 5173]

  npu_worker:  
    host: "172.16.168.22"
    services: ["npu-service", "gpu-fallback"]
    ports: [8081, 8082]
    hardware: ["intel_npu", "nvidia_gpu"]

  redis_stack:
    host: "172.16.168.23"
    services: ["redis-server", "redisinsight"]
    ports: [6379, 8002]
    databases: 11

  ai_orchestrator:
    host: "172.16.168.24"
    services: ["model-orchestrator", "inference-cache"]
    ports: [8080, 8083, 8084]

  browser_service:
    host: "172.16.168.25"
    services: ["playwright-api", "browser-pool"]  
    ports: [3000, 3001, 3002]
```

## Troubleshooting Development Issues

### Common Setup Problems

**Problem: Setup script fails with "Permission denied"**
```bash
# Solution: Fix permissions
chmod +x setup.sh scripts/start-services.sh
sudo usermod -aG docker $USER
# Logout/login or restart WSL2
```

**Problem: "Cannot connect to Redis"**
```bash
# Check Redis service status
docker ps | grep redis
redis-cli -h 172.16.168.23 ping

# If not responding, restart Redis
docker restart autobot-redis
```

**Problem: Frontend shows "Network Error" for API calls**
```bash
# Check backend is running
curl -k https://172.16.168.20:8443/api/health

# Check systemd service status
systemctl status autobot-backend

# Restart backend if needed
sudo systemctl restart autobot-backend

# Check frontend configuration
cat autobot-user-frontend/src/config/ssot-config.ts
```

**Problem: "Module not found" errors in Python**
```bash
# Ensure virtual environment is active
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Check Python path
echo $PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

**Problem: NPU worker not responding**  
```bash
# Check NPU hardware support
lspci | grep -i accelerator

# Check OpenVINO installation
python3 -c "from openvino.runtime import Core; print(Core().available_devices)"

# Restart NPU service
sudo systemctl restart autobot-npu-worker
```

### Development Debugging

**Enable Debug Mode**:
```bash
# Enable detailed logging in .env file
cd autobot-user-backend
echo "AUTOBOT_LOG_LEVEL=DEBUG" >> .env

# Restart backend service
sudo systemctl restart autobot-backend

# Or run in foreground for immediate log output
source venv/bin/activate
python backend/main.py
```

**View Real-time Logs**:
```bash
# Backend logs (systemd)
journalctl -u autobot-backend -f

# Celery worker logs
journalctl -u autobot-celery -f

# Frontend logs (browser console)
# Open browser DevTools -> Console

# Redis logs (systemd)
journalctl -u redis-stack-server -f

# All services at once
journalctl -u autobot-backend -u autobot-celery -u redis-stack-server -f
```

**Debug WebSocket Connections**:
```javascript
// Test WebSocket connection in browser console
const ws = new WebSocket('wss://172.16.168.20:8443/ws/test');
ws.onopen = () => console.log('WebSocket connected');
ws.onmessage = (event) => console.log('Received:', event.data);
ws.onerror = (error) => console.log('WebSocket error:', error);
```

**Debug Multi-modal AI Processing**:
```bash
# Test AI processing pipeline
curl -k -X POST https://172.16.168.20:8443/api/multimodal/process \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "text": "Test AI processing",
      "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    },
    "processing_options": {
      "confidence_threshold": 0.5
    }
  }'
```

## Advanced Development Topics

### Adding New API Endpoints

**1. Create API module**:
```python  
# autobot-user-backend/api/your_feature.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/your_feature", tags=["Your Feature"])

class YourRequest(BaseModel):
    param1: str
    param2: int = 10

@router.post("/endpoint")
async def your_endpoint(request: YourRequest):
    """
    Your endpoint description.

    Args:
        request: Your request parameters

    Returns:
        dict: Response data

    Raises:
        HTTPException: If processing fails
    """
    try:
        # Your logic here
        return {"success": True, "data": {"result": "processed"}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**2. Register router**:
```python
# backend/app_factory.py or fast_app_factory_fix.py
from backend.api.your_feature import router as your_feature_router

def create_app():
    app = FastAPI(title="AutoBot API")
    app.include_router(your_feature_router)
    return app
```

### Adding Frontend Components

**1. Create Vue component**:
```vue
<!-- autobot-user-frontend/src/components/YourComponent.vue -->
<template>
  <div class="your-component">
    <h2>{{ title }}</h2>
    <button @click="handleAction" :disabled="loading">
      {{ loading ? 'Processing...' : 'Submit' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useApiService } from '@/services/ApiService'

interface Props {
  title: string
}

const props = defineProps<Props>()
const loading = ref(false)
const api = useApiService()

const handleAction = async () => {
  loading.value = true
  try {
    const result = await api.post('/your_feature/endpoint', {
      param1: 'value',
      param2: 42
    })
    console.log('Success:', result)
  } catch (error) {
    console.error('Error:', error)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.your-component {
  padding: 1rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
}
</style>
```

**2. Add to router**:
```typescript
// autobot-user-frontend/src/router/index.ts
import YourComponent from '@/components/YourComponent.vue'

const routes = [
  // ... existing routes
  {
    path: '/your-feature',
    name: 'YourFeature',
    component: YourComponent,
    meta: { requiresAuth: true }
  }
]
```

### Extending Multi-Modal AI

**1. Add new modality processor**:
```python
# src/multimodal/your_processor.py
from typing import Dict, Any, Optional
from .base_processor import BaseModalityProcessor

class YourModalityProcessor(BaseModalityProcessor):
    """Process your custom modality (e.g., 3D data, sensor readings)."""

    def __init__(self):
        super().__init__()
        self.supported_formats = ['custom_format_1', 'custom_format_2']

    async def process(
        self,
        input_data: bytes,
        format_type: str,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process your custom modality.

        Args:
            input_data: Raw input bytes
            format_type: Input format identifier  
            options: Processing options

        Returns:
            Dict containing analysis results
        """
        if format_type not in self.supported_formats:
            raise ValueError(f"Unsupported format: {format_type}")

        # Your processing logic here
        result = {
            "modality": "your_modality",
            "confidence": 0.95,
            "analysis": {
                "feature_1": "detected_value",
                "feature_2": 42.0
            },
            "processing_time": 0.5
        }

        return result
```

**2. Register processor**:
```python
# src/multimodal/registry.py
from .your_processor import YourModalityProcessor

MODALITY_PROCESSORS = {
    'text': TextProcessor(),
    'image': ImageProcessor(),
    'audio': AudioProcessor(),
    'your_modality': YourModalityProcessor(),  # Add here
}
```

## Performance Optimization

### Development Performance Tips

**1. Fast Development Restarts**:
```bash
# Restart specific service after code changes
sudo systemctl restart autobot-backend

# Or use CLI wrapper
scripts/start-services.sh restart backend

# Check status
scripts/start-services.sh status
```

**2. Database Optimization**:
```bash
# Clear development cache for fresh start
redis-cli -h 172.16.168.23 FLUSHDB 3

# Optimize knowledge base index
curl -k -X POST https://172.16.168.20:8443/api/knowledge_base/optimize
```

**3. AI Model Caching**:
```bash
# Pre-load models for faster development
curl -X POST http://172.16.168.24:8080/models/preload \
  -H "Content-Type: application/json" \
  -d '{"models": ["gpt-3.5-turbo", "claude-3-sonnet"]}'
```

### Production Readiness Checklist

Before deploying to production:

```bash
# 1. Run comprehensive tests
python -m pytest tests/ --cov=src --cov-report=html

# 2. Security scan
bash scripts/security_scan.sh

# 3. Performance benchmark
bash scripts/performance_test.sh

# 4. Documentation check
bash scripts/validate_documentation.sh

# 5. Deploy via Ansible
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-native-services.yml

# 6. Verify deployment via SLM GUI
# Visit: https://172.16.168.19/orchestration
```

## Getting Help

### Documentation Resources

- **Service Management**: `docs/developer/SERVICE_MANAGEMENT.md` - Complete service management guide
- **API Documentation**: https://172.16.168.20:8443/docs (when running)
- **Architecture Guide**: `docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md`
- **Troubleshooting**: `docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING.md`
- **Security Guide**: `docs/security/SECURITY_IMPLEMENTATION.md`

### Development Tools

**Browser Extensions** (recommended):
- Vue.js DevTools - For Vue component debugging
- React DevTools - For any React components
- Redux DevTools - For state management debugging

**IDE Setup** (VS Code recommended):
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "typescript.preferences.includePackageJsonAutoImports": "auto",
  "vue.server.hybridMode": true
}
```

**Recommended Extensions**:
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Vue Language Features (Vue.volar)
- TypeScript Vue Plugin (Vue.vscode-typescript-vue-plugin)
- Docker (ms-azuretools.vscode-docker)

### Support Channels

**Internal Support**:
- Check logs: `journalctl -u autobot-backend -f` or `scripts/start-services.sh logs backend`
- Health check: `curl -k https://172.16.168.20:8443/api/health`
- System status: `scripts/start-services.sh status` or visit SLM GUI

**Community Resources**:
- GitHub Issues: For bug reports and feature requests
- Developer Slack: #autobot-development channel
- Wiki: Internal documentation and examples

---

**Next Steps After Setup**:
1. 🎯 **Try the Quick Tutorial**: Run through basic chat and knowledge base features
2. 🧪 **Explore Examples**: Check `examples/` directory for code samples  
3. 🔧 **Make Your First Change**: Add a simple API endpoint or frontend component
4. 📚 **Read Architecture Docs**: Understand the distributed system design
5. 🚀 **Build Something Cool**: Use the multi-modal AI capabilities for your use case

**Welcome to AutoBot Phase 5 Development!** 🤖✨
