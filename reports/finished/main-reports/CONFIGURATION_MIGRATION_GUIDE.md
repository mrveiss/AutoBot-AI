# Configuration Migration Guide

**Project**: Centralized Configuration Migration  
**Status**: ✅ **MIGRATION GUIDE COMPLETED**  
**Date**: 2025-09-11  
**Scope**: Complete hardcoded value elimination across 150+ files

## Executive Summary

This comprehensive migration guide provides step-by-step instructions for eliminating ALL hardcoded values from the AutoBot codebase and implementing centralized configuration management. The guide covers migration patterns, implementation strategies, and validation procedures for achieving complete configuration compliance.

### Migration Objectives
- **Complete hardcode elimination**: Zero hardcoded values in production code
- **Centralized configuration**: Single source of truth for all settings
- **Environment flexibility**: Seamless deployment across multiple environments
- **Maintainability improvement**: Simplified configuration management
- **Production readiness**: Enterprise-grade configuration architecture

## Migration Overview

This guide demonstrates how to eliminate ALL hardcoded values from the codebase and implement centralized configuration management using the unified configuration system.

## New Configuration System

### Files Created
1. `/config/complete.yaml` - Complete configuration with ALL values
2. `/src/config_helper.py` - Helper module for easy config access
3. `/config/main.yaml` - Main orchestrator (for future)
4. `HARDCODED_VALUES_AUDIT.md` - Complete audit of hardcoded values

### Core Principle
**NO HARDCODED VALUES IN CODE** - Everything must come from configuration

## Migration Pattern

### Before (Hardcoded)
```python
# BAD - Hardcoded values
redis_client = redis.Redis(
    host="127.0.0.1",
    port=6379,
    password=None,
    timeout=5
)

url = "http://172.16.168.20:8001/api/health"
timeout = 60
```

### After (Configuration-based)
```python
# GOOD - All values from config
from src.config_helper import cfg

redis_client = redis.Redis(
    host=cfg.get('redis.host'),
    port=cfg.get('redis.port'),
    password=cfg.get('redis.password'),
    timeout=cfg.get('redis.connection.timeout')
)

url = cfg.get_service_url('backend', '/api/health')
timeout = cfg.get_timeout('http', 'standard')
```

## Common Patterns

### 1. Service URLs
```python
# Before
url = "http://172.16.168.20:8001/api/knowledge_base/stats"

# After
url = cfg.get_service_url('backend', '/api/knowledge_base/stats')
# OR
url = cfg.get('services.backend.knowledge_stats_url')
```

### 2. Timeouts
```python
# Before
timeout = 60
connection_timeout = 5

# After
timeout = cfg.get_timeout('llm', 'default')
connection_timeout = cfg.get_timeout('http', 'quick')
```

### 3. File Paths
```python
# Before
log_file = "logs/system.log"
data_dir = "data/chats"

# After
log_file = cfg.get_path('logs', 'system')
data_dir = cfg.get_path('data', 'chats')
```

### 4. Redis Configuration
```python
# Before
redis.Redis(host="127.0.0.1", port=6379, db=0, password=None)

# After
redis.Redis(**cfg.get_redis_config())
# OR for specific database
config = cfg.get_redis_config()
config['db'] = 1
redis.Redis(**config)
```

### 5. Host/Port Combinations
```python
# Before
host = "172.16.168.20"
port = 8001

# After
host = cfg.get_host('backend')
port = cfg.get_port('backend')
# OR combined
url = cfg.get_service_url('backend')
```

## Files to Update (Priority Order)

### High Priority (Core Infrastructure)
1. `/backend/api/cache.py` - ✅ DONE (example)
2. `/src/knowledge_base.py` - Redis connections
3. `/backend/api/infrastructure_monitor.py` - All hardcoded IPs
4. `/src/config.py` - Default value logic
5. `/src/utils/async_redis_manager.py` - Redis defaults

### Medium Priority (Service Integrations)
1. `/src/llm_interface_unified.py` - Timeouts and URLs
2. `/src/llm_interface_fixed.py` - Ollama URLs
3. `/backend/api/playwright.py` - Frontend URL
4. `/backend/api/service_monitor.py` - Service URLs
5. `/src/utils/service_registry.py` - All service mappings

### Low Priority (Individual Components)
1. `/src/intelligence/` - Various timeout values
2. `/backend/api/rum.py` - Log file paths
3. `/src/chat_workflow_manager_fixed.py` - Config file path

## Step-by-Step Migration Process

### Step 1: Add Config Import
```python
from src.config_helper import cfg
```

### Step 2: Replace Hardcoded Values
Find all hardcoded values in the file and replace with `cfg.get()` calls

### Step 3: Test Each File
After updating each file, test that service still works

### Step 4: Remove Old Config References
Remove old config loading code once centralized config is working

## Testing Checklist

For each migrated file, verify:
- [ ] Service starts without errors
- [ ] All connections work (Redis, HTTP, etc.)
- [ ] No hardcoded values remain
- [ ] Error handling still works
- [ ] Performance is not degraded

## Configuration Helper Usage

### Basic Access
```python
# Simple value access
value = cfg.get('infrastructure.hosts.backend')
value = cfg.get('timeouts.llm.default', 60)  # With default
```

### Service URLs
```python
# Get complete service URLs
backend_url = cfg.get_service_url('backend')
health_url = cfg.get_service_url('backend', '/api/health')
```

### Specialized Getters
```python
# Redis configuration
redis_config = cfg.get_redis_config()

# Timeouts
timeout = cfg.get_timeout('llm', 'chat')

# File paths
log_path = cfg.get_path('logs', 'system')

# Feature flags
if cfg.is_feature_enabled('debug_mode'):
    # Debug code
```

### Retry Configuration
```python
# Get retry settings
retry_config = cfg.get_retry_config('redis')
for attempt in range(retry_config['attempts']):
    # Retry logic
```

## Environment Overrides

Configuration can be overridden by environment variables:
```bash
# Override Redis host
export AUTOBOT_REDIS_HOST=192.168.1.100

# Override timeout
export AUTOBOT_LLM_TIMEOUT=120
```

## Benefits After Migration

1. **Single Source of Truth** - All values in one place
2. **Environment Flexibility** - Easy dev/test/prod configs  
3. **No Magic Numbers** - All values are documented
4. **Easy Updates** - Change once, applies everywhere
5. **Validation** - Config can be validated on startup
6. **Testing** - Easy to override values for tests

## Rollback Plan

If issues occur:
1. Keep old config files as backups
2. Can temporarily revert individual files
3. Old ConfigManager still works alongside new system
4. Feature flag `use_unified_config` can disable new system

## Next Steps

1. Complete migration of high-priority files
2. Add configuration validation
3. Create environment-specific overrides
4. Remove old configuration files
5. Add configuration documentation

## Example: Complete File Migration

See `/backend/api/cache.py` for example of completely migrated file:
- Imports `cfg` helper
- All Redis connection parameters from config
- No hardcoded values
- Uses centralized timeout/retry settings