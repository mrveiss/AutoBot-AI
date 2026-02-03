# AutoBot Configuration Documentation

## Overview
AutoBot uses a centralized configuration system managed by the `ConfigManager` class in `src/config.py`. The configuration system provides a flexible, layered approach to managing application settings.

## Configuration Architecture

### Configuration Loading Hierarchy
1. **Base Configuration**: `config/config.yaml` (main configuration file)
2. **Runtime Settings**: `config/settings.json` (runtime overrides and user preferences)
3. **Environment Variables**: `AUTOBOT_*` prefixed environment variables (highest priority)

### Configuration Files Location
- **Main Config**: `config/config.yaml` (copy from `config/config.yaml.template`)
- **Template**: `config/config.yaml.template` (default configuration template)
- **Runtime Settings**: `config/settings.json` (automatically created for runtime changes)

---

## Complete Configuration Reference

### Backend Server Configuration

```yaml
backend:
  # Server Network Settings
  server_host: "0.0.0.0"                    # Server bind address
  server_port: 8001                         # Server port
  api_endpoint: "http://localhost:8001"     # API base URL

  # CORS (Cross-Origin Resource Sharing) Settings
  cors_origins:
    - "http://localhost:5173"               # Vue.js development server
    - "http://127.0.0.1:5173"
    - "http://localhost:3000"               # Playwright service port
    - "http://127.0.0.1:3000"

  # Data Storage Paths
  chat_data_dir: "data/chats"               # Chat sessions directory
  chat_history_file: "data/chat_history.json"  # Legacy chat history
  messages_dir: "data/messages"             # Message files directory
  knowledge_base_db: "data/knowledge_base.db"  # Knowledge base SQLite
  reliability_stats_file: "data/reliability_stats.json"  # Performance stats
  audit_log_file: "data/audit.log"         # Security audit log

  # Request Handling Settings
  timeout: 60                               # Request timeout (seconds)
  max_retries: 3                           # Maximum retry attempts
  streaming: false                         # Enable response streaming
```

### LLM (Language Model) Configuration

```yaml
llm_config:
  # Model Selection
  default_llm: "ollama_tinyllama"          # Default LLM identifier
  task_llm: "ollama_tinyllama"             # Task-specific LLM

  # Ollama Configuration
  ollama:
    host: "http://localhost:11434"         # Ollama server URL
    port: 11434                            # Ollama server port
    endpoint: "http://localhost:11434/api/generate"  # Generation endpoint
    base_url: "http://localhost:11434"     # Base URL for API calls
    models:                                # Available model mappings
      tinyllama: "tinyllama:latest"
      phi2: "phi:latest"
      llama2: "llama2:latest"

  # OpenAI Configuration
  openai:
    api_key: ""                            # OpenAI API key (use env variable)
    endpoint: "https://api.openai.com/v1"  # OpenAI API endpoint
    models:
      - "gpt-3.5-turbo"
      - "gpt-4"

  # Anthropic Configuration
  anthropic:
    api_key: ""                            # Anthropic API key (use env variable)
    endpoint: "https://api.anthropic.com/v1"  # Anthropic API endpoint
    models:
      - "claude-3-sonnet-20240229"
      - "claude-3-haiku-20240307"

  # LLM Behavior Settings
  orchestrator_llm_settings:
    temperature: 0.7                       # Creativity for planning tasks
  task_llm_settings:
    temperature: 0.5                       # Consistency for execution tasks
```

### Memory and Storage Configuration

```yaml
memory:
  # Long-term Memory
  long_term:
    enabled: true                          # Enable persistent memory
    retention_days: 30                     # Days to retain memory
    db_path: "data/agent_memory.db"        # SQLite database path

  # Short-term Memory
  short_term:
    enabled: true                          # Enable session memory
    duration_minutes: 30                   # Memory duration

  # Vector Storage for Embeddings
  vector_storage:
    enabled: true                          # Enable vector operations
    update_frequency_days: 7               # Update frequency

  # ChromaDB Configuration
  chromadb:
    enabled: true                          # Enable ChromaDB
    path: "data/chromadb"                  # ChromaDB storage path
    collection_name: "autobot_memory"      # Collection name

  # Redis Configuration
  redis:
    enabled: false                         # Enable Redis (optional)
    host: "localhost"                      # Redis server host
    port: 6379                            # Redis server port
```

### Security Configuration

```yaml
security:
  enable_encryption: false                 # Enable data encryption
  session_timeout_minutes: 30             # User session timeout
  audit_log_file: "data/audit.log"       # Audit log file path
```

### Logging Configuration

```yaml
logging:
  log_level: "info"                       # Log level (debug, info, warning, error)
  log_to_file: true                       # Enable file logging
  log_file_path: "logs/autobot.log"       # Log file path
```

### User Interface Configuration

```yaml
ui:
  theme: "light"                          # UI theme (light, dark)
  font_size: "medium"                     # Font size (small, medium, large)
  language: "en"                          # Interface language
  animations: true                        # Enable UI animations
  developer_mode: false                   # Show developer features
```

### Developer Mode Configuration

```yaml
developer:
  enabled: false                          # Enable developer mode
  enhanced_errors: true                   # Show detailed error messages
  endpoint_suggestions: true              # Suggest similar endpoints on 404
  debug_logging: false                    # Enable debug logging
```

### Chat Configuration

```yaml
chat:
  auto_scroll: true                       # Auto-scroll to latest messages
  max_messages: 100                       # Maximum messages per session
  message_retention_days: 30              # Days to retain chat history
  default_welcome_message: "Hello! How can I assist you today?"  # Welcome message
```

### Message Display Configuration

```yaml
message_display:
  show_thoughts: true                     # Show AI reasoning process
  show_json: false                        # Show raw JSON responses
  show_utility: false                     # Show utility function calls
  show_planning: true                     # Show planning steps
  show_debug: false                       # Show debug information
```

### Knowledge Base Configuration

```yaml
knowledge_base:
  enabled: true                           # Enable knowledge base features
  update_frequency_days: 7                # Update frequency
  db_path: "data/knowledge_base.db"       # SQLite database path
```

### Voice Interface Configuration

```yaml
voice_interface:
  enabled: false                          # Enable voice features
  voice: "default"                        # TTS voice selection
  speech_rate: 1.0                        # Speech rate multiplier
```

### Hardware Acceleration Configuration

```yaml
hardware_acceleration:
  priority:                               # Acceleration priority order
    - "openvino_npu"                      # Intel NPU (highest priority)
    - "openvino"                          # OpenVINO auto-select
    - "cuda"                              # NVIDIA GPU
    - "cpu"                               # CPU fallback
```

### Test Configuration

```yaml
test:
  chat_history_file: "data/test_chat_history.json"  # Test chat history file
```

---

## ConfigManager Class

The `ConfigManager` class in `src/config.py` provides the core configuration functionality:

### Key Features

1. **Layered Configuration**: Merges base config, user settings, and environment variables
2. **Deep Merging**: Nested dictionaries are merged recursively
3. **Environment Override**: Supports `AUTOBOT_*` environment variables
4. **Runtime Updates**: Changes can be saved to `settings.json`
5. **Validation**: Built-in configuration validation

### Main Methods

```python
from src.config import config

# Get configuration values
config.get('backend')                     # Get top-level section
config.get_nested('backend.server_port') # Get nested value with dot notation
config.get_llm_config()                  # Get LLM config with defaults
config.get_redis_config()                # Get Redis config with defaults
config.get_backend_config()              # Get backend config with defaults

# Set configuration values
config.set('ui.theme', 'dark')           # Set top-level value
config.set_nested('llm_config.ollama.host', 'http://new-host:11434')

# Save and reload
config.save_settings()                   # Save to settings.json
config.reload()                          # Reload from files
config.validate_config()                 # Validate configuration
```

---

## Environment Variables

AutoBot supports environment variable overrides using the `AUTOBOT_` prefix:

### Common Environment Variables

| Variable | Config Path | Purpose | Example |
|----------|-------------|---------|---------|
| `AUTOBOT_BACKEND_PORT` | `backend.server_port` | Backend server port | `8002` |
| `AUTOBOT_BACKEND_HOST` | `backend.server_host` | Backend bind address | `127.0.0.1` |
| `AUTOBOT_DEFAULT_LLM_MODEL` | `llm_config.ollama.model` | **Primary** - Default LLM model | `mistral:7b-instruct` |
| `AUTOBOT_OLLAMA_HOST` | `llm_config.ollama.host` | Ollama server URL | `http://ollama:11434` |
| `AUTOBOT_OLLAMA_PORT` | `llm_config.ollama.port` | Ollama server port | `11434` |
| `AUTOBOT_ORCHESTRATOR_LLM` | `llm_config.orchestrator_llm` | Orchestrator LLM | `gpt-4` |
| `AUTOBOT_REDIS_HOST` | `memory.redis.host` | Redis server host | `redis.example.com` |
| `AUTOBOT_REDIS_PORT` | `memory.redis.port` | Redis server port | `6380` |
| `AUTOBOT_REDIS_ENABLED` | `memory.redis.enabled` | Enable/disable Redis | `true` |
| `AUTOBOT_USE_LANGCHAIN` | `orchestrator.use_langchain` | Enable LangChain | `true` |

### Setting Environment Variables

**Linux/macOS:**
```bash
export AUTOBOT_BACKEND_PORT=8002
export AUTOBOT_OLLAMA_HOST=http://localhost:11434
export AUTOBOT_REDIS_ENABLED=true
```

**Windows:**
```cmd
set AUTOBOT_BACKEND_PORT=8002
set AUTOBOT_OLLAMA_HOST=http://localhost:11434
set AUTOBOT_REDIS_ENABLED=true
```

**Docker Environment:**
```bash
docker run -e AUTOBOT_BACKEND_PORT=8002 \
           -e AUTOBOT_OLLAMA_HOST=http://ollama:11434 \
           autobot
```

---

## Configuration Management via API

Settings can be managed through the REST API:

### Get Current Settings
```bash
curl http://localhost:8001/api/settings/
```

### Update Settings
```bash
curl -X POST http://localhost:8001/api/settings/ \
  -H "Content-Type: application/json" \
  -d '{
    "ui": {"theme": "dark"},
    "chat": {"max_messages": 200}
  }'
```

### Get Backend Settings
```bash
curl http://localhost:8001/api/settings/backend
```

### Update Backend Settings
```bash
curl -X POST http://localhost:8001/api/settings/backend \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "server_port": 8002,
      "cors_origins": ["http://localhost:3000"]
    }
  }'
```

---

## Configuration Examples

### Minimal Configuration
```yaml
# Minimal config for local development
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

### Production Configuration
```yaml
# Production configuration
backend:
  server_host: "0.0.0.0"
  server_port: 8001
  cors_origins:
    - "https://autobot.company.com"

llm_config:
  default_llm: "openai_gpt4"
  openai:
    api_key: ""  # Set via OPENAI_API_KEY env var

memory:
  redis:
    enabled: true
    host: "redis.internal"
    port: 6379
  chromadb:
    enabled: true

security:
  enable_encryption: true
  audit_log_file: "/var/log/autobot/audit.log"

logging:
  log_level: "warning"
  log_file_path: "/var/log/autobot/autobot.log"
```

### Development Configuration
```yaml
# Development configuration with debugging
backend:
  server_port: 8001

llm_config:
  default_llm: "ollama_phi2"
  task_llm_settings:
    temperature: 0.1  # More consistent for testing

ui:
  developer_mode: true

developer:
  enabled: true
  enhanced_errors: true
  debug_logging: true

logging:
  log_level: "debug"

message_display:
  show_thoughts: true
  show_json: true
  show_debug: true
```

---

## Configuration Validation

The ConfigManager includes built-in validation:

```python
from src.config import validate_config

# Validate current configuration
status = validate_config()
print(status)
```

**Example validation output:**
```json
{
  "config_loaded": true,
  "llm_config": {
    "default_llm": "ollama_tinyllama",
    "orchestrator_llm": "phi:2.7b"
  },
  "redis_config": {
    "enabled": false,
    "host": "localhost",
    "port": 6379
  },
  "backend_config": {
    "server_host": "0.0.0.0",
    "server_port": 8001,
    "api_endpoint": "http://localhost:8001"
  },
  "issues": []
}
```

---

## Troubleshooting Configuration

### Common Issues

1. **Configuration File Not Found**
   ```bash
   # Copy template to create config file
   cp config/config.yaml.template config/config.yaml
   ```

2. **Invalid YAML Syntax**
   ```bash
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
   ```

3. **Port Already in Use**
   ```yaml
   backend:
     server_port: 8002  # Use different port
   ```

4. **Ollama Connection Failed**
   ```yaml
   llm_config:
     ollama:
       host: "http://localhost:11434"  # Verify Ollama is running
   ```

5. **Permission Errors**
   ```bash
   # Ensure directories are writable
   mkdir -p data logs config
   chmod 755 data logs config
   ```

### Configuration Debugging

Enable debug logging to troubleshoot configuration issues:

```yaml
logging:
  log_level: "debug"

developer:
  enabled: true
  debug_logging: true
```

### Validation Command
```bash
# Validate configuration without starting the application
python -c "from src.config import validate_config; print(validate_config())"
```

---

## Configuration Migration

When upgrading AutoBot versions:

1. **Backup current configuration:**
   ```bash
   cp config/config.yaml config/config.yaml.backup
   cp config/settings.json config/settings.json.backup
   ```

2. **Compare with new template:**
   ```bash
   diff config/config.yaml.template config/config.yaml
   ```

3. **Update configuration** with new required fields

4. **Test configuration:**
   ```bash
   python -c "from src.config import config; print('Config loaded successfully')"
   ```

---

## Best Practices

### Security
- Store API keys in environment variables, not config files
- Never commit sensitive data to version control
- Use secure file permissions for config files
- Enable audit logging in production

### Performance
- Use Redis for high-performance deployments
- Configure appropriate timeouts for your network
- Set reasonable retention periods for data cleanup
- Monitor disk space usage with proper log rotation

### Reliability
- Enable audit logging for troubleshooting
- Configure appropriate retry settings
- Use backup strategies for configuration files
- Test configuration changes in development first

### Development
- Use developer mode for debugging
- Enable detailed error messages during development
- Use separate config files for different environments
- Document custom configuration changes

This configuration documentation reflects the current AutoBot implementation and provides comprehensive guidance for all configuration scenarios.
