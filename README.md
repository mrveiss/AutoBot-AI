# AutoBot - Autonomous AI Agent

AutoBot is a sophisticated autonomous agent that combines modern AI capabilities with system interaction tools. It features a Vue.js frontend, FastAPI backend, and supports multiple LLM providers for intelligent task execution and system automation.

## 🚀 Key Features

### 🤖 AI-Powered Intelligence
- **Multi-LLM Support**: Ollama (local), OpenAI, Anthropic Claude integration
- **Intelligent Task Planning**: Breaks down complex goals into executable steps
- **Context-Aware Responses**: RAG-powered knowledge base with ChromaDB vector storage
- **Configurable AI Behavior**: Temperature settings, model selection, and custom prompts

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

---

## 🛠 Technology Stack

### Frontend (Vue.js Application)
- **Framework**: Vue 3 with Composition API
- **Language**: TypeScript
- **Build Tool**: Vite
- **State Management**: Pinia
- **Routing**: Vue Router
- **Testing**: Vitest (unit) + Cypress (E2E)
- **Code Quality**: ESLint + Prettier
- **Location**: `autobot-vue/`

### Backend (Python FastAPI)
- **Framework**: FastAPI with async/await
- **Language**: Python 3.10+
- **API Documentation**: Auto-generated OpenAPI/Swagger
- **WebSockets**: Real-time event streaming
- **Location**: `backend/`

### AI & Machine Learning
- **LLM Providers**:
  - **Ollama**: Local model hosting (TinyLlama, Phi, Llama2, etc.)
  - **OpenAI**: GPT-3.5, GPT-4 series
  - **Anthropic**: Claude 3 (Sonnet, Haiku)
- **Vector Database**: ChromaDB for embeddings
- **Hardware Acceleration**:
  - Intel NPU (OpenVINO)
  - NVIDIA GPU (CUDA)
  - CPU fallback

### Data Storage
- **Primary Database**: SQLite (knowledge base, chat history)
- **Vector Storage**: ChromaDB (document embeddings)
- **Cache**: Redis (optional, for high-performance deployments)
- **File System**: Sandboxed file operations in `data/`

### Configuration & Security
- **Configuration**: YAML + JSON with environment variable overrides
- **Security**: Audit logging, permission system, sandboxed operations
- **Session Management**: Configurable timeouts and encryption options

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
  ```bash
  # Ubuntu/Debian
  sudo apt update && sudo apt install tesseract-ocr
  
  # macOS
  brew install tesseract
  
  # Windows
  # Download from: https://github.com/UB-Mannheim/tesseract/wiki
  ```

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
# or: ollama pull phi    # Better performance
# or: ollama pull llama2 # Higher quality
```

**Option B: OpenAI**
```bash
# Set API key as environment variable
export OPENAI_API_KEY="your-api-key-here"

# Or edit config/config.yaml:
# llm_config:
#   default_llm: "openai"
#   openai:
#     api_key: "your-api-key-here"
```

**Option C: Anthropic Claude**
```bash
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

### API Usage

#### Submit Goals
```bash
curl -X POST http://localhost:8001/api/goal \
  -H "Content-Type: application/json" \
  -d '{"goal": "Create a Python script to analyze CSV data"}'
```

#### Knowledge Base Search
```bash
curl -X POST http://localhost:8001/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 5}'
```

#### File Operations
```bash
# List files
curl "http://localhost:8001/api/files/list"

# Upload file
curl -X POST http://localhost:8001/api/files/upload \
  -F "file=@document.pdf" \
  -F "path=documents/"
```

---

## 🏗 Architecture Overview

### System Components

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
- **`src/gui_controller.py`**: GUI automation and system interaction
- **`backend/api/`**: FastAPI route handlers organized by domain

---

## 🔧 Configuration

AutoBot uses a layered configuration system:

1. **Base Config**: `config/config.yaml` (main settings)
2. **Runtime Settings**: `config/settings.json` (user preferences)
3. **Environment Variables**: `AUTOBOT_*` prefixed overrides

### Key Configuration Sections

```yaml
# Backend Server
backend:
  server_port: 8001
  cors_origins: ["http://localhost:5173"]

# LLM Configuration
llm_config:
  default_llm: "ollama_tinyllama"
  ollama:
    host: "http://localhost:11434"
    models:
      tinyllama: "tinyllama:latest"
      phi2: "phi:latest"

# Knowledge Base
memory:
  chromadb:
    enabled: true
    path: "data/chromadb"
  redis:
    enabled: false
    host: "localhost"
    port: 6379

# Security & Logging
security:
  enable_encryption: false
  audit_log_file: "data/audit.log"

logging:
  log_level: "info"
  log_file_path: "logs/autobot.log"
```

### Environment Variables
```bash
export AUTOBOT_BACKEND_PORT=8002
export AUTOBOT_OLLAMA_HOST=http://localhost:11434
export AUTOBOT_REDIS_ENABLED=true
export OPENAI_API_KEY=your-key-here
```

**📖 For complete configuration reference, see [Configuration Documentation](docs/configuration.md)**

---

## 🔌 API Reference

AutoBot provides a comprehensive REST API organized by functional areas:

### Core Endpoints
- **Agent Control**: `/api/goal`, `/api/pause`, `/api/resume`
- **Chat Management**: `/api/chats/*`, `/api/chat/*`
- **File Operations**: `/api/files/*`
- **Knowledge Base**: `/api/knowledge/*`
- **Settings**: `/api/settings/*`
- **System Health**: `/api/health`, `/api/status`

### Example API Calls

```bash
# Health check
curl http://localhost:8001/api/health

# Create new chat
curl -X POST http://localhost:8001/api/chats/new

# Search knowledge base
curl -X POST http://localhost:8001/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "python scripting", "limit": 10}'

# Get system status
curl http://localhost:8001/api/status
```

**📚 For complete API documentation, see [Backend API Documentation](docs/backend_api.md)**

---

## 🚀 Development

### Frontend Development
```bash
cd autobot-vue

# Install dependencies
npm install

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

# Install development dependencies
pip install -r requirements.txt

# Run backend only
python backend/main.py

# Run tests
python -m pytest tests/
```

### Code Quality
```bash
# Frontend linting
cd autobot-vue
npm run lint
npm run format

# Backend linting
black src/ backend/
flake8 src/ backend/
```

---

## 🐛 Troubleshooting

### Common Issues

**LLM Connection Failed**
```bash
# For Ollama
ollama serve
ollama list  # Check available models

# Check configuration
curl http://localhost:11434/api/tags
```

**Port Already in Use**
```bash
# Change backend port
export AUTOBOT_BACKEND_PORT=8002

# Or edit config/config.yaml
```

**Permission Errors**
```bash
chmod +x setup_agent.sh run_agent.sh
mkdir -p data logs config
```

**Configuration Issues**
```bash
# Validate configuration
python -c "from src.config import validate_config; print(validate_config())"

# Reset to defaults
cp config/config.yaml.template config/config.yaml
```

### Debug Mode
Enable enhanced debugging:
```yaml
developer:
  enabled: true
  enhanced_errors: true
  debug_logging: true

logging:
  log_level: "debug"
```

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

# Make changes and test
npm run test:unit  # Frontend tests
python -m pytest  # Backend tests
```

---

## 📄 Documentation

- **[Configuration Guide](docs/configuration.md)**: Complete configuration reference
- **[API Documentation](docs/backend_api.md)**: REST API endpoints and examples
- **[Project Architecture](docs/project.md)**: Detailed system design
- **[Task Management](docs/tasks.md)**: Development roadmap and tasks

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🌟 Acknowledgments

- **Vue.js** community for the excellent frontend framework
- **FastAPI** team for the high-performance Python web framework
- **Ollama** project for making local LLMs accessible
- **ChromaDB** for vector database capabilities
- All contributors who have helped improve AutoBot

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/AutoBot-AI/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/AutoBot-AI/discussions)
- **Documentation**: [Project Docs](docs/)

**Built with ❤️ for the AI automation community**
