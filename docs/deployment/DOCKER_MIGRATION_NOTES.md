# Docker Migration Dependency Cleanup Notes

## Components Moving to Docker

### AI Stack Container (`autobot-ai-stack`)
These dependencies will be moved to Docker and can be removed from local pip:

#### LangChain & LlamaIndex Stack
- `langchain==0.3.26`
- `langchain-core==0.3.68` 
- `llama-index==0.12.48`
- `llama-index-core==0.13.1` (current conflicted version)
- `llama-index-vector-stores-chroma==0.2.2`
- `llama-index-embeddings-ollama==0.6.0`
- `llama-index-llms-ollama==0.6.2`
- `llama-index-*` (all llama-index packages)

#### Vector Database & Embeddings
- `chromadb==1.0.16` (current version, conflicts with llama-index)
- `sentence-transformers`
- `transformers==4.52.4`
- `tokenizers==0.20.3` (downgraded due to conflicts)
- `huggingface-hub==0.34.4`

#### AI Processing Dependencies
- `numpy==1.26.4` (downgraded for redisvl compatibility)
- `tensorflow==2.17.1` (if used for embeddings)
- `torch` (if used for local models)
- `onnxruntime==1.22.0`

#### Text Processing
- `nltk==3.9.1`
- `spacy` (if installed)
- `tiktoken==0.11.0`

#### HTTP/API for AI Services
- `aiohttp==3.12.15`
- `httpx==0.28.1`
- `httpcore==1.0.9`

#### Other AI-Related
- `async-timeout==4.0.3` (downgraded for langchain)
- `packaging==24.2` (downgraded for langchain-core)
- `protobuf==5.29.5` (causes tensorflow conflicts)
- `pydantic==2.11.7` (used by both langchain and llama-index)

## Components Staying on Host

### Core AutoBot (Native Python)
- `fastapi` - Main API server (stays native for OS access)
- `uvicorn` - ASGI server (stays native)
- `redis` - Client only (Redis server already in Docker)
- `redisvl==0.8.0` - Vector operations client
- `psutil` - System monitoring (needs native access)
- `python-dotenv` - Configuration (lightweight)

### Command Execution & System Access
- `subprocess` - Built-in (for command execution)
- `pathlib` - Built-in (file operations)
- `sqlite3` - Built-in (local databases)
- `requests` - HTTP client (for external APIs if needed)

### Security & System Tools (Native)
- All Kali Linux security tools (nmap, masscan, etc.)
- System utilities (ps, df, netstat, etc.)
- Development tools (git, npm, pip)

## Docker Communication
- Host AutoBot ↔ AI Container: HTTP/REST on localhost
- Host AutoBot ↔ Redis: Docker network bridge
- Host AutoBot ↔ NPU Worker: HTTP/WebSocket to Windows host

## Cleanup Commands (After Docker Migration)
```bash
# Remove AI stack dependencies
pip uninstall langchain langchain-core llama-index llama-index-core chromadb
pip uninstall transformers tokenizers huggingface-hub
pip uninstall tensorflow torch onnxruntime nltk tiktoken
pip uninstall aiohttp httpx sentence-transformers

# Keep core dependencies
pip list | grep -E "(fastapi|uvicorn|redis|psutil|requests)"
```

## Migration Priority
1. **Phase 1**: Move LangChain + LlamaIndex to resolve dependency conflicts
2. **Phase 2**: Move vector databases (ChromaDB)
3. **Phase 3**: Move model dependencies (transformers, tokenizers)
4. **Phase 4**: Clean up local environment

## Container Resource Requirements
- **Memory**: 8GB+ for large models, 4GB for basic AI operations
- **CPU**: Multi-core recommended for parallel agent processing
- **Storage**: 20GB+ for models and vector indexes
- **Network**: Internal bridge to host AutoBot process