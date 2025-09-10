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
```bash
./setup_agent.sh
```

This will:
- ✅ Install Python 3.10.13 with pyenv
- ✅ Set up virtual environment with all dependencies
- ✅ Install Docker and required containers
- ✅ Download required Ollama models (1B and 3B)
- ✅ Build Vue.js frontend
- ✅ Verify all components

### 3. Verify Installation
```bash
./verify_installation.sh
```

### 4. Start the System
```bash
./run_agent.sh
```

## Multi-Agent Models Required

The setup script will automatically download uncensored models for unrestricted capabilities:

### Core Uncensored Models
- **artifish/llama3.2-uncensored:1b** - Chat Agent & System Commands (1.2GB)
- **artifish/llama3.2-uncensored:3b** - Orchestrator & RAG Agent (3.5GB)
- **nomic-embed-text:latest** - Knowledge Base Embeddings (274MB)

### Fallback Models
- **artifish/llama3.2-uncensored:latest** - General uncensored fallback (2.0GB)
- **llama3.2:1b-instruct-q4_K_M** - Standard 1B fallback (1.2GB)
- **llama3.2:3b-instruct-q4_K_M** - Standard 3B fallback (3.5GB)

**Total Download Size**: ~7GB

## Agent Architecture Overview

```
Agent Orchestrator (3B) → Routes requests to specialized agents
├── Chat Agent (1B) → Quick conversations
├── System Commands Agent (1B) → Safe command generation  
├── RAG Agent (3B) → Document synthesis
├── Knowledge Retrieval Agent (1B) → Fast fact lookup
└── Research Agent (3B+Web) → Web research + synthesis
```

## Manual Model Installation

If automatic installation fails:

```bash
# Essential uncensored models
ollama pull artifish/llama3.2-uncensored:1b
ollama pull artifish/llama3.2-uncensored:3b
ollama pull nomic-embed-text:latest

# General uncensored fallback
ollama pull artifish/llama3.2-uncensored:latest

# Standard fallback models (if uncensored not available)
ollama pull llama3.2:1b-instruct-q4_K_M
ollama pull llama3.2:3b-instruct-q4_K_M
```

## Configuration Override

Set specific models via environment variables:

```bash
export AUTOBOT_MODEL_CHAT="artifish/llama3.2-uncensored:1b"
export AUTOBOT_MODEL_ORCHESTRATOR="artifish/llama3.2-uncensored:3b"
export AUTOBOT_MODEL_RAG="artifish/llama3.2-uncensored:3b"
export AUTOBOT_MODEL_SYSTEM_COMMANDS="artifish/llama3.2-uncensored:1b"
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
   - Use smaller uncensored models:
     ```bash
     export AUTOBOT_MODEL_ORCHESTRATOR="artifish/llama3.2-uncensored:1b"
     export AUTOBOT_MODEL_RAG="artifish/llama3.2-uncensored:1b"
     ```

4. **Docker issues**
   ```bash
   sudo systemctl start docker
   ./setup_agent.sh  # Re-run setup
   ```

### Verification Commands

```bash
# Check Ollama models
ollama list

# Check Docker containers
docker ps

# Check Python dependencies
source venv/bin/activate
python3 -c "from src.agents import get_agent_orchestrator; print('✅ Multi-agent ready')"

# Check configuration
python3 -c "from src.config import global_config_manager; print(f'Chat model: {global_config_manager.get_task_specific_model(\"chat\")}')"
```

## Performance Expectations

| Agent | Model Size | Response Time | Memory Usage |
|-------|------------|---------------|-------------|
| Chat Agent | 1B | 200-500ms | 1.2GB |
| System Commands | 1B | 300-600ms | 1.2GB |
| Knowledge Retrieval | 1B | 100-300ms | 1.2GB |
| RAG Agent | 3B | 800-1500ms | 3.5GB |
| Orchestrator | 3B | 1-2s | 3.5GB |

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
- `src/agents/agent_orchestrator.py` - Routing logic
- `src/config.py` - Model assignments and configuration

---

**Ready to experience intelligent multi-agent AI assistance!** 🤖✨