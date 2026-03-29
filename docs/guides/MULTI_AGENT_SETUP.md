# AutoBot Multi-Agent Architecture Setup Guide

## Quick Start Installation

### Prerequisites
- WSL2 or Linux environment
- Internet connection for downloading models
- At least 8GB RAM (16GB recommended)
- 20GB free disk space

### 1. Install Ollama (Required)
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Run Complete Setup

**Option A: Ansible Deployment (Recommended for Production)**
```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml
```

**Option B: Local Development Setup**
```bash
./run_agent.sh
```

This will:
- Set up virtual environment with all dependencies
- Download required Ollama models (6-tier architecture)
- Build Vue.js frontend
- Start all services

### 3. Verify Installation
```bash
./verify_installation.sh
```

### 4. Start the System
```bash
./run_agent.sh
```

## 6-Tier Model Architecture

The setup script will automatically download models for the 6-tier architecture:

### Required Models

| Tier | Model | Size | Purpose |
|------|-------|------|---------|
| Routing | `llama3.2:1b` | 1.2GB | Orchestrator, request routing |
| Classification | `gemma2:2b` | 1.8GB | Intent detection, category assignment |
| Light Processing | `phi3:mini` | 2.3GB | Extraction, formatting |
| Instruction | `mistral:7b-instruct` | 4.1GB | RAG, step execution |
| System | `dolphin-llama3:8b` | 4.7GB | Commands, security |
| Quality | `qwen3.5:9b` | 5.5GB | Chat, research, code |

### Embedding Model
- **nomic-embed-text:latest** - Knowledge Base Embeddings (274MB)

**Total Download Size**: ~20GB

## Agent Architecture Overview

```
Agent Orchestrator (llama3.2:1b) -> Routes requests to specialized agents
+-- Classification Agent (gemma2:2b) -> Intent detection
+-- Chat Agent (qwen3.5:9b) -> Quality conversations
+-- System Commands Agent (dolphin-llama3:8b) -> Safe command generation
+-- RAG Agent (mistral:7b-instruct) -> Document synthesis
+-- Knowledge Retrieval Agent (gemma2:2b) -> Fast fact lookup
+-- Research Agent (qwen3.5:9b) -> Web research + synthesis
```

## Manual Model Installation

If automatic installation fails:

```bash
# 6-tier models (all required)
ollama pull llama3.2:1b
ollama pull gemma2:2b
ollama pull phi3:mini
ollama pull mistral:7b-instruct
ollama pull dolphin-llama3:8b
ollama pull qwen3.5:9b

# Embedding model
ollama pull nomic-embed-text:latest
```

## Configuration Override

Set specific models via environment variables:

```bash
export AUTOBOT_MODEL_TIER_ROUTING="llama3.2:1b"
export AUTOBOT_MODEL_TIER_CLASSIFICATION="gemma2:2b"
export AUTOBOT_MODEL_TIER_LIGHT="phi3:mini"
export AUTOBOT_MODEL_TIER_INSTRUCTION="mistral:7b-instruct"
export AUTOBOT_MODEL_TIER_SYSTEM="dolphin-llama3:8b"
export AUTOBOT_MODEL_TIER_QUALITY="qwen3.5:9b"
```

## Troubleshooting

### Common Issues

1. **Ollama not found**
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   # Restart terminal after installation
   ```

2. **Models fail to download**
   - Check internet connection
   - Manually download models one by one
   - Consider using smaller models if disk space is limited

3. **Memory issues**
   - Close other applications
   - Use only lower-tier models for development:
     ```bash
     export AUTOBOT_MODEL_TIER_QUALITY="mistral:7b-instruct"
     export AUTOBOT_MODEL_TIER_SYSTEM="mistral:7b-instruct"
     ```

4. **Docker issues**
   ```bash
   sudo systemctl start docker
   # Use Ansible playbooks (see autobot-slm-backend/ansible/) or ./run_agent.sh
   ```

### Verification Commands

```bash
# Check Ollama models
ollama list

# Check Docker containers
docker ps

# Check Python dependencies
source venv/bin/activate
python3 -c "from src.agents import get_agent_orchestrator; print('Multi-agent ready')"

# Check configuration
python3 -c "from src.config import global_config_manager; print(f'Chat model: {global_config_manager.get_task_specific_model(\"chat\")}')"
```

## Performance Expectations

| Agent | Model | Tier | Response Time | Memory Usage |
|-------|-------|------|---------------|-------------|
| Orchestrator | llama3.2:1b | Routing | 100-200ms | 1.2GB |
| Classification | gemma2:2b | Classification | 150-300ms | 1.8GB |
| Chat Agent | qwen3.5:9b | Quality | 500-1500ms | 5.5GB |
| System Commands | dolphin-llama3:8b | System | 400-800ms | 4.7GB |
| Knowledge Retrieval | gemma2:2b | Classification | 100-300ms | 1.8GB |
| RAG Agent | mistral:7b-instruct | Instruction | 800-1500ms | 4.1GB |

**Note**: Models share memory when using the same base model.

## Next Steps

1. **Start the system**: `./run_agent.sh`
2. **Access the interface**: `http://localhost:8001`
3. **Test agents**: Try different types of requests to see routing
4. **Monitor performance**: Check logs and resource usage
5. **Customize**: Modify agent configurations in `src/config.py`

## Advanced Configuration

For advanced users, see:
- `docs/agents/multi-agent-architecture.md` - Complete architecture documentation
- `autobot-backend/agents/agent_orchestrator.py` - Routing logic
- `src/config.py` - Model assignments and configuration

---

**Ready to experience intelligent multi-agent AI assistance!**
