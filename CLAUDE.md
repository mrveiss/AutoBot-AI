# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoBot is an autonomous agent that interacts with computer GUIs and executes tasks using LLMs for planning, a knowledge base for context, and various tools for system interaction including GUI automation, shell command execution, and real-time diagnostics.

## Architecture

### Core Components
- **Backend (Python FastAPI)**: Main server in `backend/main.py` handling API endpoints and WebSocket connections
- **Frontend (Vue.js)**: Modern Vue 3 application in `autobot-vue/` directory with TypeScript support
- **Legacy Frontend**: Static HTML/JS frontend in `frontend/` directory (being replaced by Vue app)
- **Core Modules** (`src/`):
  - `orchestrator.py`: Task planning and dispatch management with Redis/local transport
  - `llm_interface.py`: Communication with various LLM backends (Ollama, OpenAI, HuggingFace)
  - `knowledge_base.py`: RAG system with ChromaDB for document processing and fact storage
  - `worker_node.py`: Task execution engine
  - `gui_controller.py`: GUI automation (mouse, keyboard, OCR, window management)
  - `diagnostics.py`: System monitoring and failure analysis
  - `event_manager.py`: Centralized event bus for inter-module communication

## Essential Commands

### Application Lifecycle
**CRITICAL**: The application is ALWAYS run with:
```bash
./run_agent.sh
```

**CRITICAL**: Dependencies and environment changes MUST be updated with:
```bash
./setup_agent.sh
```

### Development Commands (Vue Frontend)
```bash
cd autobot-vue

# Development server (manual)
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Linting (runs both oxlint and eslint)
npm run lint

# Format code
npm run format

# Unit tests
npm run test:unit

# E2E tests
npm run test:e2e
npm run test:e2e:dev
```

## Code Architecture Principles

### Code Reusability
- **Maximize code reuse**: All common functionality must be extracted into shared modules
- **No code duplication**: Identical or similar code blocks must be consolidated into reusable functions/classes
- **Shared utilities**: Create utility modules for common operations (file handling, configuration, logging, etc.)
- **Component-based design**: Build modular components that can be imported and reused across different parts of the system

### Configuration Management
- **Single configuration location**: All configuration files stored in `config/` directory
- **Centralized config loading**: Use a single configuration manager that loads from `config/config.yaml`
- **No hardcoded values**: All constants, paths, URLs, ports, and settings must be configurable
- **Runtime configuration**: Support dynamic configuration updates through database or config file changes
- **Environment-specific configs**: Support different configurations for development, testing, and production

### Data Storage
- **Single data location**: All data stored in `data/` directory
- **Centralized data access**: Use data access layer to abstract storage mechanisms
- **Consistent data formats**: Standardize data formats across all components
- **Database-driven settings**: Store runtime settings and user preferences in database tables

### Configuration Files Structure
- `config/config.yaml`: Main application configuration
- `config/settings.json`: Runtime settings and user preferences
- `config/config.yaml.template`: Template for initial setup
- All modules must load configuration through centralized config manager

### Data Directory Structure
- `data/`: Root data directory for all persistent storage
- `data/chats/`: Chat history and conversation data
- `data/chromadb/`: Vector database storage
- `data/knowledge_base.db`: SQLite database for structured data
- `data/audit.log`: Security and operational audit logs

## Documentation and Task Management

### Task Structure Requirements
When adding tasks to `docs/tasks.md`, follow this hierarchical structure:

1. **Tasks** (High-level features/goals)
   - **Subtasks** (Component-level work)
     - **Steps** (Specific implementation actions)

### Task Dependencies
Tasks must include dependency mapping to ensure proper execution order. Document task dependencies in the following format:
- Task A depends on Task B completion
- Subtask X requires Subtask Y infrastructure
- Step 1 must complete before Step 2

### Documentation Files
- `docs/tasks.md`: Todo list with task hierarchy and dependencies
- `docs/task_log.md`: Execution summaries and completion records
- `docs/project.md`: Project phases and detailed architecture
- `docs/decisions.md`: Architecture and design decisions
- `docs/status.md`: Current project status tracking

## Key Development Notes

### Environment Management
- Uses pyenv for Python 3.10.13 management
- Uses nvm for Node.js 20.x LTS management
- Redis server required for task transport
- All dependencies managed through setup_agent.sh script

### Application Architecture
- Backend runs on configurable port (default 8001 via config)
- Frontend runs on configurable port (default 5173 via config)
- Redis connection configured through `config/config.yaml`
- All ports, hosts, and endpoints must be configurable

### Configuration-Driven Development
- **Never hardcode**: Ports, file paths, URLs, API keys, timeouts, or any operational values
- **Database settings**: Store user preferences, feature flags, and runtime settings in database
- **Config validation**: Validate all configuration values on startup
- **Config hot-reload**: Support configuration changes without application restart where possible

### LLM Backend Support
- Multiple LLM backends: Ollama (default), OpenAI, local HuggingFace models
- All LLM settings stored in `config/config.yaml`
- Model selection and parameters configurable at runtime
- Hardware acceleration settings stored in configuration

### Data Storage Standards
- SQLite database for knowledge base at `data/knowledge_base.db`
- ChromaDB for vector embeddings at `data/chromadb/`
- Chat history in `data/chats/` as JSON files
- All data paths configurable through `config/config.yaml`

### Security & Monitoring
- Security policies defined in configuration files
- Audit logging to `data/audit.log`
- Log levels and destinations configurable
- Monitoring thresholds stored in database