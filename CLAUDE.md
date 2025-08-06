# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoBot is an enterprise-grade autonomous AI platform that provides advanced task automation, knowledge management, and system interaction capabilities. Built with Vue 3 frontend and FastAPI backend, it features real-time monitoring, comprehensive knowledge management with template systems, and multi-LLM support (Ollama, OpenAI, Anthropic).

**Current Status**: Production-ready with Phase 4 complete
**Key Features**: GUI automation, RAG-powered knowledge base, voice interface, Redis-backed task orchestration

## Architecture

### Application Entry Points
- **Backend**: `main.py` → `backend/app_factory.py` (FastAPI application factory pattern)
- **Frontend**: `autobot-vue/` (Vue 3 + TypeScript + Vite)
- **Configuration**: `src/config.py` (centralized config management)

### Core Backend Modules (`src/`)
- `orchestrator.py`: Task planning with Redis-backed autonomous operation
- `llm_interface.py`: Multi-LLM support (Ollama, OpenAI, Anthropic, HuggingFace)
- `knowledge_base.py`: RAG system with ChromaDB vector storage + SQLite
- `worker_node.py`: Task execution engine with background processing
- `gui_controller.py`: GUI automation (PyAutoGUI, OCR with pytesseract)
- `diagnostics.py`: System health monitoring (CPU, RAM, GPU metrics)
- `event_manager.py`: WebSocket event streaming and Redis pub/sub
- `voice_interface.py`: Speech recognition and TTS capabilities

### API Structure (`backend/api/`)
- `chat.py`: Chat endpoints and conversation management
- `diagnostics.py`: System health and metrics endpoints
- `files.py`: File browser and management API
- `goal.py`: Goal submission and task planning
- `knowledge_base.py`: Knowledge CRUD operations
- `llm.py`: LLM configuration and model management

## Essential Commands

### Application Lifecycle
```bash
# Initial setup (creates venv, installs deps, configures environment)
./setup_agent.sh

# Run application (starts backend, frontend, and Redis)
./run_agent.sh
```

### Backend Development
```bash
# Activate virtual environment
source venv/bin/activate

# Run backend only
python main.py
# or with uvicorn for development
uvicorn main:app --host 0.0.0.0 --port 8001 --log-level debug --reload

# Run tests
python -m pytest tests/
python -m pytest tests/test_specific.py -v  # Run specific test
```

### Frontend Development
```bash
cd autobot-vue

# Install dependencies
npm install

# Development server with hot reload
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Linting (runs both oxlint and eslint)
npm run lint

# Format code with Prettier
npm run format

# Unit tests with Vitest
npm run test:unit
npm run test:unit -- --watch  # Watch mode

# E2E tests with Cypress
npm run test:e2e       # Headless
npm run test:e2e:dev   # Interactive
```

### API Testing
```bash
# Health check
curl -s "http://localhost:8001/api/system/health" | python3 -m json.tool

# Submit a goal
curl -X POST "http://localhost:8001/api/goal" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Create a Python hello world script"}'

# Search knowledge base
curl -X POST "http://localhost:8001/api/knowledge_base/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 5}'

# Get LLM models
curl -s "http://localhost:8001/api/llm/models" | python3 -m json.tool
```

## Configuration and Data Management

### Configuration System
- **Primary Config**: `config/config.yaml` - all system settings
- **Environment Variables**: Override with `AUTOBOT_` prefix (see `docs/environment-variables.md`)
- **No Hardcoding**: All values (ports, paths, API keys) must be configurable
- **Config Loading**: Through `src/config.py` singleton

### Environment Variable Examples
```bash
# Backend configuration
export AUTOBOT_BACKEND_HOST=0.0.0.0
export AUTOBOT_BACKEND_PORT=8001

# LLM configuration
export AUTOBOT_LLM_DEFAULT=ollama_tinyllama
export AUTOBOT_OLLAMA_HOST=http://localhost:11434
export AUTOBOT_OPENAI_API_KEY=sk-...

# Redis configuration
export AUTOBOT_REDIS_ENABLED=true
export AUTOBOT_REDIS_HOST=localhost
```

### Data Storage Layout
```
data/
├── chats/              # Chat history (JSON files)
├── chromadb/           # Vector embeddings
├── knowledge_base.db   # SQLite database
├── file_manager_root/  # Uploaded files
├── audit.log          # Security audit log
└── messages/          # System messages

logs/
└── autobot.log        # Application logs

config/
├── config.yaml        # Main configuration
├── settings.json      # User preferences (optional)
└── config.yaml.template  # Config template
```

## Key Architecture Patterns

### Application Factory Pattern
- `main.py` is a thin wrapper that imports from `backend/app_factory.py`
- All FastAPI app configuration in `create_app()` function
- Clean separation of app creation from server startup

### Dependency Management
- Python: `pyenv` manages Python 3.10.13
- Node.js: `nvm` manages Node.js 20.x LTS
- Redis: Docker container managed by scripts
- All handled automatically by `setup_agent.sh`

### Environment Scripts
```bash
# Development mode (debug logging)
source scripts/set-env-development.sh

# Production mode (optimized settings)
source scripts/set-env-production.sh

# DeepSeek model configuration
source scripts/set-env-deepseek.sh
```

### Testing Strategy
- Backend: pytest with fixtures in `tests/`
- Frontend: Vitest for unit tests, Cypress for E2E
- API: Comprehensive endpoint testing via curl/httpie
- Integration: Full system tests with `run_agent.sh`

## Development Workflow

### Local Development Setup
1. Fork and clone the repository
2. Run `./setup_agent.sh` to configure environment
3. Start development with `./run_agent.sh`
4. Frontend dev server: `cd autobot-vue && npm run dev`
5. Backend only: `python main.py`

### Code Quality Tools
- **Backend**: Black formatter, isort imports, flake8 linting
- **Frontend**: ESLint + oxlint, Prettier formatting
- **Pre-commit hooks**: Configured in `.pre-commit-config.yaml`
- **Type checking**: mypy (Python), TypeScript strict mode

### Common Development Tasks
```bash
# Add a new Python dependency
echo "new-package==1.0.0" >> requirements.txt
./setup_agent.sh  # Reinstalls all dependencies

# Add a new npm dependency
cd autobot-vue
npm install new-package
npm run type-check  # Verify TypeScript compatibility

# Create a new API endpoint
# 1. Add route handler in backend/api/
# 2. Update OpenAPI schema if needed
# 3. Add frontend API client in autobot-vue/src/services/
# 4. Update types in autobot-vue/src/types/
```

### Debugging Tips
- Backend logs: `tail -f logs/autobot.log`
- Frontend console: Browser DevTools
- API testing: Visit http://localhost:8001/docs for Swagger UI
- WebSocket events: Monitor in browser Network tab
- Redis monitoring: `docker exec -it autobot-redis redis-cli MONITOR`

### Performance Considerations
- Knowledge base queries use vector similarity (limit results)
- File uploads processed asynchronously via Redis queue
- Frontend uses lazy loading for large components
- API responses paginated where applicable
- WebSocket events throttled to prevent flooding

## Important Notes

### GUI Automation Dependencies
- **PyAutoGUI**: Requires display access (may need `xhost +` on Linux)
- **Tesseract OCR**: Optional, install with `apt-get install tesseract-ocr`
- **Voice Interface**: Requires `portaudio` for microphone access

### Redis Configuration
- Started automatically by `run_agent.sh` as Docker container
- Includes RedisStack modules: Search, JSON, TimeSeries, Bloom
- Default port: 6379 (configurable via AUTOBOT_REDIS_PORT)
- Persistent data in Docker volume `autobot-redis-data`

### Security Considerations
- Never commit `.env` files or API keys
- File browser sandboxed to `data/file_manager_root/`
- Command execution requires user approval
- Audit logging tracks all sensitive operations

### Hardware Acceleration
- Intel NPU: Requires OpenVINO and Python 3.11+
- NVIDIA GPU: CUDA toolkit required for GPU inference
- CPU fallback: Always available, no special requirements
