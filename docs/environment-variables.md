# Environment Variables Reference

AutoBot supports comprehensive configuration through environment variables with the `AUTOBOT_` prefix. All variables have fallback defaults defined in `config/config.yaml`.

## Backend Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_BACKEND_HOST` | `0.0.0.0` | Backend server host |
| `AUTOBOT_BACKEND_PORT` | `8001` | Backend server port |
| `AUTOBOT_BACKEND_API_ENDPOINT` | `http://localhost:8001` | Full API endpoint URL |
| `AUTOBOT_BACKEND_TIMEOUT` | `60` | Request timeout in seconds |
| `AUTOBOT_BACKEND_MAX_RETRIES` | `3` | Maximum retry attempts |
| `AUTOBOT_BACKEND_STREAMING` | `false` | Enable streaming responses |

## LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_OLLAMA_HOST` | `http://localhost:11434` | Ollama server endpoint |
| `AUTOBOT_OLLAMA_MODEL` | `deepseek-r1:14b` | Default Ollama model |
| `AUTOBOT_OLLAMA_ENDPOINT` | `http://localhost:11434/api/generate` | Ollama API endpoint |
| `AUTOBOT_OLLAMA_SELECTED_MODEL` | `deepseek-r1:14b` | Currently selected Ollama model |
| `AUTOBOT_ORCHESTRATOR_LLM` | `deepseek-r1:14b` | LLM model for orchestrator |
| `AUTOBOT_DEFAULT_LLM` | `ollama_deepseek-r1:14b` | Default LLM identifier |
| `AUTOBOT_TASK_LLM` | `ollama_deepseek-r1:14b` | Task-specific LLM identifier |
| `AUTOBOT_LLM_PROVIDER_TYPE` | `local` | LLM provider type (local/cloud) |

## Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_REDIS_HOST` | `localhost` | Redis server host |
| `AUTOBOT_REDIS_PORT` | `6379` | Redis server port |
| `AUTOBOT_REDIS_ENABLED` | `false` | Enable Redis for memory storage |

## Chat Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_CHAT_MAX_MESSAGES` | `100` | Maximum messages per chat |
| `AUTOBOT_CHAT_WELCOME_MESSAGE` | `Hello! How can I assist you today?` | Default welcome message |
| `AUTOBOT_CHAT_AUTO_SCROLL` | `true` | Auto-scroll chat interface |
| `AUTOBOT_CHAT_RETENTION_DAYS` | `30` | Chat message retention period |

## Knowledge Base Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_KB_ENABLED` | `true` | Enable knowledge base |
| `AUTOBOT_KB_UPDATE_FREQUENCY` | `7` | Update frequency in days |
| `AUTOBOT_KB_DB_PATH` | `` | Knowledge base database path |

## Logging Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_LOG_LEVEL` | `info` | Logging level (debug/info/warning/error) |
| `AUTOBOT_LOG_TO_FILE` | `false` | Enable file logging |
| `AUTOBOT_LOG_FILE_PATH` | `` | Log file path |

## Developer Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_DEVELOPER_MODE` | `false` | Enable developer mode |
| `AUTOBOT_DEBUG_LOGGING` | `false` | Enable debug logging |
| `AUTOBOT_ENHANCED_ERRORS` | `true` | Show enhanced error messages |

## UI Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_UI_THEME` | `light` | UI theme (light/dark) |
| `AUTOBOT_UI_FONT_SIZE` | `medium` | Font size (small/medium/large) |
| `AUTOBOT_UI_LANGUAGE` | `en` | Interface language |
| `AUTOBOT_UI_ANIMATIONS` | `true` | Enable UI animations |

## Message Display Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_SHOW_THOUGHTS` | `true` | Show thought messages |
| `AUTOBOT_SHOW_JSON` | `false` | Show JSON output |
| `AUTOBOT_SHOW_DEBUG` | `false` | Show debug messages |
| `AUTOBOT_SHOW_PLANNING` | `true` | Show planning messages |
| `AUTOBOT_SHOW_UTILITY` | `false` | Show utility messages |

## Security Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_ENABLE_ENCRYPTION` | `false` | Enable data encryption |
| `AUTOBOT_SESSION_TIMEOUT` | `30` | Session timeout in minutes |

## Voice Interface Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_VOICE_ENABLED` | `false` | Enable voice interface |
| `AUTOBOT_VOICE_RATE` | `1` | Speech rate multiplier |
| `AUTOBOT_VOICE` | `default` | Voice selection |

## Legacy Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_USE_LANGCHAIN` | `false` | Use LangChain orchestrator |
| `AUTOBOT_USE_PHI2` | `false` | Use Phi-2 model (deprecated) |

## Frontend Configuration

The frontend uses Vite environment variables with the `VITE_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8001` | Backend API base URL |

## Usage Examples

### Setting Model to DeepSeek
```bash
export AUTOBOT_OLLAMA_MODEL="deepseek-r1:14b"
export AUTOBOT_ORCHESTRATOR_LLM="deepseek-r1:14b"
```

### Using Different Backend Port
```bash
export AUTOBOT_BACKEND_PORT=8002
export AUTOBOT_BACKEND_API_ENDPOINT="http://localhost:8002"
export VITE_API_BASE_URL="http://localhost:8002"
```

### Enable Redis
```bash
export AUTOBOT_REDIS_ENABLED=true
export AUTOBOT_REDIS_HOST="redis.example.com"
export AUTOBOT_REDIS_PORT=6380
```

### Developer Mode
```bash
export AUTOBOT_DEVELOPER_MODE=true
export AUTOBOT_DEBUG_LOGGING=true
export AUTOBOT_LOG_LEVEL=debug
```

## Configuration Priority

Environment variables take precedence over config file values:

1. **Environment Variables** (highest priority)
2. **config/config.yaml** (fallback defaults)
3. **Hardcoded defaults** (last resort, now eliminated)

## Validation

The system validates environment variables on startup and logs applied overrides. Invalid values will fall back to config file defaults with warnings logged.
