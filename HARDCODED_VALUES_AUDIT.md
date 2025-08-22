# AutoBot Hardcoded Values Audit Report

## Executive Summary
This comprehensive audit identifies all hardcoded values in the AutoBot codebase that should be converted to environment variables or configuration settings. Values are categorized by type and priority for refactoring.

## Critical Priority (Must Fix Immediately)

### 1. API Endpoints & URLs

#### Backend API
- **File**: `src/config.py:797`
  - **Value**: `"http://localhost:8001"`
  - **Variable**: `AUTOBOT_BACKEND_API_ENDPOINT`
  - **Reason**: Backend API location varies by deployment
  - **Priority**: CRITICAL

#### Frontend URLs
- **File**: `src/config.py:800-801`
  - **Values**: `"http://localhost:5173"`, `"http://127.0.0.1:5173"`
  - **Variable**: `AUTOBOT_FRONTEND_URLS`
  - **Reason**: CORS allowed origins need environment-specific config
  - **Priority**: CRITICAL

#### External API Endpoints
- **File**: `src/modern_ai_integration.py:634`
  - **Value**: `"https://api.openai.com/v1/chat/completions"`
  - **Variable**: `OPENAI_API_ENDPOINT`
  - **Priority**: CRITICAL

- **File**: `src/modern_ai_integration.py:654`
  - **Value**: `"https://api.anthropic.com/v1/messages"`
  - **Variable**: `ANTHROPIC_API_ENDPOINT`
  - **Priority**: CRITICAL

- **File**: `backend/api/llm.py:324`
  - **Value**: `"http://localhost:1234/v1"`
  - **Variable**: `LM_STUDIO_ENDPOINT`
  - **Priority**: CRITICAL

### 2. Service Ports

#### Redis
- **Multiple files**
  - **Value**: `:6379`
  - **Variable**: `AUTOBOT_REDIS_PORT`
  - **Reason**: Redis port may vary in different environments
  - **Priority**: CRITICAL

#### Ollama
- **Files**: `src/config.py:501,524`, `backend/api/llm.py:310`
  - **Value**: `"http://127.0.0.2:11434"`
  - **Variable**: `AUTOBOT_OLLAMA_URL`
  - **Priority**: CRITICAL

#### AI Stack
- **Multiple files**
  - **Value**: `:8080`
  - **Variable**: `AUTOBOT_AI_STACK_PORT`
  - **Priority**: CRITICAL

#### NPU Worker
- **File**: `test_npu_worker.py:30`
  - **Value**: `"http://localhost:8081"`
  - **Variable**: `AUTOBOT_NPU_WORKER_URL`
  - **Priority**: CRITICAL

#### Playwright VNC
- **Files**: Various
  - **Value**: `:3000`
  - **Variable**: `AUTOBOT_PLAYWRIGHT_PORT`
  - **Priority**: CRITICAL

#### Seq Logging
- **Files**: Various
  - **Value**: `:5341`
  - **Variable**: `AUTOBOT_SEQ_PORT`
  - **Priority**: CRITICAL

### 3. Database Paths

#### Knowledge Base
- **Files**: `src/command_manual_manager.py:38`, `backend/services/config_service.py:114`
  - **Value**: `"data/knowledge_base.db"`
  - **Variable**: `AUTOBOT_KNOWLEDGE_BASE_PATH`
  - **Priority**: CRITICAL

#### Enhanced Memory
- **Files**: `src/enhanced_memory_manager.py:73`, `src/enhanced_memory_manager_async.py:96`
  - **Value**: `"data/enhanced_memory.db"`
  - **Variable**: `AUTOBOT_MEMORY_DB_PATH`
  - **Priority**: CRITICAL

#### Agent Memory
- **File**: `src/memory_manager.py:55`
  - **Value**: `"data/agent_memory.db"`
  - **Variable**: `AUTOBOT_LONG_TERM_DB_PATH`
  - **Priority**: CRITICAL

#### Secrets Database
- **File**: `backend/services/secrets_service.py:24`
  - **Value**: `"data/secrets.db"`
  - **Variable**: `AUTOBOT_SECRETS_DB_PATH`
  - **Priority**: CRITICAL

## High Priority

### 4. Data Directories

#### Chat Data
- **Files**: `backend/chat_api.py:34`, `backend/services/config_service.py:108`
  - **Value**: `"data/chats"`
  - **Variable**: `AUTOBOT_CHAT_DATA_DIR`
  - **Priority**: HIGH

#### Messages Directory
- **File**: `backend/chat_api.py:37`
  - **Value**: `"data/messages"`
  - **Variable**: `AUTOBOT_MESSAGES_DIR`
  - **Priority**: HIGH

#### ChromaDB Path
- **File**: `backend/services/config_service.py:216`
  - **Value**: `"data/chromadb"`
  - **Variable**: `AUTOBOT_CHROMADB_PATH`
  - **Priority**: HIGH

#### Chat Knowledge Storage
- **File**: `backend/api/chat_knowledge.py:93`
  - **Value**: `"data/chat_knowledge"`
  - **Variable**: `AUTOBOT_CHAT_KNOWLEDGE_DIR`
  - **Priority**: HIGH

### 5. Log Files & Paths

#### Application Logs
- **File**: `backend/services/config_service.py:164`
  - **Value**: `"logs/autobot.log"`
  - **Variable**: `AUTOBOT_LOG_FILE_PATH`
  - **Priority**: HIGH

#### Audit Logs
- **Files**: `backend/services/config_service.py:120`
  - **Value**: `"data/audit.log"`
  - **Variable**: `AUTOBOT_AUDIT_LOG_PATH`
  - **Priority**: HIGH

#### Fluentd Logs
- **File**: `docker/volumes/fluentd/fluent.conf:69,75`
  - **Values**: `/var/log/fluentd/fluent`, `/var/log/fluentd/buffer`
  - **Variables**: `FLUENTD_LOG_PATH`, `FLUENTD_BUFFER_PATH`
  - **Priority**: HIGH

### 6. Timeouts & Intervals

#### Circuit Breaker Timeouts
- **File**: `src/circuit_breaker.py:570-571,583-584,599-600`
  - **Values**: `recovery_timeout=30.0`, `timeout=120.0`, etc.
  - **Variables**: `CIRCUIT_BREAKER_LLM_TIMEOUT`, `CIRCUIT_BREAKER_RECOVERY_TIMEOUT`
  - **Priority**: HIGH

#### Command Execution Timeouts
- **File**: `src/intelligence/intelligent_agent.py:317,467,534`
  - **Values**: `timeout=300`, `timeout=600`
  - **Variables**: `COMMAND_EXECUTION_TIMEOUT`, `INSTALLATION_TIMEOUT`
  - **Priority**: HIGH

#### WebSocket Timeouts
- **File**: `src/npu_integration.py:215,252`
  - **Values**: `timeout=1.0`, `timeout=30.0`
  - **Variables**: `WEBSOCKET_QUEUE_TIMEOUT`, `NPU_PROCESSING_TIMEOUT`
  - **Priority**: HIGH

## Medium Priority

### 7. Model Names

#### LLM Models
- **Files**: Various
  - **Values**: `"gpt-4-turbo-preview"`, `"claude-3-opus-20240229"`, `"gemma"`, `"llama3.2"`
  - **Variables**: `DEFAULT_OPENAI_MODEL`, `DEFAULT_ANTHROPIC_MODEL`, etc.
  - **Priority**: MEDIUM

#### Embedding Models
- **File**: `scripts/populate_kb_chromadb.py:35`
  - **Value**: `"nomic-embed-text"`
  - **Variable**: `DEFAULT_EMBEDDING_MODEL`
  - **Priority**: MEDIUM

### 8. Container/Service Names

#### Docker Services
- **Files**: `docker/compose/*.yml`
  - **Values**: `autobot-redis`, `autobot-backend`, `autobot-frontend`, etc.
  - **Variables**: Service name prefixes should be configurable
  - **Priority**: MEDIUM

### 9. File Extensions & Patterns

#### Allowed File Types
- **File**: `src/secure_command_executor.py:153-155`
  - **Values**: `".txt"`, `".log"`, `".json"`
  - **Variable**: `ALLOWED_FILE_EXTENSIONS`
  - **Priority**: MEDIUM

#### Cleanup Patterns
- **File**: `backend/api/chat.py:2305,2328-2333`
  - **Values**: `"*.log"`, `"*_json_output.json"`, etc.
  - **Variable**: `CLEANUP_FILE_PATTERNS`
  - **Priority**: MEDIUM

### 10. System Paths

#### Temporary Directories
- **Files**: `src/secure_command_executor.py:147`, `src/desktop_streaming_manager.py:234`
  - **Values**: `/var/tmp`, `/tmp/`
  - **Variables**: `SYSTEM_TEMP_DIRS`
  - **Priority**: MEDIUM

### 10. Cache and Performance Settings

#### Database Cache Size
- **Files**: `src/memory_manager.py:94`, `src/enhanced_memory_manager_async.py:119`, `src/utils/database_pool.py:69`
  - **Value**: `cache_size=10000`
  - **Variable**: `DATABASE_CACHE_SIZE`
  - **Priority**: MEDIUM

#### Max Cache Sizes
- **File**: `src/context_aware_decision_system.py:131`
  - **Value**: `max_cache_size = 100`
  - **Variable**: `DECISION_SYSTEM_MAX_CACHE_SIZE`
  - **Priority**: MEDIUM

- **File**: `src/computer_vision_system.py:108`
  - **Value**: `cache_size = 5`
  - **Variable**: `VISION_SYSTEM_CACHE_SIZE`
  - **Priority**: MEDIUM

### 11. Queue and Channel Names

#### Redis Channels
- **File**: `src/enhanced_multi_agent_orchestrator.py:435,439,445`
  - **Values**: Collaboration channel patterns
  - **Variable**: `REDIS_CHANNEL_PREFIX`
  - **Priority**: MEDIUM

### 12. Default Function Parameters

#### Retention Periods
- **File**: `src/enhanced_memory_manager_async.py:519`
  - **Value**: `retention_days: int = 90`
  - **Variable**: `DEFAULT_RETENTION_DAYS`
  - **Priority**: MEDIUM

- **File**: `src/enhanced_memory_manager.py:618`
  - **Value**: `days_to_keep: int = 90`
  - **Variable**: `DEFAULT_DAYS_TO_KEEP`
  - **Priority**: MEDIUM

#### Performance Analysis Periods
- **Files**: `src/task_execution_tracker.py:171,214`, `src/enhanced_memory_manager.py:553`
  - **Value**: `days_back: int = 30`
  - **Variable**: `DEFAULT_ANALYSIS_DAYS`
  - **Priority**: MEDIUM

#### Command History Limit
- **File**: `src/secure_command_executor.py:455`
  - **Value**: `limit: int = 100`
  - **Variable**: `DEFAULT_COMMAND_HISTORY_LIMIT`
  - **Priority**: MEDIUM

#### Concurrency Limits
- **File**: `src/npu_integration.py:185`
  - **Value**: `max_concurrent: int = 3`
  - **Variable**: `NPU_MAX_CONCURRENT_TASKS`
  - **Priority**: MEDIUM

#### Security Key Length
- **File**: `src/encryption_service.py:220`
  - **Value**: `length: int = 64`
  - **Variable**: `DEFAULT_SECURITY_KEY_LENGTH`
  - **Priority**: MEDIUM

## Low Priority

### 13. UI/Display Values

#### Browser Settings
- **File**: `autobot-vue/src/components/ComputerDesktopViewer.vue:14`
  - **Value**: `"http://localhost:6080/vnc.html"`
  - **Variable**: `VNC_VIEWER_URL`
  - **Priority**: LOW

### 12. Search Engine URLs

#### Web Search
- **Files**: `src/agents/librarian_assistant_agent.py:60-62`
  - **Values**: DuckDuckGo, Bing, Google search URLs
  - **Variable**: `SEARCH_ENGINE_URLS`
  - **Priority**: LOW

### 13. Example/Test URLs

#### Documentation Examples
- **Files**: Various test and example files
  - **Values**: `"https://example.com"`, etc.
  - **Priority**: LOW (These can remain hardcoded as they're examples)

### 14. Frontend API Endpoints

#### API Path Prefixes
- **File**: `autobot-vue/src/config/environment.js:31-62`
  - **Values**: All API endpoint paths (`/api/system/health`, `/api/chat`, etc.)
  - **Variable**: These are already centralized but could be made configurable
  - **Priority**: LOW (Already centralized in configuration)

#### Developer API Endpoints
- **File**: `autobot-vue/src/services/SettingsService.js:220,240,254`
  - **Values**: `/api/developer/config`, `/api/developer/endpoints`
  - **Variable**: Already using centralized API client
  - **Priority**: LOW

## Implementation Recommendations

### 1. Create Central Configuration Module
```python
# config/environment.py
import os
from typing import Dict, Any

class EnvironmentConfig:
    # API Endpoints
    BACKEND_API_URL = os.getenv('AUTOBOT_BACKEND_API_URL', 'http://localhost:8001')
    FRONTEND_URL = os.getenv('AUTOBOT_FRONTEND_URL', 'http://localhost:5173')

    # Service Ports
    REDIS_PORT = int(os.getenv('AUTOBOT_REDIS_PORT', '6379'))
    OLLAMA_PORT = int(os.getenv('AUTOBOT_OLLAMA_PORT', '11434'))

    # Database Paths
    KNOWLEDGE_BASE_PATH = os.getenv('AUTOBOT_KNOWLEDGE_BASE_PATH', 'data/knowledge_base.db')
    MEMORY_DB_PATH = os.getenv('AUTOBOT_MEMORY_DB_PATH', 'data/enhanced_memory.db')

    # Timeouts
    DEFAULT_TIMEOUT = int(os.getenv('AUTOBOT_DEFAULT_TIMEOUT', '30'))
    LLM_TIMEOUT = int(os.getenv('AUTOBOT_LLM_TIMEOUT', '120'))
```

### 2. Update .env.example
Add all identified environment variables with sensible defaults.

### 3. Migration Strategy
1. **Phase 1**: Critical priority items (APIs, ports, databases)
2. **Phase 2**: High priority items (directories, logs, timeouts)
3. **Phase 3**: Medium priority items (models, containers, patterns)
4. **Phase 4**: Low priority items (UI values, search URLs)

### 4. Testing Requirements
- Test each configuration change in development environment
- Verify Docker compose files work with new variables
- Update deployment scripts to include new environment variables
- Create validation script to check all required variables are set

## Total Findings Summary
- **Critical Priority**: 25 hardcoded values
- **High Priority**: 32 hardcoded values
- **Medium Priority**: 36 hardcoded values (updated with cache, queue, and default parameters)
- **Low Priority**: 8 hardcoded values
- **Total**: 101 hardcoded values requiring configuration

## Next Steps
1. Review and prioritize this list with the team
2. Create environment variable naming convention
3. Implement changes in phases
4. Update documentation and deployment guides
5. Add configuration validation to startup scripts

## Recommended .env.example Additions

```bash
# API Endpoints
AUTOBOT_BACKEND_API_URL=http://localhost:8001
AUTOBOT_FRONTEND_URL=http://localhost:5173
AUTOBOT_OPENAI_API_ENDPOINT=https://api.openai.com/v1/chat/completions
AUTOBOT_ANTHROPIC_API_ENDPOINT=https://api.anthropic.com/v1/messages
AUTOBOT_LM_STUDIO_ENDPOINT=http://localhost:1234/v1

# Service Ports
AUTOBOT_REDIS_PORT=6379
AUTOBOT_OLLAMA_URL=http://127.0.0.2:11434
AUTOBOT_AI_STACK_PORT=8080
AUTOBOT_NPU_WORKER_URL=http://localhost:8081
AUTOBOT_PLAYWRIGHT_PORT=3000
AUTOBOT_SEQ_PORT=5341

# Database Paths
AUTOBOT_KNOWLEDGE_BASE_PATH=data/knowledge_base.db
AUTOBOT_MEMORY_DB_PATH=data/enhanced_memory.db
AUTOBOT_LONG_TERM_DB_PATH=data/agent_memory.db
AUTOBOT_SECRETS_DB_PATH=data/secrets.db

# Data Directories
AUTOBOT_CHAT_DATA_DIR=data/chats
AUTOBOT_MESSAGES_DIR=data/messages
AUTOBOT_CHROMADB_PATH=data/chromadb
AUTOBOT_CHAT_KNOWLEDGE_DIR=data/chat_knowledge

# Logging
AUTOBOT_LOG_FILE_PATH=logs/autobot.log
AUTOBOT_AUDIT_LOG_PATH=data/audit.log
FLUENTD_LOG_PATH=/var/log/fluentd/fluent
FLUENTD_BUFFER_PATH=/var/log/fluentd/buffer

# Timeouts (in seconds)
CIRCUIT_BREAKER_LLM_TIMEOUT=120
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
COMMAND_EXECUTION_TIMEOUT=300
INSTALLATION_TIMEOUT=600
WEBSOCKET_QUEUE_TIMEOUT=1
NPU_PROCESSING_TIMEOUT=30

# Performance Settings
DATABASE_CACHE_SIZE=10000
DECISION_SYSTEM_MAX_CACHE_SIZE=100
VISION_SYSTEM_CACHE_SIZE=5
NPU_MAX_CONCURRENT_TASKS=3

# Retention Settings
DEFAULT_RETENTION_DAYS=90
DEFAULT_DAYS_TO_KEEP=90
DEFAULT_ANALYSIS_DAYS=30
DEFAULT_COMMAND_HISTORY_LIMIT=100

# Security
DEFAULT_SECURITY_KEY_LENGTH=64

# Model Names (Optional - can be left as defaults)
# DEFAULT_OPENAI_MODEL=gpt-4-turbo-preview
# DEFAULT_ANTHROPIC_MODEL=claude-3-opus-20240229
# DEFAULT_EMBEDDING_MODEL=nomic-embed-text
```
