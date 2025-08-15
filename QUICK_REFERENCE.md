# AutoBot Quick Reference Card

## 🚀 **Essential Commands**

```bash
# System Control
./run_agent.sh                    # Start full system
./run_agent.sh --test-mode       # Test mode with validation
docker ps | grep autobot         # Check running containers
docker logs autobot-backend -f   # View backend logs

# Development
source venv/bin/activate         # Activate Python environment
python main.py --dev            # Development mode with auto-reload
cd autobot-vue && npm run dev   # Frontend development server
```

## 🤖 **Agent Quick Reference**

### **Chat with AutoBot**
```python
# Simple chat
"Hello AutoBot"                  # Basic conversation

# Complex request triggering multi-agent workflow
"Find network scanning tools and help me install them"
```

### **Agent Types by Model Size**
```
1B Models (Fast):     chat, system_commands, knowledge_retrieval
3B Models (Smart):    rag, research, orchestrator
Special (Tools):      security_scanner, network_discovery, terminal
```

## 🔧 **Configuration**

### **Key Configuration Files**
```
configs/base_config.yaml         # Main configuration
configs/agents/                  # Agent-specific configs
.env                            # Environment variables
```

### **Important Ports**
```
5173  - Vue Frontend
8001  - FastAPI Backend
6379  - Redis Stack
8080  - AI Stack (Chat, RAG)
8081  - NPU Worker
3000  - Playwright Service
6080  - NoVNC (Desktop Streaming)
```

## 🛡️ **Security Levels**

```python
# Agent Risk Classifications
LOW_RISK = ["chat", "kb_librarian", "rag"]              # Safe
MEDIUM_RISK = ["system_commands", "research"]           # Controlled
HIGH_RISK = ["security_scanner", "network_discovery"]   # Approval needed
CRITICAL_RISK = ["interactive_terminal"]                # Human oversight
```

## 📊 **Health Checks**

```bash
# System Health
curl http://localhost:8001/api/system/health

# Memory System
curl http://localhost:8001/api/memory/health

# Workflow Status
curl http://localhost:8001/api/workflow/workflows

# Agent Status
curl http://localhost:8001/api/agents/health
```

## 🧪 **Testing**

```bash
# Run all tests
python -m pytest tests/ -v

# Test categories
python -m pytest tests/unit/ -v        # Unit tests
python -m pytest tests/integration/ -v # Integration tests
python -m pytest tests/security/ -v    # Security tests
python -m pytest tests/e2e/ -v        # End-to-end tests

# Phase 9 validation
python test_phase9_ai.py              # Multi-modal AI tests
python test_npu_worker.py            # NPU acceleration tests
```

## 🔄 **Common Workflows**

### **Deploy New Agent**
1. Create agent extending `BaseAgent`
2. Add to `src/agents/__init__.py`
3. Update orchestrator registry
4. Create tests in `tests/unit/`
5. Update documentation

### **Add API Endpoint**
1. Create route in `backend/api/`
2. Add request/response models
3. Update frontend service
4. Add tests
5. Update API documentation

### **Emergency Recovery**
```bash
# System recovery
pkill -f uvicorn
docker compose -f docker/compose/docker-compose.hybrid.yml down
./scripts/setup/setup_agent.sh --force-reinstall
./run_agent.sh

# Database recovery
cp data/knowledge_base.db.backup data/knowledge_base.db
cp data/memory_system.db.backup data/memory_system.db
```

## 📚 **Key Documentation**

- **[Agent System Guide](docs/AGENT_SYSTEM_GUIDE.md)** - Complete agent development
- **[Enterprise Deployment](docs/deployment/ENTERPRISE_DEPLOYMENT_STRATEGY.md)** - Production rollout
- **[CLAUDE.md](CLAUDE.md)** - AI-assisted development rules
- **[Executive Summary](EXECUTIVE_SUMMARY.md)** - Business overview

## 🎯 **Performance Tips**

1. **Use appropriate agent tiers** - 1B for speed, 3B for complexity
2. **Enable NPU acceleration** - 5-10x speedup for inference
3. **Cache frequently used data** - Redis for performance
4. **Batch similar requests** - Reduce overhead
5. **Monitor resource usage** - Prevent bottlenecks

## 🚨 **Troubleshooting**

### **Backend Won't Start**
```bash
lsof -ti:8001 | xargs kill -9    # Kill process on port
export PYTHONPATH="$PWD:$PYTHONPATH"  # Fix import errors
```

### **Redis Connection Failed**
```bash
docker start autobot-redis        # Start Redis container
docker logs autobot-redis         # Check Redis logs
```

### **NPU Not Detected**
```bash
docker exec autobot-npu-worker python -c "import openvino"
clinfo                           # Check OpenCL devices
```

## 🌟 **AutoBot Philosophy**

"True autonomous AI that bridges the gap between reactive assistants and artificial general intelligence."

**Remember**: AutoBot is not just software—it's a revolutionary platform that redefines what's possible with AI.
