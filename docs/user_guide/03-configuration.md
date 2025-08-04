# Configuration Guide

## Configuration Overview

AutoBot uses a centralized configuration system based on YAML files and a web-based control panel. All settings are stored in `config/config.yaml`.

## Configuration Structure

```yaml
# Main configuration sections
llm:           # LLM backend settings
memory:        # Redis and memory configuration
agent:         # Core agent behavior
network:       # Network and security settings
logging:       # Log levels and destinations
hardware:      # GPU/NPU acceleration settings
```

## LLM Configuration

### Ollama (Local Inference)
```yaml
llm:
  provider: "ollama"
  model: "phi3:mini"
  ollama:
    base_url: "http://localhost:11434"
    temperature: 0.7
    max_tokens: 2048
```

### OpenAI API
```yaml
llm:
  provider: "openai"
  model: "gpt-4"
  openai:
    api_key: "your-api-key-here"
    temperature: 0.7
    max_tokens: 2048
```

### Hardware Acceleration
```yaml
hardware:
  gpu:
    enabled: true
    device: "cuda:0"  # or "rocm:0", "cpu"
    layers_offload: 32
    precision: "fp16"  # or "fp32", "int8"
```

## Memory and Storage

### Redis Configuration
```yaml
memory:
  redis:
    enabled: true
    host: "localhost"
    port: 6379
    password: null
    db: 0
    index_name: "autobot_knowledge_index"
```

### Knowledge Base Storage
```yaml
knowledge_base:
  storage_path: "./data/knowledge_base.db"
  vector_store: "redis"  # or "chromadb", "faiss"
  embedding_model: "nomic-embed-text"
```

## Network Settings

### Web Interface
```yaml
network:
  web_interface:
    host: "0.0.0.0"
    port: 8001
    enable_cors: true

  api:
    host: "0.0.0.0"
    port: 8001
```

### Worker Nodes
```yaml
workers:
  enabled: false
  discovery:
    method: "manual"  # or "automatic"
    port: 8002
  security:
    require_auth: true
    secret_key: "your-secret-here"
```

## Agent Behavior

### Core Settings
```yaml
agent:
  autonomy_level: "supervised"  # or "autonomous", "restricted"
  max_task_depth: 10
  timeout_seconds: 300

  permissions:
    file_system: true
    network_access: true
    system_commands: true
    package_install: false
```

### Safety Features
```yaml
safety:
  command_filter:
    enabled: true
    blacklist: ["rm -rf", "format", "delete"]

  resource_limits:
    max_memory_mb: 4096
    max_cpu_percent: 80
```

## Logging Configuration

```yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR

  files:
    agent_log: "logs/agent.log"
    llm_usage: "logs/llm_usage.log"
    error_log: "logs/errors.log"

  rotation:
    max_size_mb: 100
    backup_count: 5
```

## Environment-Specific Settings

### Development
```yaml
environment: "development"
debug: true
auto_reload: true
```

### Production
```yaml
environment: "production"
debug: false
security:
  strict_mode: true
  require_https: true
```

## Configuration via Web Interface

Most settings can be modified through the web control panel:

1. **Access Settings**: Type `/settings open` or click the settings icon
2. **Navigate Sections**: Use tabs for different configuration areas
3. **Apply Changes**: Settings are saved automatically
4. **Restart**: Some changes require agent restart

## Environment Variables

Sensitive settings can be overridden with environment variables:

```bash
export AUTOBOT_OPENAI_API_KEY="your-key"
export AUTOBOT_REDIS_PASSWORD="your-password"
export AUTOBOT_SECRET_KEY="your-secret"
```

## Configuration Validation

AutoBot validates configuration on startup:

```bash
# Check configuration
python -c "from src.config import config; config.validate()"
```

## Backup and Restore

### Backup Configuration
```bash
cp config/config.yaml config/config.backup.yaml
```

### Reset to Defaults
```bash
cp config/config.yaml.template config/config.yaml
```

## Advanced Topics

- **Multiple Profiles**: Switch between configuration profiles
- **Dynamic Updates**: Modify settings without restart
- **Distributed Configuration**: Sync settings across worker nodes
- **Security Hardening**: Encryption and access controls
