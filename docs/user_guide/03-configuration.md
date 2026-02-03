# User Configuration Guide

Simple, user-friendly configuration options for AutoBot. For detailed technical configuration, see [Complete Configuration Reference](../configuration.md).

## Quick Configuration

### Accessing Settings

AutoBot provides multiple ways to configure settings:

1. **Web Interface**: Click the gear icon (⚙️) in the web interface
2. **Chat Commands**: Type `/settings` in the chat
3. **Configuration File**: Edit `config/config.yaml` directly

### Essential Settings

#### Choose Your AI Provider

**Option 1: Ollama (Local, Free)**
```yaml
llm_config:
  default_llm: "ollama_tinyllama"
  ollama:
    host: "http://localhost:11434"
```

**Option 2: OpenAI (Cloud, Paid)**
```yaml
llm_config:
  default_llm: "openai_gpt35"
  openai:
    api_key: ""  # Set via environment variable OPENAI_API_KEY
```

**Option 3: Anthropic Claude (Cloud, Paid)**
```yaml
llm_config:
  default_llm: "anthropic_claude"
  anthropic:
    api_key: ""  # Set via environment variable ANTHROPIC_API_KEY
```

#### Basic System Settings

```yaml
# Change ports if needed
backend:
  server_port: 8001

# Frontend port (if running development server)
frontend:
  port: 5173

# Enable/disable features
memory:
  redis:
    enabled: true    # Set false if Redis not available
  chromadb:
    enabled: true    # Vector database for knowledge search
```

## Configuration Through Web Interface

### LLM Settings

1. **Access Settings**: Click ⚙️ icon → "LLM Configuration"
2. **Choose Provider**: Select Ollama, OpenAI, or Anthropic
3. **Select Model**: Pick from available models
4. **Adjust Temperature**:
   - Low (0.1-0.3): More focused, deterministic responses
   - Medium (0.4-0.7): Balanced creativity and consistency
   - High (0.8-1.0): More creative, varied responses

### System Behavior

1. **Access Settings**: Click ⚙️ icon → "Agent Behavior"
2. **Autonomy Level**:
   - **Supervised**: Asks permission for system commands (recommended)
   - **Autonomous**: Executes approved commands automatically
   - **Restricted**: Chat only, no system access
3. **Command Permissions**: Enable/disable file system, network, and command execution

### Performance Settings

1. **Access Settings**: Click ⚙️ icon → "Performance"
2. **Hardware Acceleration**: Enable GPU if available
3. **Memory Limits**: Set RAM usage limits
4. **Model Options**: Choose faster vs higher quality models

## Common Configuration Scenarios

### Home User Setup (Recommended)

```yaml
llm_config:
  default_llm: "ollama_tinyllama"  # Fast, local, free

agent:
  autonomy_level: "supervised"     # Safe, asks permission

memory:
  redis:
    enabled: true                  # Enhanced features
  chromadb:
    enabled: true                  # Knowledge search

hardware:
  gpu:
    enabled: false                 # Use CPU (stable)
```

### Developer Setup

```yaml
llm_config:
  default_llm: "ollama_llama2"     # Better code understanding

agent:
  autonomy_level: "autonomous"     # Faster workflow
  max_task_depth: 15               # Complex tasks

debugging:
  enabled: true                    # Development tools
  log_level: "debug"               # Detailed logs

hardware:
  gpu:
    enabled: true                  # Faster inference
```

### Enterprise Setup

```yaml
llm_config:
  default_llm: "openai_gpt4"       # Highest quality

security:
  strict_mode: true                # Enhanced security
  command_filter:
    enabled: true                  # Filter dangerous commands

logging:
  audit_enabled: true              # Compliance logging
  retention_days: 90               # Keep logs longer

network:
  require_auth: true               # Authentication required
```

## Environment Variables

For sensitive information, use environment variables instead of config files:

```bash
# AI Provider API Keys
export OPENAI_API_KEY="your-openai-key"  # pragma: allowlist secret
export ANTHROPIC_API_KEY="your-anthropic-key"  # pragma: allowlist secret

# Server Configuration
export AUTOBOT_BACKEND_PORT=8001
export AUTOBOT_FRONTEND_PORT=5173

# Redis Configuration
export AUTOBOT_REDIS_HOST="localhost"
export AUTOBOT_REDIS_PORT=6379
export AUTOBOT_REDIS_PASSWORD="your-password"  # pragma: allowlist secret

# Security
export AUTOBOT_SECRET_KEY="your-secure-secret"  # pragma: allowlist secret
```

Add these to your shell profile (`.bashrc`, `.zshrc`) to persist across sessions.

## Configuration Validation

### Check Configuration

```bash
# Validate configuration file
python -c "from src.config import config; print('✓ Configuration valid')"

# Test specific components
python -c "from src.diagnostics import check_llm; check_llm()"
python -c "from src.diagnostics import check_redis; check_redis()"
```

### Configuration Status

Use the web interface or chat commands:

```
/status config
```

```
/settings validate
```

## Backup and Restore

### Backup Current Configuration

```bash
# Create timestamped backup
cp config/config.yaml config/config.backup.$(date +%Y%m%d_%H%M%S).yaml

# Quick backup
cp config/config.yaml config/config.backup.yaml
```

### Restore Configuration

```bash
# Restore from backup
cp config/config.backup.yaml config/config.yaml

# Reset to defaults
cp config/config.yaml.template config/config.yaml
```

### Export Settings

Through web interface:
1. Settings → "Export Configuration"
2. Save the downloaded file as backup
3. Import on other AutoBot instances

## Troubleshooting Configuration

### Common Issues

**Issue: Changes not taking effect**
- Restart AutoBot: `./run_agent.sh`
- Check configuration syntax: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`

**Issue: LLM connection failed**
- Verify API keys in environment variables
- For Ollama: ensure service is running (`ollama serve`)
- Check network connectivity

**Issue: Port conflicts**
- Change ports in configuration:
```yaml
backend:
  server_port: 8002  # Change from default 8001
```

**Issue: Performance problems**
- Disable GPU if causing issues:
```yaml
hardware:
  gpu:
    enabled: false
```
- Use lighter models (tinyllama instead of llama2)

### Configuration Help

1. **Built-in Validation**: AutoBot validates configuration on startup
2. **Web Interface**: Visual feedback for configuration errors
3. **Log Files**: Check `logs/autobot.log` for configuration issues
4. **Chat Support**: Ask AutoBot about configuration: "Help me configure my settings"

## Advanced Configuration

For advanced users who need detailed technical configuration:

- **[Complete Configuration Reference](../configuration.md)**: All YAML sections and options
- **[API Configuration](../backend_api.md)**: REST API settings and security
- **[Developer Configuration](../project.md)**: Development and deployment options

## Configuration Best Practices

### Security
1. **Never commit API keys** to version control
2. **Use environment variables** for sensitive data
3. **Set secure file permissions**: `chmod 600 config/config.yaml`
4. **Regular backups** of working configurations

### Performance
1. **Start simple**: Use default settings first
2. **Monitor resources**: Watch CPU/RAM usage
3. **GPU acceleration**: Enable only if stable
4. **Model selection**: Balance speed vs quality

### Maintenance
1. **Version control**: Track configuration changes
2. **Documentation**: Comment complex settings
3. **Testing**: Validate after changes
4. **Monitoring**: Watch logs for issues

---

**Need more advanced configuration options?** See the [Complete Configuration Reference](../configuration.md) for technical details.
