# SSOT Configuration Guide

> **Single Source of Truth (SSOT) Configuration System Developer Guide**
>
> Part of Issue #604 - SSOT Phase 4 Cleanup

## Overview

AutoBot uses a **Single Source of Truth (SSOT)** configuration pattern where all configuration values originate from environment variables defined in the `.env` file. This approach ensures consistency across all components (Python backend, TypeScript frontend, shell scripts) and eliminates configuration drift.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     .env (Master SSOT)                          │
│  AUTOBOT_BACKEND_HOST=172.16.168.20                            │
│  AUTOBOT_FRONTEND_HOST=172.16.168.21                           │
│  AUTOBOT_REDIS_HOST=172.16.168.23                              │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Python Backend │  │    Frontend     │  │  Shell Scripts  │
│  ssot_config.py │  │  ssot-config.ts │  │  source .env    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Quick Reference

### Python (Backend)

```python
from src.config.ssot_config import config

# Access configuration values
backend_host = config.backend.host        # "172.16.168.20"
redis_url = config.redis.url              # Full connection URL
llm_model = config.llm.default_model      # "llama3.2:3b"

# Get full URL for a service
api_url = config.backend.url              # "http://172.16.168.20:8001"
```

### TypeScript (Frontend)

```typescript
import { getConfig, getBackendUrl, getRedisUrl } from '@/config/ssot-config'

// Access configuration
const config = getConfig()
const backendHost = config.backend.host   // "172.16.168.20"

// Get full URLs
const apiUrl = getBackendUrl()            // "http://172.16.168.20:8001"
const redisUrl = getRedisUrl()            // Full Redis connection URL
```

### Shell Scripts

```bash
# Load SSOT configuration at script start
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a  # Automatically export all variables
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Use variables with fallbacks
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
```

## Environment Variables

All SSOT variables use the `AUTOBOT_` prefix. Here's the complete list:

### Network Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_BACKEND_HOST` | `172.16.168.20` | Backend API server IP |
| `AUTOBOT_BACKEND_PORT` | `8001` | Backend API port |
| `AUTOBOT_FRONTEND_HOST` | `172.16.168.21` | Frontend server IP |
| `AUTOBOT_FRONTEND_PORT` | `5173` | Frontend dev server port |
| `AUTOBOT_REDIS_HOST` | `172.16.168.23` | Redis server IP |
| `AUTOBOT_REDIS_PORT` | `6379` | Redis port |
| `AUTOBOT_NPU_WORKER_HOST` | `172.16.168.22` | NPU Worker IP |
| `AUTOBOT_NPU_WORKER_PORT` | `8081` | NPU Worker port |
| `AUTOBOT_AI_STACK_HOST` | `172.16.168.24` | AI Stack IP |
| `AUTOBOT_AI_STACK_PORT` | `8080` | AI Stack port |
| `AUTOBOT_BROWSER_SERVICE_HOST` | `172.16.168.25` | Browser service IP |
| `AUTOBOT_BROWSER_SERVICE_PORT` | `3000` | Browser service port |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_DEFAULT_LLM_MODEL` | `llama3.2:3b` | Default LLM model |
| `AUTOBOT_OLLAMA_HOST` | `172.16.168.24` | Ollama API host |
| `AUTOBOT_OLLAMA_PORT` | `11434` | Ollama API port |

### Redis Databases

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_REDIS_DB_MAIN` | `0` | Main cache/queues |
| `AUTOBOT_REDIS_DB_KNOWLEDGE` | `1` | Knowledge base vectors |
| `AUTOBOT_REDIS_DB_PROMPTS` | `2` | LLM prompts/templates |
| `AUTOBOT_REDIS_DB_ANALYTICS` | `3` | Analytics data |

## Best Practices

### DO: Use SSOT Config Loaders

```python
# ✅ CORRECT - Python
from src.config.ssot_config import config
redis_host = config.redis.host
```

```typescript
// ✅ CORRECT - TypeScript
import { getConfig } from '@/config/ssot-config'
const redisHost = getConfig().redis.host
```

```bash
# ✅ CORRECT - Shell
source "$PROJECT_ROOT/.env"
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
```

### DON'T: Hardcode Values

```python
# ❌ WRONG - Hardcoded IP
redis_host = "172.16.168.23"

# ❌ WRONG - Direct os.getenv without SSOT
redis_host = os.getenv("REDIS_HOST", "localhost")
```

```typescript
// ❌ WRONG - Hardcoded
const redisHost = "172.16.168.23"
```

```bash
# ❌ WRONG - Hardcoded in script
REDIS_HOST="172.16.168.23"
```

### DO: Use Fallbacks in Shell Scripts

Always provide fallback values when using environment variables in shell scripts:

```bash
# ✅ CORRECT - With fallback
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

# ❌ WRONG - No fallback (will fail if .env missing)
BACKEND_PORT="$AUTOBOT_BACKEND_PORT"
```

### DO: Load .env at Script Start

Load the `.env` file at the beginning of every shell script:

```bash
#!/bin/bash
set -e

# =============================================================================
# SSOT Configuration - Load from .env file (Single Source of Truth)
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Now use AUTOBOT_* variables...
```

## Migration Guide

### Migrating Python Code

**Before (hardcoded):**
```python
import redis
client = redis.Redis(host="172.16.168.23", port=6379, db=0)
```

**After (SSOT):**
```python
from src.config.ssot_config import config
import redis

client = redis.Redis(
    host=config.redis.host,
    port=config.redis.port,
    db=config.redis.db_main
)
```

### Migrating TypeScript Code

**Before (hardcoded):**
```typescript
const API_URL = "http://172.16.168.20:8001"
```

**After (SSOT):**
```typescript
import { getBackendUrl } from '@/config/ssot-config'
const API_URL = getBackendUrl()
```

### Migrating Shell Scripts

**Before (hardcoded):**
```bash
REMOTE_HOST="172.16.168.21"
ssh autobot@$REMOTE_HOST "command"
```

**After (SSOT):**
```bash
# Load .env first (see template above)
REMOTE_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
ssh autobot@$REMOTE_HOST "command"
```

## Validation

### Pre-commit Hook

A pre-commit hook validates that new code doesn't introduce hardcoded values:

```bash
# Runs automatically on git commit
./scripts/detect-hardcoded-values.sh
```

### Manual Check

Run the detection script manually:

```bash
./scripts/detect-hardcoded-values.sh

# Expected output for clean code:
# ✅ No hardcoding violations found!
```

## Troubleshooting

### ".env file not found" Warning

If you see this warning, ensure the `.env` file exists:

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Configuration Not Loading

1. Verify `.env` exists in project root
2. Check variable naming (must use `AUTOBOT_` prefix)
3. Ensure no syntax errors in `.env` file
4. Restart services after `.env` changes

### Shell Script Not Finding .env

Ensure correct path resolution:

```bash
# ✅ CORRECT - Dynamic path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ❌ WRONG - Relative path (depends on working directory)
source "../../.env"
```

## Related Documentation

- [HARDCODING_PREVENTION.md](HARDCODING_PREVENTION.md) - Hardcoding policy
- [REDIS_CLIENT_USAGE.md](REDIS_CLIENT_USAGE.md) - Redis client patterns
- [SSOT_CONFIGURATION_ARCHITECTURE.md](../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md) - Full architecture spec

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Issue**: #604 - SSOT Phase 4 Cleanup