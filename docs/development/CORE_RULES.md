# Core Project Rules & Standards

## 🔴 ZERO TOLERANCE RULES
1. **NO error left unfixed, NO warning left unfixed** - ZERO TOLERANCE for any linting or compilation errors
2. **NEVER abandon started tasks** - ALWAYS continue working until completion
3. **Group tasks by priority** - errors/warnings ALWAYS take precedence over features
4. **ALWAYS test before committing** - NO EXCEPTIONS
5. **NEVER restart applications** - Application restarts are handled by USER ONLY

## 🏗️ Application Lifecycle Management
- **SETUP**: Application is configured ONCE using `./setup_agent.sh`
- **EXECUTION**: Application runs ONLY via `./run_agent.sh [options]`
- **RESTARTS**: Handled EXCLUSIVELY by user - NEVER restart programmatically
- **CONFIGURATION**: All setup and configuration changes go through `setup_agent.sh`
- **OPTIONS**: Use `./run_agent.sh --help` to see available runtime options

## 🔐 CRITICAL: USER RESTART REQUIRED
**When AutoBot needs restart, ALWAYS ask user to manually restart:**
- `./run_agent.sh` requires sudo password entry for Docker operations
- Claude Code CANNOT automate password entry for security reasons
- **ACTION**: Request user to run `./run_agent.sh` in their terminal
- **REASON**: Docker container management, volume mounting, network setup require elevated privileges

## 🔴 CRITICAL: STARTUP/SETUP SCRIPT MAINTENANCE
**ALL IMPLEMENTED CHANGES MUST BE REFLECTED IN STARTUP AND SETUP SCRIPTS**

- `run_agent.sh` and `setup_agent.sh` MUST ALWAYS be up to date
- **ZERO TOLERANCE** for missing changes in these scripts
- New features, dependencies, Docker configurations, Redis settings MUST be included
- Any architectural changes MUST be represented in script options and configurations
- Scripts are the SINGLE SOURCE OF TRUTH for application deployment

## 🚫 CRITICAL: AVOID HARDCODED VALUES AT ALL COST

### ❌ What NOT to do:
```python
# ❌ Hardcoded port
server_port = 8001

# ❌ Hardcoded URL
api_url = "http://localhost:8001/api"

# ❌ Hardcoded file path
log_file = "/var/log/autobot.log"

# ❌ Hardcoded database connection
db_url = "redis://localhost:6379"

# ❌ Hardcoded API keys or secrets
# api_key = "literal-secret-here"  # This exposes secrets in source code! # pragma: allowlist secret
```

### ✅ What TO do:
```python
# ✅ Use environment variables
import os
server_port = int(os.getenv("AUTOBOT_SERVER_PORT", "8001"))

# ✅ Use configuration system
from src.config import config
api_url = config.get_nested("backend.api_endpoint")

# ✅ Use relative paths or config
log_file = config.get_nested("logging.log_file_path", "data/logs/autobot.log")

# ✅ Use environment variables
redis_url = os.getenv("AUTOBOT_REDIS_URL", "redis://localhost:6379")

# ✅ Use secure configuration
api_key = config.get_secret("EXTERNAL_API_KEY")  # From secrets manager # pragma: allowlist secret
```

### Configuration Best Practices:
```python
# ✅ Ports - always configurable
BACKEND_PORT = int(os.getenv("AUTOBOT_BACKEND_PORT", "8001"))

# ✅ URLs - read the SSOT, never rebuild them (autobot_shared.ssot_config.config)
API_BASE_URL = ssot_config.backend_url

# ✅ File paths - relative to project or configurable
DATA_DIR = os.getenv("AUTOBOT_DATA_DIR", "data")

# ✅ Feature flags - environment controlled
ENABLE_FEATURE_X = os.getenv("AUTOBOT_ENABLE_FEATURE_X", "false").lower() == "true"
```

**Why avoid hardcoded values:**
- **Deployment flexibility**: Different environments need different values
- **Security**: Prevents secrets from being committed to source control
- **Maintainability**: Central configuration is easier to manage
- **Scalability**: Easy to adjust for different deployment scenarios
- **Testing**: Enables different values for test vs production environments

## ⚙️ Configuration & Dependencies
- **NEVER hardcode values** - use `src/config.py` for all configuration
- **Update docstrings** following Google style for any function changes
- **Dependencies must reflect in**:
  - Install scripts
  - requirements.txt
  - **SECURITY UPDATES MANDATORY**

## 💾 Data Safety
- **CRITICAL**: Backup `data/` before schema changes to:
  - knowledge_base.db
  - memory_system.db

## Priority Hierarchy
1. **🔴 Critical Errors** (blocking functionality)
2. **🟡 API Duplications** (technical debt, maintenance burden)
3. **🟡 Warnings** (potential issues)
4. **🔵 Security Updates** (mandatory)
5. **🟢 Features** (new functionality)
6. **⚪ Refactoring** (code improvement)
