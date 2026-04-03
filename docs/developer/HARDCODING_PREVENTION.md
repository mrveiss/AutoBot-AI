# Hardcoding Prevention Guide

**Status**: Automated enforcement via pre-commit hooks

This guide provides detailed implementation instructions for the **NO HARDCODED VALUES** policy.

> **MANDATORY RULE**: NO HARDCODED VALUES - USE SSOT CONFIG

---

## What Constitutes Hardcoding

The following values must NEVER be hardcoded in source files:

| Type | Examples | Correct Alternative |
|------|----------|---------------------|
| **IP Addresses** | `"172.16.168.20"`, `"192.168.1.100"` | `config.backend.host` (Python) or SSOT env vars |
| **Port Numbers** | `8001`, `6379`, `5173` | `config.backend.port` (Python) or SSOT env vars |
| **LLM Model Names** | `"qwen3.5:9b"`, `"mistral:7b-instruct"` | `config.llm.default_model` or `AUTOBOT_DEFAULT_LLM_MODEL` |
| **URLs** | `"http://example.com/api"` | `getBackendUrl()` (TypeScript) or SSOT config |
| **API Keys/Secrets** | `"sk-abc123..."`, `"password123"` | Environment variables (NEVER commit) |

> See also: [SSOT_CONFIG_GUIDE.md](SSOT_CONFIG_GUIDE.md) for complete configuration patterns

---

## Automated Detection

### Pre-Commit Hook

The pre-commit hook automatically scans staged files before every commit:

```bash
# Runs automatically on git commit
# Located at: .git/hooks/pre-commit-hardcode-check
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh
```

**What it checks**:

- IP address patterns (IPv4/IPv6)
- Port numbers (common service ports)
- LLM model names (Ollama/OpenAI patterns)
- Hardcoded URLs
- Potential secrets (API keys, tokens)

**When violations are found**:

- Commit is blocked
- Violation report is displayed
- You must fix violations before committing

### Manual Scan

Run the detection script manually to audit the entire codebase:

```bash
# Scan entire codebase for violations
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh

# Get detailed report with line numbers
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh | less

# Scan specific file or directory
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh autobot-user-autobot-backend/api/chat.py
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh autobot-backend/
```

**Script location**: `autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh`

---

## ConfigRegistry Fallback Pattern (Issue #2671)

`registry_defaults.py` now sources all default values from `autobot_shared.ssot_config` at import time. This means `ConfigRegistry.get()` callers **no longer need hardcoded fallbacks** -- the registry defaults tier provides SSOT-sourced values automatically.

```python
# GOOD -- no hardcoded fallback needed
redis_host = ConfigRegistry.get("vm.redis")
npu_port = ConfigRegistry.get("port.npu")

# BAD -- redundant hardcoded fallback (will trigger detection script)
redis_host = ConfigRegistry.get("vm.redis", "172.16.168.23")
```

For model names and embedding models, use the SSOT constants:

```python
from autobot_shared.ssot_config import DEFAULT_LLM_MODEL, DEFAULT_EMBEDDING_MODEL

# GOOD
model = DEFAULT_LLM_MODEL
embedding = DEFAULT_EMBEDDING_MODEL

# BAD
model = "qwen3.5:9b"
embedding = "nomic-embed-text:latest"
```

---

## How to Fix Violations

### 1. For IP Addresses and Port Numbers

**Use the SSOT config (Python)**:

```python
# BAD - Hardcoded values
url = "https://172.16.168.20:8443/api/chat"
redis_host = "172.16.168.23"
redis_port = 6379

# GOOD - Use SSOT config
from autobot_shared.ssot_config import config

url = config.backend.url + "/api/chat"
redis_host = config.redis.host
redis_port = config.redis.port
```

**Use the SSOT config (TypeScript)**:

```typescript
// BAD - Hardcoded values
const url = "https://172.16.168.20:8443/api/chat"

// GOOD - Use SSOT config
import { getBackendUrl } from '@/config/ssot-config'

const url = getBackendUrl() + "/api/chat"
```

**Use SSOT in Shell Scripts**:

```bash
# Load .env at script start
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# BAD - Hardcoded
BACKEND_HOST="172.16.168.20"

# GOOD - SSOT env var with fallback
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
```

### 2. For LLM Model Names

**Use SSOT config**:

```python
# BAD - Hardcoded model name
model = "qwen3.5:9b"

# GOOD - Use SSOT config
from autobot_shared.ssot_config import config
model = config.llm.default_model
```

**Environment variable**: Set in `.env` file:

```bash
AUTOBOT_DEFAULT_LLM_MODEL=qwen3.5:9b
```

### 3. For Other Values (URLs, API Keys, etc.)

**Use environment variables via SSOT**:

**Step 1**: Add to `.env` file (never commit this file):

```bash
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=sk-abc123...
AUTOBOT_CUSTOM_SETTING=value
```

**Step 2**: Read via SSOT config or env vars:

```python
# BAD - Hardcoded URL
api_url = "http://api.example.com"

# GOOD - Use SSOT config for standard values
from autobot_shared.ssot_config import config
backend_url = config.backend.url

# GOOD - Use os.getenv for custom values
import os
api_key = os.getenv("AUTOBOT_API_KEY")  # NEVER hardcode secrets!
```

**Step 3**: Document in `.env.example`:

```bash
# API Configuration
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=your-api-key-here
```

---

## Override (Emergency Only)

**When hardcoding is ABSOLUTELY necessary** (extremely rare cases):

### Prerequisites

1. **Document WHY** in code comments
2. **Add entry** to `.hardcode-exceptions` file
3. **Get approval** in code review

### Exception File Format

Create/edit `.hardcode-exceptions` in repository root:

```text
# Hardcoding Exceptions
# Format: file_path:line_number:reason

autobot-backend/utils/legacy_module.py:45:Legacy API requires hardcoded endpoint
infrastructure/shared/tests/integration/test_fixtures.py:120:Test fixture needs static IP
```

### Bypass Pre-Commit Hook

**NOT RECOMMENDED** - Only use if you've added exception:

```bash
# Bypass pre-commit hook (use with extreme caution)
git commit --no-verify -m "Your message"
```

**Warning**: This bypasses ALL pre-commit checks, not just hardcoding detection.

---

## Detection Script Details

### Script Location

```text
autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh
```

### What It Detects

**IP Address Patterns**:

- IPv4: `172.16.168.20`, `192.168.1.1`, etc.
- IPv6: Full and compressed formats
- Excludes: Comments, documentation, test files

**Port Numbers**:

- Common service ports: 8001, 6379, 5173, etc.
- Excludes: Commented code, examples

**LLM Model Names**:

- Ollama models: `qwen3.5:9b`, `mistral:7b-instruct`, `gemma2:2b`, `llama3.2:1b`
- OpenAI models: `gpt-4`, `gpt-3.5-turbo`
- Anthropic models: `claude-3-opus`

**URLs and Secrets**:

- HTTP/HTTPS URLs
- Potential API keys (pattern matching)
- Tokens and credentials

### Exclusions

The script automatically excludes:

- `.env` files (intended for configuration)
- `.env.example` files (documentation)
- `network_constants.py` (canonical source of truth)
- Documentation files (`.md`)
- Test fixtures (when marked as such)
- Comments and docstrings

---

## Pre-Commit Hook Setup

### Installation

The hook is automatically installed via:

```bash
bash infrastructure/shared/scripts/install-pre-commit-hooks.sh
```

### Manual Installation

If needed, install manually:

```bash
# Make script executable
chmod +x autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh

# Create pre-commit hook
cat > .git/hooks/pre-commit-hardcode-check << 'EOF'
#!/bin/bash
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh --staged
if [ $? -ne 0 ]; then
    echo "Hardcoded values detected. Fix violations before committing."
    exit 1
fi
EOF

chmod +x .git/hooks/pre-commit-hardcode-check
```

### Hook Location

```text
.git/hooks/pre-commit-hardcode-check
```

---

## Best Practices

### 1. Check Before You Code

- Know the proper pattern before writing code
- Use SSOT `config` for IPs/ports/URLs
- Use `config.llm.default_model` for models
- Use `.env` for custom values

### 2. Run Manual Scans

```bash
# Before starting work
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh

# After making changes
./autobot-autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh autobot-user-autobot-backend/api/
```

### 3. Keep .env.example Updated

When adding new environment variables:

```bash
# Add to .env (local only)
AUTOBOT_NEW_FEATURE=value

# Document in .env.example (committed)
AUTOBOT_NEW_FEATURE=example-value
```

### 4. Review Before Committing

- Pre-commit hook runs automatically
- Fix violations immediately
- Don't use `--no-verify` unless absolutely necessary

---

## Troubleshooting

### False Positives

**Issue**: Script flags legitimate code

**Solution 1**: Add comment to clarify

```python
# This is a test fixture, not production code
test_ip = "127.0.0.1"  # Test only
```

**Solution 2**: Add to `.hardcode-exceptions`

```text
infrastructure/shared/tests/fixtures/network_mock.py:45:Test fixture requires static IP
```

### Pre-Commit Hook Not Running

**Issue**: Hook doesn't run on `git commit`

**Solution**:

```bash
# Reinstall hooks
bash infrastructure/shared/scripts/install-pre-commit-hooks.sh

# Verify hook exists and is executable
ls -la .git/hooks/pre-commit-hardcode-check
chmod +x .git/hooks/pre-commit-hardcode-check
```

### Need to Commit Urgently

**Issue**: Need to commit despite violations (emergency)

**Solution**:

1. Document the violation in code comments
2. Create GitHub issue to fix it
3. Add to `.hardcode-exceptions`
4. Use `--no-verify` (last resort)

```bash
# Emergency commit (not recommended)
git commit --no-verify -m "Emergency fix - see issue #123"
```

---

## Related Documentation

- **SSOT Config Guide**: [SSOT_CONFIG_GUIDE.md](SSOT_CONFIG_GUIDE.md) - Complete SSOT configuration patterns
- **Migration Checklist**: [CONFIG_MIGRATION_CHECKLIST.md](CONFIG_MIGRATION_CHECKLIST.md) - Migrating code to SSOT
- **SSOT Architecture**: [../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md](../architecture/SSOT_CONFIGURATION_ARCHITECTURE.md)
- **Python SSOT Config**: `autobot_shared/ssot_config.py`
- **TypeScript SSOT Config**: `autobot-frontend/src/config/ssot-config.ts`
- **Environment Setup**: [DEVELOPER_SETUP.md](DEVELOPER_SETUP.md)
- **Code Quality**: [CODE_QUALITY_ENFORCEMENT.md](CODE_QUALITY_ENFORCEMENT.md)

---

## Summary Checklist

**Before committing**:

- [ ] No hardcoded IP addresses (use SSOT `config.*.host`)
- [ ] No hardcoded port numbers (use SSOT `config.*.port`)
- [ ] No hardcoded model names (use `config.llm.default_model`)
- [ ] No hardcoded URLs (use `getBackendUrl()` or SSOT config)
- [ ] No hardcoded secrets (use environment variables)
- [ ] Pre-commit hook passes
- [ ] `.env.example` updated (if new variables added)

**If you must hardcode** (rare):

- [ ] Documented WHY in code comments
- [ ] Added to `.hardcode-exceptions` file
- [ ] Got approval in code review
- [ ] Created issue to remove hardcoding later

---
