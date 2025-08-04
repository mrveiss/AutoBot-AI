# AutoBot - Autonomous AI Agent

AutoBot is an enterprise-grade autonomous AI platform that provides advanced task automation, knowledge management, and system interaction capabilities. The system features a modern Vue 3 frontend with real-time monitoring, comprehensive knowledge management with template systems, and robust backend services with full API coverage.

**Current Status**: ✅ ENTERPRISE-READY - All core features operational with advanced capabilities implemented
**Latest Version**: Phase 4 Complete - Advanced Features Development (100% implemented)
**System Health**: All components operational with real-time monitoring and comprehensive testing validation

---

## 🚀 Key Features

### 🤖 AI-Powered Intelligence
- **Multi-LLM Support**: Ollama (local), OpenAI, Anthropic Claude integration
- **Intelligent Task Planning**: Breaks down complex goals into executable steps
- **Context-Aware Responses**: RAG-powered knowledge base with ChromaDB vector storage
- **Configurable AI Behavior**: Temperature settings, model selection, and custom prompts
- **🧠 Prompt Intelligence Sync**: Transforms agent into expert system with operational intelligence

### 🎯 System Interaction
- **GUI Automation**: Mouse/keyboard control, OCR text recognition, window management
- **Shell Command Execution**: Secure command execution with approval workflows
- **File Management**: Sandboxed file operations with browser interface
- **Real-time Monitoring**: System metrics (CPU, RAM, GPU/VRAM) tracking

### 🌐 Modern Web Interface
- **Vue.js 3 Frontend**: TypeScript, Vite, modern component architecture
- **Real-time Communication**: WebSocket integration for live updates
- **Responsive Design**: Works on desktop and mobile devices
- **Developer Tools**: Enhanced debugging, API explorer, system diagnostics

### 📚 Knowledge Management
- **RAG System**: Document processing (PDF, DOCX, TXT, CSV, MD)
- **Vector Search**: ChromaDB-powered semantic similarity matching
- **Fact Storage**: Structured data storage with SQLite backend
- **Content Upload**: Drag-and-drop file processing and URL ingestion
- **Template System**: Professional knowledge entry templates with visual gallery

---

## 🛠 Technology Stack

### Frontend
- **Vue 3** with Composition API and TypeScript
- **Vite** build tool with **Pinia** state management
- **Vue Router** with **Vitest** + **Cypress** testing
- Location: `autobot-vue/`

### Backend
- **FastAPI** with async/await and Python 3.10+
- **Auto-generated OpenAPI/Swagger** documentation
- **WebSockets** for real-time event streaming
- Location: `backend/`

### AI & Data
- **LLM Providers**: Ollama, OpenAI, Anthropic
- **Vector Database**: ChromaDB for embeddings
- **Primary Database**: SQLite (knowledge base, chat history)
- **Cache**: Redis (optional, for high-performance deployments)
- **Hardware Acceleration**: Intel NPU (OpenVINO), NVIDIA GPU (CUDA), CPU fallback

---

## ⚡ Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/your-repo/AutoBot-AI.git
cd AutoBot-AI

# Run automated setup (creates venv, installs dependencies)
chmod +x setup_agent.sh
./setup_agent.sh
```

### 2. Configure LLM Provider

**Option A: Ollama (Local, Recommended)**
```bash
# Install and start Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &

# Pull a model
ollama pull tinyllama
```

**Option B: OpenAI/Anthropic**
```bash
export OPENAI_API_KEY="your-api-key-here"
# or
export ANTHROPIC_API_KEY="your-api-key-here"
```

### 3. Launch AutoBot
```bash
# Start all services (backend + frontend)
./run_agent.sh
```

### 4. Access Interface
- **Main Interface**: http://localhost:5173 (Vue.js frontend)
- **API Documentation**: http://localhost:8001/docs (Swagger UI)
- **Health Check**: http://localhost:8001/api/health

---

## 📋 Prerequisites

### Required Software
- **Python 3.10+** (3.11+ recommended for Intel NPU support)
- **Node.js 20.x LTS** (for frontend development)
- **Git** (for cloning repository)

### Optional Dependencies
- **Ollama** (for local LLM hosting): [Install Ollama](https://ollama.ai)
- **Redis Server** (for high-performance deployments)
- **Tesseract OCR** (for GUI text recognition)

**📖 For detailed installation instructions, see [Installation Guide](docs/user_guide/01-installation.md)**

---

## 🎮 Usage Guide

### Web Interface Features

#### 💬 Chat Interface
- **AI Conversations**: Natural language interaction with your chosen LLM
- **Command Execution**: Direct system command execution with approval
- **File Upload**: Drag and drop files for knowledge base integration
- **Session Management**: Multiple chat sessions with history

#### 📁 File Browser
- **Secure File Management**: Upload, download, view, and organize files
- **Knowledge Integration**: Add documents directly to the knowledge base
- **File Viewer**: Built-in viewer for text files and documents

#### ⚙️ Settings Panel
- **LLM Configuration**: Switch between models, adjust temperature
- **Interface Customization**: Themes, display options, developer mode
- **System Settings**: Backend configuration, Redis setup

#### 📊 System Monitor
- **Real-time Metrics**: CPU, RAM, GPU usage monitoring
- **Connection Status**: LLM and database connection health
- **Performance Tracking**: Response times and system load

### Basic API Usage

```bash
# Submit goals
curl -X POST http://localhost:8001/api/goal \
  -H "Content-Type: application/json" \
  -d '{"goal": "Create a Python script to analyze CSV data"}'

# Search knowledge base
curl -X POST http://localhost:8001/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 5}'

# List files
curl "http://localhost:8001/api/files/list"
```

**📚 For complete API documentation, see [Backend API Documentation](docs/backend_api.md)**

---

## 🔧 Configuration

AutoBot uses a layered configuration system:

```yaml
# Basic Configuration (config/config.yaml)
backend:
  server_port: 8001

llm_config:
  default_llm: "ollama_tinyllama"
  ollama:
    host: "http://localhost:11434"

memory:
  chromadb:
    enabled: true
```

### Environment Variables
```bash
export AUTOBOT_BACKEND_PORT=8002
export AUTOBOT_OLLAMA_HOST=http://localhost:11434
export AUTOBOT_REDIS_ENABLED=true
```

**⚙️ For complete configuration reference, see [Configuration Guide](docs/configuration.md)**

---

## 🐛 Troubleshooting

### Common Issues

**LLM Connection Failed**
```bash
# For Ollama
ollama serve
ollama list  # Check available models
```

**Port Already in Use**
```bash
# Change backend port
export AUTOBOT_BACKEND_PORT=8002
```

**Permission Errors**
```bash
chmod +x setup_agent.sh run_agent.sh
mkdir -p data logs config
```

**🔧 For detailed troubleshooting, see [Troubleshooting Guide](docs/user_guide/04-troubleshooting.md)**

---

## 🏗 Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Vue.js 3      │    │   FastAPI        │    │   LLM Provider  │
│   Frontend      │◄──►│   Backend        │◄──►│   (Ollama/API)  │
│                 │    │                  │    │                 │
├─────────────────┤    ├──────────────────┤    ├─────────────────┤
│ • Chat UI       │    │ • REST API       │    │ • Ollama        │
│ • File Browser  │    │ • WebSockets     │    │ • OpenAI        │
│ • Settings      │    │ • Task Queue     │    │ • Anthropic     │
│ • Monitoring    │    │ • Auth & Security│    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                               │
                       ┌───────▼────────┐
                       │  Data Layer    │
                       │                │
                       │ • SQLite       │
                       │ • ChromaDB     │
                       │ • Redis        │
                       │ • File System  │
                       └────────────────┘
```

### Core Modules
- **`src/orchestrator.py`**: Task planning and execution coordination
- **`src/llm_interface.py`**: Unified LLM provider abstraction
- **`src/knowledge_base.py`**: RAG system with ChromaDB integration
- **`src/config.py`**: Centralized configuration management
- **`src/worker_node.py`**: Task execution engine
- **`backend/api/`**: FastAPI route handlers organized by domain

---

## � Development

### Frontend Development
```bash
cd autobot-vue

# Development server
npm run dev

# Build for production
npm run build

# Run tests
npm run test:unit
npm run test:e2e
```

### Backend Development
```bash
# Activate virtual environment
source bin/activate

# Run backend only
python backend/main.py

# Run tests
python -m pytest tests/
```

**📖 For detailed development guide, see [Quick Start Guide](docs/user_guide/02-quickstart.md)**

---

## 🧠 Prompt Intelligence Synchronization

AutoBot features an advanced **Prompt-to-Knowledge Base Synchronization System** that transforms your agent from a basic tool executor into an expert system with operational intelligence.

### What It Does
- Automatically imports carefully crafted prompt library into the knowledge base
- Makes operational intelligence instantly searchable during agent operations
- Provides contextual tool mastery, error prevention, and behavioral intelligence

### Key Benefits
- **60+ operational intelligence patterns** from extensive prompt library
- **Context-aware tool usage** with optimal parameter selection
- **Proactive error prevention** using documented recovery strategies
- **Domain expertise switching** based on task requirements

### Usage
1. Ensure Redis is running and configured
2. Start AutoBot with `./run_agent.sh`
3. Access Knowledge Manager in web interface
4. Trigger sync via sync button or API: `POST /api/prompt_sync/sync`

---

## 📄 Documentation Index

### 🎯 **Core Documentation**
- **[Development Roadmap](docs/project.md)**: Complete development phases and project evolution
- **[Phase Validation Report](docs/phase_validation.md)**: Comprehensive validation of all development phases
- **[Configuration Guide](docs/configuration.md)**: Complete configuration reference with all YAML sections
- **[API Documentation](docs/backend_api.md)**: REST API endpoints with request/response examples

### 📋 **Project Management**
- **[Task Management](docs/tasks.md)**: Development roadmap and active tasks
- **[Task Log](docs/task_log.md)**: Execution history and completed work
- **[Project Status](docs/status.md)**: Current development status
- **[Decision Log](docs/decisions.md)**: Architecture and design decisions

### 📚 **User Guides**
- **[Installation Guide](docs/user_guide/01-installation.md)**: Step-by-step setup instructions
- **[Quick Start Guide](docs/user_guide/02-quickstart.md)**: Get up and running quickly
- **[Configuration Guide](docs/user_guide/03-configuration.md)**: User-friendly configuration options
- **[Troubleshooting Guide](docs/user_guide/04-troubleshooting.md)**: Common issues and solutions

### 🔧 **Technical References**
- **[System Architecture](docs/developer/01-architecture.md)**: Comprehensive technical architecture overview
- **[Process Flow Documentation](docs/developer/02-process-flow.md)**: Detailed system interactions and data flows
- **[External APIs](docs/external_apps/ollama_api.md)**: Ollama API integration details

### 🚀 **Development Progress**
- **[Phase 2 Validation](docs/phase2_validation_progress.md)**: Core functionality validation results
- **[Suggested Improvements](docs/suggested_improvements.md)**: Enhancement recommendations
- **[TODO Items](docs/todo.md)**: Pending development tasks

---

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** following our code style
4. **Add tests** for new functionality
5. **Submit a pull request**

### Development Setup
```bash
# Clone your fork
git clone https://github.com/your-username/AutoBot-AI.git
cd AutoBot-AI

# Setup development environment
./setup_agent.sh

# Create feature branch
git checkout -b feature/your-feature
```

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/AutoBot-AI/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/AutoBot-AI/discussions)
- **Documentation**: [Project Docs](docs/)

---

## � License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🌟 Acknowledgments

- **Vue.js** community for the excellent frontend framework
- **FastAPI** team for the high-performance Python web framework
- **Ollama** project for making local LLMs accessible
- **ChromaDB** for vector database capabilities
- All contributors who have helped improve AutoBot

**Built with ❤️ for the AI automation community**
