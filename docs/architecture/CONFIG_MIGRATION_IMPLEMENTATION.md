# Config Migration Implementation Guide

**Issue**: #63 - Config Systems Consolidation
**Target**: Migrate unified_config.py → unified_config_manager.py
**Author**: mrveiss
**Status**: Ready for Implementation

## Quick Start Checklist

```bash
# 1. Create feature branch
git checkout -b fix/config-consolidation-63

# 2. Run baseline tests
python -m pytest tests/unit/test_timeout_configuration.py -v
python scripts/validate_timeout_config.py

# 3. Implement changes (see below)

# 4. Verify no regression
bash run_autobot.sh --dev
curl http://172.16.168.21:5173  # Frontend accessible?
```

## Implementation Steps

### Step 1: Add Missing Methods to unified_config_manager.py

Add these methods to the UnifiedConfigManager class:

```python
# Add after line 766 (after existing get_timeout method)

def get_timeout_for_env(
    self,
    category: str,
    timeout_type: str,
    environment: str = None,
    default: float = 60.0,
) -> float:
    """
    Get environment-aware timeout value.

    Port of unified_config.py functionality for Issue #63.
    Critical for knowledge_base_timeouts.py operations.

    Args:
        category: Category path (e.g., 'redis.operations')
        timeout_type: Specific timeout type (e.g., 'get')
        environment: Environment name ('development', 'production')
        default: Fallback value if not found

    Returns:
        Timeout value in seconds
    """
    if environment is None:
        environment = os.getenv("AUTOBOT_ENVIRONMENT", "production")

    # Try environment-specific override first
    env_path = f"environments.{environment}.timeouts.{category}.{timeout_type}"
    env_timeout = self.get_nested(env_path)
    if env_timeout is not None:
        return float(env_timeout)

    # Fall back to base configuration
    base_path = f"timeouts.{category}.{timeout_type}"
    base_timeout = self.get_nested(base_path, default)
    return float(base_timeout)

def get_timeout_group(
    self, category: str, environment: str = None
) -> Dict[str, float]:
    """
    Get all timeouts for a category as a dictionary.

    Port of unified_config.py functionality for Issue #63.
    Used by validation scripts and tests.

    Args:
        category: Category path (e.g., 'redis.operations')
        environment: Environment name (optional)

    Returns:
        Dictionary of timeout names to values
    """
    base_path = f"timeouts.{category}"
    base_config = self.get_nested(base_path, {})

    if not isinstance(base_config, dict):
        return {}

    # Apply environment overrides if specified
    if environment:
        env_path = f"environments.{environment}.timeouts.{category}"
        env_overrides = self.get_nested(env_path, {})
        if isinstance(env_overrides, dict):
            base_config = {**base_config, **env_overrides}

    # Convert all values to float
    result = {}
    for k, v in base_config.items():
        if isinstance(v, (int, float)):
            result[k] = float(v)

    return result

def validate_timeouts(self) -> Dict[str, Any]:
    """
    Validate all timeout configurations.

    Port of unified_config.py functionality for Issue #63.
    Used by validate_timeout_config.py script.

    Returns:
        Validation report with issues and warnings
    """
    issues = []
    warnings = []

    # Check required timeout categories
    required_categories = ["redis", "llamaindex", "documents", "http", "llm"]
    for category in required_categories:
        timeout_config = self.get_nested(f"timeouts.{category}")
        if timeout_config is None:
            issues.append(f"Missing timeout configuration for '{category}'")

    # Validate timeout ranges
    all_timeouts = self.get_nested("timeouts", {})

    def check_timeout_values(config, path=""):
        for key, value in config.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                check_timeout_values(value, current_path)
            elif isinstance(value, (int, float)):
                if value <= 0:
                    issues.append(
                        f"Invalid timeout '{current_path}': {value} (must be > 0)"
                    )
                elif value > 600:
                    warnings.append(
                        f"Very long timeout '{current_path}': {value}s (> 10 minutes)"
                    )

    check_timeout_values(all_timeouts)

    return {"valid": len(issues) == 0, "issues": issues, "warnings": warnings}

def get_cors_origins(self) -> list:
    """
    Generate CORS allowed origins from infrastructure configuration.

    Port of unified_config.py functionality for Issue #63.
    CRITICAL: Used by app_factory.py for frontend connectivity.

    Returns a list of allowed origins including:
    - Localhost variants for development
    - Frontend service (Vite dev server)
    - Browser service (Playwright)
    - Backend service (for WebSocket/CORS testing)
    """
    # Check if explicitly configured in security.cors_origins
    explicit_origins = self.get_nested("security.cors_origins", [])
    if explicit_origins:
        return explicit_origins

    # Otherwise, generate from infrastructure config
    frontend_host = self.get_host("frontend")
    frontend_port = self.get_port("frontend")
    browser_host = self.get_host("browser_service")
    browser_port = self.get_port("browser_service")
    backend_host = self.get_host("backend")
    backend_port = self.get_port("backend")

    origins = [
        # Localhost variants for development
        "http://localhost:5173",  # Vite dev server default
        "http://127.0.0.1:5173",
        "http://localhost:3000",  # Browser/other dev tools
        "http://127.0.0.1:3000",
        # Frontend service
        f"http://{frontend_host}:{frontend_port}",
        # Browser service (Playwright)
        f"http://{browser_host}:{browser_port}",
        # Backend service (for testing/debugging)
        f"http://{backend_host}:{backend_port}",
    ]

    # Remove duplicates while preserving order
    seen = set()
    unique_origins = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            unique_origins.append(origin)

    return unique_origins

def get_security_config(self) -> Dict[str, Any]:
    """
    Get security configuration.

    Port of unified_config.py functionality for Issue #63.

    Returns:
        Security configuration with session and encryption settings
    """
    return self.get_nested(
        "security",
        {"session": {"timeout_minutes": 30}, "encryption": {"enabled": False}},
    )

def is_feature_enabled(self, feature: str) -> bool:
    """
    Check if a feature is enabled.

    Port of unified_config.py functionality for Issue #63.

    Args:
        feature: Feature name to check

    Returns:
        True if feature is enabled, False otherwise
    """
    return self.get_nested(f"features.{feature}", False)
```

### Step 2: Create Compatibility Shim

Replace entire content of `/home/kali/Desktop/AutoBot/src/unified_config.py`:

```python
"""
Unified Configuration System - Compatibility Shim

This module provides backward compatibility during migration to unified_config_manager.
All functionality has been consolidated into unified_config_manager.py.

Issue #63: Config Systems Consolidation
This file will be removed after all imports are updated.
"""

import logging
from src.unified_config_manager import unified_config_manager

logger = logging.getLogger(__name__)
logger.info("unified_config.py compatibility shim loaded - please update imports to unified_config_manager")

# Create singleton instance for backward compatibility
config = unified_config_manager

# Re-export all methods for backward compatibility
get_host = unified_config_manager.get_host
get_port = unified_config_manager.get_port
get_service_url = unified_config_manager.get_service_url
get_timeout = unified_config_manager.get_timeout
get_redis_config = unified_config_manager.get_redis_config

# Export the ported methods
get_timeout_for_env = unified_config_manager.get_timeout_for_env
get_timeout_group = unified_config_manager.get_timeout_group
validate_timeouts = unified_config_manager.validate_timeouts
get_cors_origins = unified_config_manager.get_cors_origins
get_security_config = unified_config_manager.get_security_config
is_feature_enabled = unified_config_manager.is_feature_enabled

# Export commonly used values (backward compatibility)
BACKEND_HOST = unified_config_manager.get_host("backend")
BACKEND_PORT = unified_config_manager.get_port("backend")
FRONTEND_HOST = unified_config_manager.get_host("frontend")
FRONTEND_PORT = unified_config_manager.get_port("frontend")
REDIS_HOST = unified_config_manager.get_host("redis")
REDIS_PORT = unified_config_manager.get_port("redis")
OLLAMA_HOST = unified_config_manager.get_host("ollama")
OLLAMA_PORT = unified_config_manager.get_port("ollama")

# Service URLs
BACKEND_URL = unified_config_manager.get_service_url("backend")
FRONTEND_URL = unified_config_manager.get_service_url("frontend")
REDIS_URL = unified_config_manager.get_service_url("redis")
OLLAMA_URL = unified_config_manager.get_service_url("ollama")

# Timeouts
DEFAULT_TIMEOUT = unified_config_manager.get_timeout("http", "standard")
LLM_TIMEOUT = unified_config_manager.get_timeout("llm", "default")
REDIS_TIMEOUT = unified_config_manager.get_timeout("redis", "stats_collection")

logger.info(
    f"Unified config shim exports - Backend: {BACKEND_URL}, Redis: {REDIS_URL}, Ollama: {OLLAMA_URL}"
)
```

### Step 3: Update Critical Files First

Start with lowest risk files and test after each:

#### 3.1 Update validation script
```python
# In scripts/validate_timeout_config.py
# Change line 6:
from src.unified_config_manager import unified_config_manager as config
```

#### 3.2 Update test files
```python
# In tests/unit/test_timeout_configuration.py
# Change import:
from src.unified_config_manager import unified_config_manager as config
```

#### 3.3 Test critical path
```bash
# After updating validation and tests:
python scripts/validate_timeout_config.py
python -m pytest tests/unit/test_timeout_configuration.py -v

# If pass, continue to next files
```

### Step 4: Mass Migration Script

Create `/home/kali/Desktop/AutoBot/scripts/migrate_config_imports.py`:

```python
#!/usr/bin/env python3
"""
Migrate config imports from unified_config to unified_config_manager
Issue #63: Config Systems Consolidation
"""

import os
import re
from pathlib import Path

def migrate_file(file_path):
    """Update imports in a single file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Pattern replacements
    replacements = [
        (r'from src\.unified_config import config',
         'from src.unified_config_manager import unified_config_manager as config'),
        (r'from unified_config import config',
         'from src.unified_config_manager import unified_config_manager as config'),
        (r'import src\.unified_config',
         'import src.unified_config_manager'),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Files to migrate (in order of risk)
files_to_migrate = [
    "scripts/validate_timeout_config.py",
    "tests/unit/test_timeout_configuration.py",
    "autobot-user-backend/utils/knowledge_base_timeouts.py",
    "src/startup_validator.py",
    "src/conversation_file_manager.py",
    "autobot-user-backend/api/system.py",
    "autobot-user-backend/api/llm.py",
    "src/auth_middleware.py",
    "src/autobot_memory_graph.py",
    "src/knowledge_base_factory.py",
    "src/chat_history_manager.py",
    "src/chat_workflow_manager.py",
    "src/knowledge_base.py",
    "src/llm_interface.py",
    "backend/app_factory.py",  # CRITICAL - test thoroughly!
]

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent

    for file_path in files_to_migrate:
        full_path = project_root / file_path
        if full_path.exists():
            if migrate_file(full_path):
                print(f"✓ Migrated: {file_path}")
            else:
                print(f"- No changes: {file_path}")
        else:
            print(f"✗ Not found: {file_path}")
```

### Step 5: Testing Protocol

After each migration phase:

```bash
# 1. Basic functionality
python -c "from src.unified_config_manager import unified_config_manager; print(unified_config_manager.get_cors_origins())"

# 2. Timeout validation
python scripts/validate_timeout_config.py

# 3. Backend startup
curl http://localhost:8001/api/health

# 4. Frontend connectivity (CRITICAL!)
curl http://172.16.168.21:5173

# 5. Full system test
bash run_autobot.sh --dev
# Open browser to http://172.16.168.21:5173
# Test model selection in GUI
```

### Step 6: Cleanup

After all tests pass:

```bash
# 1. Remove old config files
git rm src/config.py
git rm src/config_consolidated.py

# 2. Archive unified_config.py (now just a shim)
mkdir -p archives/config/2025-01-16
mv src/unified_config.py archives/config/2025-01-16/

# 3. Update unified_config_manager.py to remove circular import
# Remove line 636: from src.unified_config import config
# Replace with direct implementation

# 4. Commit changes
git add -A
git commit -m "fix(config): Consolidate 5 config systems into unified_config_manager (#63)

- Ported 6 unique features from unified_config.py
- Migrated 20 files to use unified_config_manager
- Preserved ALL features per consolidation policy
- Removed 3 obsolete config files
- Added comprehensive test coverage

BREAKING CHANGE: unified_config.py removed, use unified_config_manager instead"
```

## Rollback Plan

If issues arise:

```bash
# Quick rollback
git stash
git checkout main
bash run_autobot.sh --restart

# Or revert compatibility shim
git checkout HEAD -- src/unified_config.py
```

## Verification Checklist

### Pre-Migration
- [ ] Backup config files
- [ ] Document current model selection
- [ ] Test frontend connectivity
- [ ] Run timeout validation

### Post-Migration
- [ ] All 6 features working
- [ ] Frontend loads (CORS working)
- [ ] Model selection in GUI works
- [ ] Knowledge base operations normal
- [ ] Redis timeouts correct
- [ ] All tests passing

### Final Cleanup
- [ ] Old files archived
- [ ] Documentation updated
- [ ] No circular imports
- [ ] Performance unchanged

## Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| Frontend won't load | Check get_cors_origins() implementation |
| Timeout errors | Verify get_timeout_for_env() logic |
| Model selection broken | Check get_selected_model() in unified_config_manager |
| Import errors | Run compatibility shim test |
| Redis connection fails | Verify get_redis_config() returns correct format |

## Contact for Issues

If critical issues arise during migration:
1. Check this guide first
2. Review CONFIG_CONSOLIDATION_ANALYSIS.md
3. Test with compatibility shim
4. Rollback if necessary

---

**End of Implementation Guide**
