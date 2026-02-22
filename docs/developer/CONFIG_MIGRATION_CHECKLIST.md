# Configuration Migration Checklist

> **Checklist for migrating code to SSOT Configuration Pattern**
>
> Part of Issue #604 - SSOT Phase 4 Cleanup

## Pre-Migration Checklist

Before migrating any code, verify:

- [ ] `.env` file exists in project root
- [ ] `.env.example` is updated with any new variables needed
- [ ] You understand the current configuration source (hardcoded, os.getenv, config file)
- [ ] You know the target SSOT loader for your language

## Python Migration Checklist

### Step 1: Identify Hardcoded Values

- [ ] Search for hardcoded IPs: `grep -rn "172\.16\.168\." src/ backend/`
- [ ] Search for hardcoded ports: `grep -rn ":[0-9]\{4,5\}" src/ backend/`
- [ ] Search for hardcoded model names: `grep -rn "llama\|mistral\|dolphin" src/ backend/`
- [ ] Search for direct os.getenv: `grep -rn "os\.getenv" src/ backend/`

### Step 2: Import SSOT Config

```python
from src.config.ssot_config import config
```

- [ ] Import added at top of file
- [ ] No circular import issues

### Step 3: Replace Hardcoded Values

| Pattern | Replace With |
|---------|--------------|
| `"172.16.168.20"` | `config.backend.host` |
| `"172.16.168.21"` | `config.frontend.host` |
| `"172.16.168.23"` | `config.redis.host` |
| `8001` (backend port) | `config.backend.port` |
| `6379` (redis port) | `config.redis.port` |
| `"llama3.2:3b"` | `config.llm.default_model` |

- [ ] All hardcoded IPs replaced
- [ ] All hardcoded ports replaced
- [ ] All hardcoded model names replaced

### Step 4: Replace os.getenv Calls

```python
# Before
os.getenv("REDIS_HOST", "localhost")

# After
config.redis.host
```

- [ ] All os.getenv calls for SSOT variables replaced
- [ ] Non-SSOT environment variables can remain as os.getenv

### Step 5: Verify

- [ ] Run `./scripts/detect-hardcoded-values.sh` - no violations
- [ ] Run tests: `python -m pytest tests/`
- [ ] Manual test of affected functionality

## TypeScript/Vue Migration Checklist

### Step 1: Identify Hardcoded Values

- [ ] Search for hardcoded IPs: `grep -rn "172\.16\.168\." autobot-user-frontend/src/`
- [ ] Search for hardcoded ports: `grep -rn ":[0-9]\{4,5\}" autobot-user-frontend/src/`
- [ ] Search for hardcoded URLs: `grep -rn "http://" autobot-user-frontend/src/`

### Step 2: Import SSOT Config

```typescript
import { getConfig, getBackendUrl } from '@/config/ssot-config'
```

- [ ] Import added at top of file
- [ ] No import path issues

### Step 3: Replace Hardcoded Values

| Pattern | Replace With |
|---------|--------------|
| `"https://172.16.168.20:8443"` | `getBackendUrl()` |
| `"172.16.168.20"` | `getConfig().backend.host` |
| `8001` | `getConfig().backend.port` |

- [ ] All hardcoded URLs replaced
- [ ] All hardcoded IPs replaced
- [ ] All hardcoded ports replaced

### Step 4: Verify

- [ ] Run `./scripts/detect-hardcoded-values.sh` - no violations
- [ ] Run type check: `npm run type-check`
- [ ] Run linting: `npm run lint`
- [ ] Manual test in browser

## Shell Script Migration Checklist

### Step 1: Add SSOT Loading Block

Add this block at the start of the script (after `set -e`):

```bash
# =============================================================================
# SSOT Configuration - Load from .env file (Single Source of Truth)
# Issue: #604 - SSOT Phase 4 Cleanup
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
```

- [ ] SSOT loading block added
- [ ] `PROJECT_ROOT` path is correct for script location
- [ ] Comment references Issue #604

### Step 2: Replace Hardcoded Values

| Pattern | Replace With |
|---------|--------------|
| `172.16.168.20` | `${AUTOBOT_BACKEND_HOST:-172.16.168.20}` |
| `172.16.168.21` | `${AUTOBOT_FRONTEND_HOST:-172.16.168.21}` |
| `172.16.168.22` | `${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}` |
| `172.16.168.23` | `${AUTOBOT_REDIS_HOST:-172.16.168.23}` |
| `172.16.168.24` | `${AUTOBOT_AI_STACK_HOST:-172.16.168.24}` |
| `172.16.168.25` | `${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}` |
| `8001` (backend) | `${AUTOBOT_BACKEND_PORT:-8001}` |
| `5173` (frontend) | `${AUTOBOT_FRONTEND_PORT:-5173}` |
| `6379` (redis) | `${AUTOBOT_REDIS_PORT:-6379}` |

- [ ] All hardcoded IPs replaced with env vars + fallbacks
- [ ] All hardcoded ports replaced with env vars + fallbacks
- [ ] Fallback values match the original hardcoded values

### Step 3: Verify

- [ ] Run `./scripts/detect-hardcoded-values.sh` - no violations
- [ ] Test script execution: `bash -n script.sh` (syntax check)
- [ ] Manual test of script functionality

## Post-Migration Checklist

After completing migration:

- [ ] All files saved and committed
- [ ] No hardcoding violations: `./scripts/detect-hardcoded-values.sh`
- [ ] All tests pass
- [ ] Documentation updated if needed
- [ ] PR includes reference to Issue #604

## Related Documentation

- [SSOT_CONFIG_GUIDE.md](SSOT_CONFIG_GUIDE.md) - Full developer guide
- [HARDCODING_PREVENTION.md](HARDCODING_PREVENTION.md) - Hardcoding policy

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Issue**: #604 - SSOT Phase 4 Cleanup
