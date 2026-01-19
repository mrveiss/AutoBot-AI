# AutoBot Configuration Documentation

## Overview
AutoBot uses a centralized configuration system managed by the `ConfigManager` class. Configuration is loaded from YAML files and can be overridden by environment variables.

## Configuration Files Location
- **Primary Config**: `config/config.yaml` (runtime configuration)
- **Template**: `config/config.yaml.template` (default template)
- **Settings**: `config/settings.json` (runtime settings storage)

---

## Configuration File Structure

### Complete Configuration Example
```yaml
# AutoBot Main Configuration File
version: "1.0"
project_name: "AutoBot"

# Backend Server Configuration
backend:
  host: "0.0.0.0"
  port: 8001
  cors_origins:
    - "http://localhost:8080"
    - "http://localhost:5173"
    - "http://localhost:3000"
  static_files:
    directory: "frontend/static"
    html: true

# LLM Configuration
llm:
  provider: "ollama"          # Options: ollama, openai, huggingface
  model: "phi:2.7b"          # Default model to use
  temperature: 0.7           # Response creativity (0.0-2.0)
  max_tokens: 2048          # Maximum response length
  timeout: 30               # Request timeout in seconds
  
  # Provider-specific settings
  ollama:
    base_url: "http://localhost:11434"
    models:
      - "phi:2.7b"
      - "llama2"
      - "mistral"
  
  openai:
    api_key: "${OPENAI_API_KEY}"  # Environment variable
    base_url: "https://api.openai.com/v1"
    models:
      - "gpt-3.5-turbo"
      - "gpt-4"
  
  huggingface:
    api_token: "${HUGGINGFACE_TOKEN}"
    base_url: "https://api-inference.huggingface.co/models"
    models:
      - "microsoft/DialoGPT-medium"

# Memory & Storage Configuration
memory:
  redis:
    enabled: true
    host: "localhost"
    port: 6379
    password: "${REDIS_PASSWORD}"  # Optional environment variable
    db: 1                          # Database number for general memory
    connection_pool:
      max_connections: 50
      retry_on_timeout: true
  
  sqlite:
    enabled: true
    database_path: "data/memory.db"
    
  long_term:
    enabled: true
    max_entries: 10000
    cleanup_interval: 3600  # seconds

# Task Management Configuration
tasks:
  transport: "redis"        # Options: redis, local, memory
  max_concurrent: 5         # Maximum concurrent tasks
  timeout: 300             # Task timeout in seconds
  retry_attempts: 3        # Number of retry attempts
  priority_levels:
    - "low"
    - "normal" 
    - "high"
    - "urgent"
  
  approval:
    required_for:
      - "system_commands"
      - "file_operations" 
      - "network_requests"
    timeout: 60            # Approval timeout in seconds

# LlamaIndex Knowledge Base Configuration
llama_index:
  vector_store:
    type: "redis"          # Options: redis, chroma, memory
    
    redis:
      host: "localhost"
      port: 6379
      password: "${REDIS_PASSWORD}"
      db: 0                # Separate DB for vector storage
      index_name: "autobot_index"
  
  embedding:
    model: "nomic-embed-text"  # Ollama embedding model
    dimensions: 768            # Embedding vector dimensions
  
  chunk_size: 512             # Document chunk size
  chunk_overlap: 20           # Overlap between chunks
  
  retrieval:
    similarity_top_k: 5       # Number of similar chunks to retrieve
    similarity_threshold: 0.7  # Minimum similarity score

# Security Configuration
security:
  authentication:
    enabled: false           # Enable/disable authentication
    session_timeout: 3600    # Session timeout in seconds
    max_login_attempts: 5    # Maximum failed login attempts
    lockout_duration: 300    # Account lockout duration in seconds
  
  permissions:
    default_role: "user"     # Default user role
    roles:
      user:
        - "allow_goal_submission"
        - "allow_chat_control"
        - "allow_voice_listen"
        - "allow_voice_speak"
      admin:
        - "allow_goal_submission"
        - "allow_chat_control"
        - "allow_shell_execute"
        - "allow_command_approval"
        - "allow_agent_control"
        - "allow_voice_listen"
        - "allow_voice_speak"
  
  audit:
    enabled: true
    log_file: "data/audit.log"
    max_file_size: 10485760   # 10MB in bytes
    backup_count: 5           # Number of backup files to keep

# Logging Configuration
logging:
  level: "INFO"              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  
  files:
    backend: "logs/autobot_backend.log"
    llm_usage: "logs/llm_usage.log"
    error: "logs/error.log"
  
  max_file_size: 10485760    # 10MB
  backup_count: 5
  
  console:
    enabled: true
    level: "INFO"

# Data Storage Paths
data:
  base_directory: "data"
  chat_history_file: "data/chat_history.json"
  knowledge_base_db: "data/knowledge_base.db"
  reliability_stats: "data/reliability_stats.json"
  upload_directory: "uploads"
  
  chats:
    directory: "data/chats"
    max_sessions: 100
    auto_cleanup: true
    cleanup_days: 30
  
  chromadb:
    directory: "data/chromadb"
    collection_name: "autobot_knowledge"

# Voice Interface Configuration  
voice:
  enabled: false             # Enable/disable voice features
  continuous_listening: false
  
  speech_to_text:
    provider: "whisper"      # Options: whisper, google, azure
    model: "base"           # Whisper model size
    language: "en"          # Language code
  
  text_to_speech:
    provider: "pyttsx3"     # Options: pyttsx3, azure, google
    voice_rate: 150         # Speaking rate
    voice_volume: 0.8       # Volume level (0.0-1.0)

# GUI Automation Configuration
gui:
  enabled: true
  screenshot_interval: 1.0   # Seconds between screenshots
  action_delay: 0.5         # Delay between GUI actions
  
  ocr:
    provider: "tesseract"    # OCR engine
    confidence_threshold: 60 # Minimum OCR confidence
  
  window_management:
    focus_timeout: 5         # Timeout for window focus operations
    search_timeout: 10       # Timeout for element search

# Diagnostics & Monitoring
diagnostics:
  enabled: true
  collection_interval: 60   # Metrics collection interval in seconds
  
  system_metrics:
    cpu: true
    memory: true
    disk: true
    network: true
  
  gpu_monitoring:
    enabled: true
    nvidia_smi: true        # Use nvidia-smi for GPU stats
  
  health_checks:
    interval: 30            # Health check interval in seconds
    endpoints:
      - "http://localhost:11434/api/tags"  # Ollama health
      - "redis://localhost:6379"          # Redis health

# Network Configuration
network:
  share:
    enabled: false
    path: "${NETWORK_SHARE_PATH}"
    username: "${NETWORK_SHARE_USERNAME}" 
    password: "${NETWORK_SHARE_PASSWORD}"
  
  proxy:
    enabled: false
    http: "${HTTP_PROXY}"
    https: "${HTTPS_PROXY}"
    no_proxy: "localhost,127.0.0.1"

# Development & Debug Settings
development:
  debug_mode: false
  hot_reload: false
  verbose_logging: false
  
  profiling:
    enabled: false
    output_directory: "logs/profiling"
  
  testing:
    mock_llm: false
    mock_redis: false
    test_data_directory: "tests/data"

# Feature Flags
features:
  langchain_agent: true      # Enable LangChain integration
  worker_nodes: true         # Enable distributed worker nodes
  voice_interface: false     # Enable voice commands
  gui_automation: true       # Enable GUI control
  file_browser: true         # Enable file management
  knowledge_base: true       # Enable knowledge base features
  chat_history: true         # Enable chat persistence
  system_commands: true      # Enable system command execution
```

---

## Configuration Sections Explained

### 1. Backend Server (`backend`)
Controls the FastAPI web server settings.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | "0.0.0.0" | Server bind address |
| `port` | integer | 8001 | Server port number |
| `cors_origins` | array | ["http://localhost:8080"] | Allowed CORS origins |
| `static_files.directory` | string | "frontend/static" | Static files directory |

**Example:**
```yaml
backend:
  host: "127.0.0.1"  # Localhost only
  port: 9000         # Custom port
  cors_origins:
    - "http://localhost:3000"
    - "https://myapp.com"
```

### 2. LLM Configuration (`llm`)
Controls AI language model settings.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | string | "ollama" | LLM provider (ollama/openai/huggingface) |
| `model` | string | "phi:2.7b" | Default model name |
| `temperature` | float | 0.7 | Response creativity (0.0-2.0) |
| `max_tokens` | integer | 2048 | Maximum response length |
| `timeout` | integer | 30 | Request timeout in seconds |

**Provider-Specific Settings:**

**Ollama:**
```yaml
llm:
  ollama:
    base_url: "http://localhost:11434"
    models: ["phi:2.7b", "llama2", "mistral"]
```

**OpenAI:**
```yaml
llm:
  openai:
    api_key: "${OPENAI_API_KEY}"
    models: ["gpt-3.5-turbo", "gpt-4"]
```

### 3. Memory & Storage (`memory`)
Controls data persistence and caching.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `redis.enabled` | boolean | true | Enable Redis for memory |
| `redis.host` | string | "localhost" | Redis server address |
| `redis.port` | integer | 6379 | Redis server port |
| `redis.db` | integer | 1 | Redis database number |
| `sqlite.enabled` | boolean | true | Enable SQLite storage |

**Redis Configuration:**
```yaml
memory:
  redis:
    enabled: true
    host: "redis.example.com"
    port: 6380
    password: "secure_password"
    db: 2
    connection_pool:
      max_connections: 100
```

### 4. Task Management (`tasks`)
Controls task execution and scheduling.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `transport` | string | "redis" | Task transport method |
| `max_concurrent` | integer | 5 | Maximum concurrent tasks |
| `timeout` | integer | 300 | Task timeout in seconds |
| `retry_attempts` | integer | 3 | Number of retry attempts |

### 5. Knowledge Base (`llama_index`)
Controls LlamaIndex vector storage and retrieval.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vector_store.type` | string | "redis" | Vector store backend |
| `embedding.model` | string | "nomic-embed-text" | Embedding model |
| `chunk_size` | integer | 512 | Document chunk size |
| `retrieval.similarity_top_k` | integer | 5 | Number of results to retrieve |

### 6. Security (`security`)
Controls authentication and authorization.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `authentication.enabled` | boolean | false | Enable user authentication |
| `permissions.default_role` | string | "user" | Default user role |
| `audit.enabled` | boolean | true | Enable audit logging |

### 7. Logging (`logging`)
Controls application logging behavior.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `level` | string | "INFO" | Log level |
| `max_file_size` | integer | 10485760 | Max log file size (bytes) |
| `backup_count` | integer | 5 | Number of backup files |

---

## Environment Variables

AutoBot supports environment variable substitution in configuration files using `${VARIABLE_NAME}` syntax.

### Common Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | `sk-...` |
| `HUGGINGFACE_TOKEN` | HuggingFace API token | `hf_...` |
| `REDIS_PASSWORD` | Redis server password | `secure123` |
| `NETWORK_SHARE_PATH` | Network share mount path | `/mnt/share` |
| `NETWORK_SHARE_USERNAME` | Network share username | `user` |
| `NETWORK_SHARE_PASSWORD` | Network share password | `password` |
| `HTTP_PROXY` | HTTP proxy server | `http://proxy:8080` |
| `HTTPS_PROXY` | HTTPS proxy server | `https://proxy:8080` |

### Setting Environment Variables

**Linux/macOS:**
```bash
export OPENAI_API_KEY="sk-your-api-key-here"
export REDIS_PASSWORD="your-redis-password"
```

**Windows:**
```cmd
set OPENAI_API_KEY=sk-your-api-key-here
set REDIS_PASSWORD=your-redis-password
```

**Docker Environment:**
```bash
docker run -e OPENAI_API_KEY="sk-..." -e REDIS_PASSWORD="..." autobot
```

---

## Configuration Methods

### 1. Configuration File Editing

Edit `config/config.yaml` directly:
```bash
nano config/config.yaml
```

### 2. API-Based Configuration

Update settings via REST API:
```bash
# Get current settings
curl http://localhost:8001/api/settings

# Update settings
curl -X POST http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{"llm": {"temperature": 0.8}}'
```

### 3. Runtime Configuration

Settings can be modified at runtime and will be saved to `config/settings.json`.

### 4. Environment Override

Set environment variables to override config values:
```bash
export AUTOBOT_LLM_TEMPERATURE=0.9
export AUTOBOT_BACKEND_PORT=9000
```

---

## Configuration Validation

AutoBot validates configuration on startup and provides detailed error messages for invalid settings.

### Common Validation Rules

1. **Port numbers**: Must be between 1-65535
2. **File paths**: Must be accessible and writable
3. **URLs**: Must be valid HTTP/HTTPS URLs
4. **Boolean values**: Must be `true` or `false`
5. **Numeric ranges**: Temperature (0.0-2.0), timeouts (> 0)

### Validation Examples

**Invalid Configuration:**
```yaml
backend:
  port: 99999  # ERROR: Port out of range
llm:
  temperature: 3.0  # ERROR: Temperature too high
```

**Valid Configuration:**
```yaml
backend:
  port: 8080   # OK: Valid port range
llm:
  temperature: 0.8  # OK: Valid temperature range
```

---

## Configuration Templates

### Minimal Configuration
```yaml
version: "1.0"
backend:
  port: 8001
llm:
  provider: "ollama"
  model: "phi:2.7b"
memory:
  redis:
    enabled: true
```

### Production Configuration
```yaml
version: "1.0"
backend:
  host: "0.0.0.0"
  port: 8001
llm:
  provider: "openai"
  model: "gpt-3.5-turbo"
  api_key: "${OPENAI_API_KEY}"
memory:
  redis:
    enabled: true
    host: "redis-cluster.internal"
    password: "${REDIS_PASSWORD}"
security:
  authentication:
    enabled: true
  audit:
    enabled: true
logging:
  level: "WARNING"
```

### Development Configuration
```yaml
version: "1.0"
backend:
  port: 8001
llm:
  provider: "ollama"
  model: "phi:2.7b"
development:
  debug_mode: true
  verbose_logging: true
logging:
  level: "DEBUG"
```

---

## Configuration Best Practices

### 1. Security
- Store sensitive values in environment variables
- Never commit API keys or passwords to version control
- Use strong passwords for Redis and database connections
- Enable authentication in production environments

### 2. Performance
- Adjust `max_concurrent` tasks based on system resources
- Configure appropriate timeouts for your network environment
- Use Redis connection pooling for high-load scenarios
- Set reasonable chunk sizes for knowledge base operations

### 3. Reliability
- Enable audit logging for troubleshooting
- Configure appropriate retry attempts and timeouts
- Use backup and cleanup settings for log files
- Monitor disk space usage with data retention policies

### 4. Monitoring
- Enable diagnostics and health checks
- Set appropriate collection intervals
- Configure log levels based on environment
- Use proper CORS origins for security

---

## Troubleshooting Configuration

### Common Issues

1. **Port Already in Use**
   ```yaml
   backend:
     port: 8002  # Change to available port
   ```

2. **Redis Connection Failed**
   ```yaml
   memory:
     redis:
       host: "localhost"  # Verify Redis server address
       port: 6379         # Verify Redis port
   ```

3. **LLM Connection Timeout**
   ```yaml
   llm:
     timeout: 60  # Increase timeout for slow connections
   ```

4. **File Permission Errors**
   ```bash
   chmod 755 data/          # Ensure data directory is writable
   chmod 644 config/*.yaml  # Ensure config files are readable
   ```

### Configuration Validation Command
```bash
# Validate configuration without starting the application
python -m src.config --validate
```

---

## Configuration Migration

When upgrading AutoBot versions, configuration files may need migration:

1. **Backup current configuration:**
   ```bash
   cp config/config.yaml config/config.yaml.backup
   ```

2. **Check for new configuration options:**
   ```bash
   diff config/config.yaml.template config/config.yaml
   ```

3. **Update configuration file** with new required fields

4. **Validate updated configuration:**
   ```bash
   python -m src.config --validate
   ```

This comprehensive configuration documentation covers all aspects of AutoBot's configuration system, from basic setup to advanced production deployments.
