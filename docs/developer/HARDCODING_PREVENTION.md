# Hardcoding Prevention Guide

**Status**: ✅ Automated enforcement via pre-commit hooks

This guide provides detailed implementation instructions for the **NO HARDCODED VALUES** policy.

> **⚠️ MANDATORY RULE**: NO HARDCODED VALUES in AutoBot codebase

---

## 📋 What Constitutes Hardcoding

The following values must NEVER be hardcoded in source files:

| Type | Examples | Correct Alternative |
|------|----------|---------------------|
| **IP Addresses** | `"172.16.168.20"`, `"192.168.1.100"` | `NetworkConstants.MAIN_MACHINE_IP` or `.env` |
| **Port Numbers** | `8001`, `6379`, `5173` | `NetworkConstants.BACKEND_PORT` or `.env` |
| **LLM Model Names** | `"llama3.2:1b-instruct-q4_K_M"` | `config.get_default_llm_model()` or `AUTOBOT_DEFAULT_LLM_MODEL` |
| **URLs** | `"http://example.com/api"` | Environment variables |
| **API Keys/Secrets** | `"sk-abc123..."`, `"password123"` | Environment variables (NEVER commit) |

---

## 🔍 Automated Detection

### Pre-Commit Hook

The pre-commit hook automatically scans staged files before every commit:

```bash
# Runs automatically on git commit
# Located at: .git/hooks/pre-commit-hardcode-check
./scripts/detect-hardcoded-values.sh
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
./scripts/detect-hardcoded-values.sh

# Get detailed report with line numbers
./scripts/detect-hardcoded-values.sh | less

# Scan specific file or directory
./scripts/detect-hardcoded-values.sh backend/api/chat.py
./scripts/detect-hardcoded-values.sh src/
```

**Script location**: `scripts/detect-hardcoded-values.sh`

---

## 🔧 How to Fix Violations

### 1. For IP Addresses and Port Numbers

**Use the `NetworkConstants` class**:

```python
# ❌ BAD - Hardcoded values
url = "http://172.16.168.20:8001/api/chat"
redis_host = "172.16.168.23"
redis_port = 6379

# ✅ GOOD - Use NetworkConstants
from src.constants.network_constants import NetworkConstants

url = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}/api/chat"
redis_host = NetworkConstants.REDIS_VM_IP
redis_port = NetworkConstants.REDIS_PORT
```

**Available constants** (see `src/constants/network_constants.py`):
```python
class NetworkConstants:
    MAIN_MACHINE_IP = "172.16.168.20"
    FRONTEND_VM_IP = "172.16.168.21"
    NPU_WORKER_VM_IP = "172.16.168.22"
    REDIS_VM_IP = "172.16.168.23"
    AI_STACK_VM_IP = "172.16.168.24"
    BROWSER_VM_IP = "172.16.168.25"

    BACKEND_PORT = 8001
    FRONTEND_PORT = 5173
    REDIS_PORT = 6379
    # ... and more
```

### 2. For LLM Model Names

**Use config methods**:

```python
# ❌ BAD - Hardcoded model name
model = "llama3.2:1b-instruct-q4_K_M"

# ✅ GOOD - Use config method
from src.config import config
model = config.get_default_llm_model()

# ✅ ALTERNATIVE - Use environment variable
import os
model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:1b")
```

**Environment variable**: Set in `.env` file:
```bash
AUTOBOT_DEFAULT_LLM_MODEL=llama3.2:1b-instruct-q4_K_M
```

### 3. For Other Values (URLs, API Keys, etc.)

**Use environment variables**:

**Step 1**: Add to `.env` file (never commit this file):
```bash
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=sk-abc123...
AUTOBOT_CUSTOM_SETTING=value
```

**Step 2**: Read in code:
```python
# ❌ BAD - Hardcoded URL
api_url = "http://api.example.com"
api_key = "sk-abc123..."

# ✅ GOOD - Use environment variables
import os

api_url = os.getenv("AUTOBOT_API_BASE_URL")
api_key = os.getenv("AUTOBOT_API_KEY")  # NEVER hardcode secrets!

# Provide defaults for non-sensitive values
custom_setting = os.getenv("AUTOBOT_CUSTOM_SETTING", "default_value")
```

**Step 3**: Document in `.env.example`:
```bash
# API Configuration
AUTOBOT_API_BASE_URL=http://api.example.com
AUTOBOT_API_KEY=your-api-key-here
```

---

## 🚨 Override (Emergency Only)

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

src/utils/legacy_module.py:45:Legacy API requires hardcoded endpoint
tests/integration/test_fixtures.py:120:Test fixture needs static IP
```

### Bypass Pre-Commit Hook

**NOT RECOMMENDED** - Only use if you've added exception:

```bash
# Bypass pre-commit hook (use with extreme caution)
git commit --no-verify -m "Your message"
```

**Warning**: This bypasses ALL pre-commit checks, not just hardcoding detection.

---

## 🔍 Detection Script Details

### Script Location
```
scripts/detect-hardcoded-values.sh
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
- Ollama models: `llama3.2:1b-instruct-q4_K_M`
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

## 📊 Pre-Commit Hook Setup

### Installation

The hook is automatically installed via:
```bash
bash scripts/install-pre-commit-hooks.sh
```

### Manual Installation

If needed, install manually:
```bash
# Make script executable
chmod +x scripts/detect-hardcoded-values.sh

# Create pre-commit hook
cat > .git/hooks/pre-commit-hardcode-check << 'EOF'
#!/bin/bash
./scripts/detect-hardcoded-values.sh --staged
if [ $? -ne 0 ]; then
    echo "❌ Hardcoded values detected. Fix violations before committing."
    exit 1
fi
EOF

chmod +x .git/hooks/pre-commit-hardcode-check
```

### Hook Location
```
.git/hooks/pre-commit-hardcode-check
```

---

## ✅ Best Practices

### 1. Check Before You Code
- Know the proper pattern before writing code
- Use `NetworkConstants` for IPs/ports
- Use `config` methods for models
- Use `.env` for everything else

### 2. Run Manual Scans
```bash
# Before starting work
./scripts/detect-hardcoded-values.sh

# After making changes
./scripts/detect-hardcoded-values.sh backend/api/
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

## 🐛 Troubleshooting

### False Positives

**Issue**: Script flags legitimate code

**Solution 1**: Add comment to clarify
```python
# This is a test fixture, not production code
test_ip = "127.0.0.1"  # Test only
```

**Solution 2**: Add to `.hardcode-exceptions`
```text
tests/fixtures/network_mock.py:45:Test fixture requires static IP
```

### Pre-Commit Hook Not Running

**Issue**: Hook doesn't run on `git commit`

**Solution**:
```bash
# Reinstall hooks
bash scripts/install-pre-commit-hooks.sh

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

## 📚 Related Documentation

- **Network Constants**: `src/constants/network_constants.py`
- **Config Module**: `src/config.py`
- **Environment Setup**: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- **Code Quality**: `docs/developer/CODE_QUALITY_ENFORCEMENT.md`

---

## 🎯 Summary Checklist

**Before committing**:
- [ ] No hardcoded IP addresses (use `NetworkConstants`)
- [ ] No hardcoded port numbers (use `NetworkConstants` or `.env`)
- [ ] No hardcoded model names (use `config.get_default_llm_model()`)
- [ ] No hardcoded URLs (use environment variables)
- [ ] No hardcoded secrets (use environment variables)
- [ ] Pre-commit hook passes
- [ ] `.env.example` updated (if new variables added)

**If you must hardcode** (rare):
- [ ] Documented WHY in code comments
- [ ] Added to `.hardcode-exceptions` file
- [ ] Got approval in code review
- [ ] Created issue to remove hardcoding later

---
