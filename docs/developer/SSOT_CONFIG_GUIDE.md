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
│  AUTOBOT_BACKEND_HOST=<backend-ip>                            │
│  AUTOBOT_FRONTEND_HOST=<frontend-ip>                           │
│  AUTOBOT_REDIS_HOST=<database-ip>                              │
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
from autobot_shared.ssot_config import config

# Access configuration values
backend_host = config.backend.host        # "<backend-ip>"
redis_url = config.redis.url              # Full connection URL
llm_model = config.llm.default_model      # "qwen3.5:9b"

# Get full URL for a service
api_url = config.backend.url              # "https://<backend-ip>:8443"
```

### TypeScript (Frontend)

```typescript
import { getConfig, getBackendUrl, getRedisUrl } from '@/config/ssot-config'

// Access configuration
const config = getConfig()
const backendHost = config.backend.host   // "<backend-ip>"

// Get full URLs
const apiUrl = getBackendUrl()            // "https://<backend-ip>:8443"
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
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-<backend-ip>}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
```

## Environment Variables

All SSOT variables use the `AUTOBOT_` prefix. Here's the complete list:

### Network Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_BACKEND_HOST` | `<backend-ip>` | Backend API server IP |
| `AUTOBOT_BACKEND_PORT` | `8001` | Backend API port |
| `AUTOBOT_FRONTEND_HOST` | `<frontend-ip>` | Frontend server IP |
| `AUTOBOT_FRONTEND_PORT` | `5173` | Frontend dev server port |
| `AUTOBOT_REDIS_HOST` | `<database-ip>` | Redis server IP |
| `AUTOBOT_REDIS_PORT` | `6379` | Redis port |
| `AUTOBOT_NPU_WORKER_HOST` | `<npu-ip>` | NPU Worker IP |
| `AUTOBOT_NPU_WORKER_PORT` | `8081` | NPU Worker port |
| `AUTOBOT_AI_STACK_HOST` | `<aiml-ip>` | AI Stack IP |
| `AUTOBOT_AI_STACK_PORT` | `8080` | AI Stack port |
| `AUTOBOT_BROWSER_SERVICE_HOST` | `<browser-ip>` | Browser service IP |
| `AUTOBOT_BROWSER_SERVICE_PORT` | `3000` | Browser service port |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_DEFAULT_LLM_MODEL` | `qwen3.5:9b` | Default LLM model |
| `AUTOBOT_OLLAMA_HOST` | `127.0.0.1` | Ollama API host |
| `AUTOBOT_OLLAMA_PORT` | `11434` | Ollama API port |

### Redis Databases

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_REDIS_DB_MAIN` | `0` | Main cache/queues |
| `AUTOBOT_REDIS_DB_KNOWLEDGE` | `1` | Knowledge base vectors |
| `AUTOBOT_REDIS_DB_PROMPTS` | `2` | LLM prompts/templates |
| `AUTOBOT_REDIS_DB_ANALYTICS` | `3` | Analytics data |

## ConfigRegistry and Registry Defaults

The `ConfigRegistry` (in `autobot-backend/config/registry.py`) provides a five-tier fallback chain:

```
Cache → Redis → Environment → Registry Defaults → Caller Default
```

As of Issue #2671, `registry_defaults.py` sources all its values from the SSOT config at import time:

```python
from autobot_shared.ssot_config import get_config

_ssot = get_config()

REGISTRY_DEFAULTS = {
    "vm.main": _ssot.vm.main,          # From .env or pydantic default
    "vm.redis": _ssot.vm.redis,
    "port.backend": str(_ssot.port.backend),
    # ... all values from SSOT
}
```

This means `ConfigRegistry.get()` callers **no longer need hardcoded fallbacks**:

```python
# ✅ CORRECT — registry_defaults provides SSOT-sourced fallback
redis_host = ConfigRegistry.get("vm.redis")

# ❌ WRONG — redundant hardcoded fallback
redis_host = ConfigRegistry.get("vm.redis", "<database-ip>")
```

## Best Practices

### DO: Use SSOT Config Loaders

```python
# ✅ CORRECT - Python
from autobot_shared.ssot_config import config
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
REDIS_HOST="${AUTOBOT_REDIS_HOST:-<database-ip>}"
```

### DON'T: Hardcode Values

```python
# ❌ WRONG - Hardcoded IP
redis_host = "<database-ip>"

# ❌ WRONG - Direct os.getenv without SSOT
redis_host = os.getenv("REDIS_HOST", "localhost")
```

```typescript
// ❌ WRONG - Hardcoded
const redisHost = "<database-ip>"
```

```bash
# ❌ WRONG - Hardcoded in script
REDIS_HOST="<database-ip>"
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
client = redis.Redis(host="<database-ip>", port=6379, db=0)
```

**After (SSOT):**
```python
from autobot_shared.ssot_config import config
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
const API_URL = "https://<backend-ip>:8443"
```

**After (SSOT):**
```typescript
import { getBackendUrl } from '@/config/ssot-config'
const API_URL = getBackendUrl()
```

### Migrating Shell Scripts

**Before (hardcoded):**
```bash
REMOTE_HOST="<frontend-ip>"
ssh autobot@$REMOTE_HOST "command"
```

**After (SSOT):**
```bash
# Load .env first (see template above)
REMOTE_HOST="${AUTOBOT_FRONTEND_HOST:-<frontend-ip>}"
ssh autobot@$REMOTE_HOST "command"
```

## Validation & Enforcement

### Pre-commit Hook (Issue #642)

The enhanced SSOT-aware pre-commit hook validates that new code doesn't introduce hardcoded values and specifically identifies when hardcoded values have SSOT config equivalents:

```bash
# Runs automatically on git commit
./scripts/detect-hardcoded-values.sh
```

### Manual Check

Run the detection script manually with different modes:

```bash
# Standard check
./scripts/detect-hardcoded-values.sh

# Expected output for clean code:
# ✅ No hardcoding violations found!

# Generate detailed compliance report
./scripts/detect-hardcoded-values.sh --report

# Output in JSON format (for CI/CD integration)
./scripts/detect-hardcoded-values.sh --json
```

### SSOT Violation Types

The script distinguishes between two types of violations:

1. **SSOT Violations** (High Priority): Values that have known SSOT config equivalents
   - These should ALWAYS use SSOT config imports
   - The script shows the exact SSOT config path to use

2. **Other Violations** (Medium Priority): Generic hardcoded values
   - These may need environment variables or constants files

### CI/CD Integration (Issue #642)

A GitHub Actions workflow automatically checks SSOT compliance on every PR:

```yaml
# .github/workflows/ssot-coverage.yml
# Runs on: push, pull_request
# Reports: Total violations, SSOT violations, compliance percentage
```

The workflow:

- Comments on PRs with SSOT compliance status
- Shows exact config replacements needed
- Tracks compliance over time

### SSOT Mappings Registry

The `src/config/ssot_mappings.py` module provides programmatic access to SSOT mappings:

```python
from src.config.ssot_mappings import get_mapping_for_value, get_ssot_suggestion

# Check if a value has an SSOT equivalent
mapping = get_mapping_for_value("<database-ip>")
if mapping:
    print(f"Use {mapping.python_config} instead")
    # Output: Use config.vm.redis instead

# Get language-specific suggestion
suggestion = get_ssot_suggestion("8001", "typescript")
# Output: Use config.port.backend from @/config/ssot-config
```

### Environment Analyzer Integration

The EnvironmentAnalyzer now includes SSOT mapping in its output:

```python
from tools.code-analysis-suite.src.env_analyzer import EnvironmentAnalyzer

analyzer = EnvironmentAnalyzer()
results = await analyzer.analyze_codebase(".")

# New in Issue #642: SSOT coverage report
if "ssot_coverage" in results:
    print(f"Compliance: {results['ssot_coverage']['ssot_compliance_pct']}%")
    print(f"Values with SSOT equivalents: {results['ssot_coverage']['with_ssot_equivalent']}")
```

Each hardcoded value now includes SSOT mapping info:

```json
{
  "file": "src/example.py",
  "line": 42,
  "value": "<database-ip>",
  "ssot_mapping": {
    "has_ssot_equivalent": true,
    "python_config": "config.vm.redis",
    "typescript_config": "config.vm.redis",
    "env_var": "AUTOBOT_REDIS_HOST",
    "status": "NOT_USING_SSOT"
  }
}
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

## config.yaml vs .env (SSOT)

**Issue #639** consolidated the configuration system. Here's the separation of concerns:

### config.yaml - User Preferences Only

The `config/config.yaml` file now contains **only user-configurable preferences**:

```yaml
# User preferences - configurable at runtime
ui:
  theme: light
  language: en
  font_size: medium

chat:
  auto_scroll: true
  max_messages: 100

logging:
  log_level: INFO
  log_to_file: true

voice_interface:
  enabled: false
  speech_rate: 1
```

### .env - Infrastructure Configuration (SSOT)

All infrastructure configuration (IPs, ports, hosts) is in `.env`:

```bash
# Infrastructure - managed by SSOT
AUTOBOT_BACKEND_HOST=<backend-ip>
AUTOBOT_REDIS_HOST=<database-ip>
AUTOBOT_OLLAMA_HOST=127.0.0.1
AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
```

### What Goes Where?

| Setting Type | Location | Example |
|-------------|----------|---------|
| VM IP addresses | `.env` | `AUTOBOT_REDIS_HOST` |
| Service ports | `.env` | `AUTOBOT_BACKEND_PORT` |
| LLM endpoints | `.env` | `AUTOBOT_OLLAMA_HOST` |
| Default models | `.env` | `AUTOBOT_DEFAULT_LLM_MODEL` |
| UI preferences | `config.yaml` | `ui.theme` |
| Chat settings | `config.yaml` | `chat.auto_scroll` |
| Log settings | `config.yaml` | `logging.log_level` |
| Feature flags | `config.yaml` | `developer.enabled` |
| Timeout values | `config.yaml` | `timeouts.redis.get` |

### Accessing Configuration

```python
# For infrastructure (network, ports, hosts) - use SSOT
from autobot_shared.ssot_config import config
redis_host = config.vm.redis           # Infrastructure from .env
backend_url = config.backend_url       # Computed URL from .env

# For user preferences - use unified config manager
from src.config import unified_config_manager
theme = unified_config_manager.get_nested('ui.theme')  # From config.yaml
auto_scroll = unified_config_manager.get_nested('chat.auto_scroll')
```

## Related Documentation

- [HARDCODING_PREVENTION.md](HARDCODING_PREVENTION.md) - Hardcoding policy
- [REDIS_CLIENT_USAGE.md](REDIS_CLIENT_USAGE.md) - Redis client patterns
- [SSOT_CONFIGURATION_ARCHITECTURE.md](../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md) - Full architecture spec
- [CONFIG_MIGRATION_CHECKLIST.md](CONFIG_MIGRATION_CHECKLIST.md) - Migration steps

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Issues**: #604 - SSOT Phase 4 Cleanup, #639 - SSOT Phase 5 config.yaml Consolidation, #642 - SSOT Config Validation & Enforcement
