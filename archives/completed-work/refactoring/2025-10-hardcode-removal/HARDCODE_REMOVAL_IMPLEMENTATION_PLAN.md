# Comprehensive Hardcode Removal - Implementation Plan

**Date**: 2025-10-21
**Objective**: Systematically eliminate ALL hardcoded values (IPs, ports, paths) across AutoBot codebase
**Scope**: 596 hardcoded IPs + 185 hardcoded paths = 781 total hardcodes

---

## Executive Summary

### Current State

**Hardcode Inventory** (from `/tmp/hardcode_report.txt`):
- **596 hardcoded IP addresses** (`172.16.168.*`)
- **185 hardcoded paths** (`/home/kali/Desktop/AutoBot`)
- **Multiple hardcoded ports** scattered throughout

**Existing Infrastructure** (UNDERUTILIZED):
- `src/constants/network_constants.py` - Comprehensive Python constants (EXISTS but NOT widely used)
- `autobot-vue/src/config/defaults.js` - Frontend config (EXISTS but inconsistent usage)
- No path constants infrastructure for Python
- No constants infrastructure for TypeScript MCP tools

**Problem**: Constants files exist but were never fully integrated. Most code still uses hardcoded values.

### Implementation Strategy

**5-Phase Systematic Refactoring**:
1. **Phase 1**: Establish missing constants infrastructure
2. **Phase 2**: Refactor Python backend (40+ critical files)
3. **Phase 3**: Refactor TypeScript/JavaScript (MCP tools + frontend)
4. **Phase 4**: Update configuration files (YAML/ENV)
5. **Phase 5**: Comprehensive testing and validation

**Target**: Zero hardcoded values in production code (excluding `temp/`, `venv/`, `archive/`)

---

## Phase 1: Constants Infrastructure

### 1.1 Create Python Path Constants

**File**: `src/constants/path_constants.py` (NEW)

**Requirements**:
```python
from pathlib import Path
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class PathConstants:
    """Centralized path constants for AutoBot"""

    # Dynamically detect project root (NEVER hardcode)
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

    # Core directories
    SRC_DIR: Path = PROJECT_ROOT / "src"
    BACKEND_DIR: Path = PROJECT_ROOT / "backend"
    FRONTEND_DIR: Path = PROJECT_ROOT / "autobot-vue"

    # Data directories
    DATA_DIR: Path = PROJECT_ROOT / "data"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    TEMP_DIR: Path = PROJECT_ROOT / "temp"

    # Configuration
    CONFIG_DIR: Path = PROJECT_ROOT / "config"
    SECURITY_CONFIG_DIR: Path = CONFIG_DIR / "security"

    # Security
    SECURITY_DIR: Path = DATA_DIR / "security"
    AUDIT_LOGS_DIR: Path = LOGS_DIR / "audit"

    # Database
    DATABASE_DIR: Path = PROJECT_ROOT / "database"
    MIGRATIONS_DIR: Path = DATABASE_DIR / "migrations"

    # Tests
    TESTS_DIR: Path = PROJECT_ROOT / "tests"
    TEST_RESULTS_DIR: Path = TESTS_DIR / "results"

    # User home (for SSH keys, etc.)
    USER_HOME: Path = Path.home()
    SSH_DIR: Path = USER_HOME / ".ssh"
    AUTOBOT_CONFIG_DIR: Path = USER_HOME / ".autobot"
```

**Why Dynamic Detection**:
- Never hardcodes `/home/kali/Desktop/AutoBot`
- Works on any machine, any user
- Works in WSL, Linux, or Docker containers

### 1.2 Create TypeScript Constants for MCP Tools

**File**: `mcp-tools/mcp-autobot-tracker/src/constants/network.ts` (NEW)

```typescript
/**
 * Network Constants for AutoBot MCP Tools
 * Mirrors Python network_constants.py for consistency
 */

export const NetworkConstants = {
  // Main machine (WSL)
  MAIN_MACHINE_IP: '172.16.168.20',

  // VM Infrastructure IPs
  FRONTEND_VM_IP: '172.16.168.21',
  NPU_WORKER_VM_IP: '172.16.168.22',
  REDIS_VM_IP: '172.16.168.23',
  AI_STACK_VM_IP: '172.16.168.24',
  BROWSER_VM_IP: '172.16.168.25',

  // Ports
  BACKEND_PORT: 8001,
  FRONTEND_PORT: 5173,
  REDIS_PORT: 6379,
  NPU_WORKER_PORT: 8081,
  AI_STACK_PORT: 8080,
  BROWSER_PORT: 3000,

  // Protocols
  HTTP_PROTOCOL: 'http',
  REDIS_PROTOCOL: 'redis',
} as const;

export const ServiceURLs = {
  backend: () => `${NetworkConstants.HTTP_PROTOCOL}://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`,
  frontend: () => `${NetworkConstants.HTTP_PROTOCOL}://${NetworkConstants.FRONTEND_VM_IP}:${NetworkConstants.FRONTEND_PORT}`,
  redis: () => `${NetworkConstants.REDIS_PROTOCOL}://${NetworkConstants.REDIS_VM_IP}:${NetworkConstants.REDIS_PORT}`,
  npuWorker: () => `${NetworkConstants.HTTP_PROTOCOL}://${NetworkConstants.NPU_WORKER_VM_IP}:${NetworkConstants.NPU_WORKER_PORT}`,
  aiStack: () => `${NetworkConstants.HTTP_PROTOCOL}://${NetworkConstants.AI_STACK_VM_IP}:${NetworkConstants.AI_STACK_PORT}`,
  browser: () => `${NetworkConstants.HTTP_PROTOCOL}://${NetworkConstants.BROWSER_VM_IP}:${NetworkConstants.BROWSER_PORT}`,
} as const;
```

**File**: `mcp-tools/mcp-autobot-tracker/src/constants/paths.ts` (NEW)

```typescript
import * as path from 'path';
import * as os from 'os';

/**
 * Path Constants for AutoBot MCP Tools
 * Use environment variables with fallbacks
 */

const PROJECT_ROOT = process.env.AUTOBOT_PROJECT_ROOT || '/home/kali/Desktop/AutoBot';

export const PathConstants = {
  PROJECT_ROOT,

  // Data directories
  DATA_DIR: path.join(PROJECT_ROOT, 'data'),
  LOGS_DIR: path.join(PROJECT_ROOT, 'logs'),

  // Specific log files
  BACKEND_LOG: path.join(PROJECT_ROOT, 'data/logs/backend.log'),
  FRONTEND_LOG: path.join(PROJECT_ROOT, 'data/logs/frontend.log'),
  REDIS_LOG: path.join(PROJECT_ROOT, 'data/logs/redis.log'),
  CHAT_LOG: path.join(PROJECT_ROOT, 'data/logs/chat.log'),

  // Conversation data
  CONVERSATIONS_DIR: path.join(PROJECT_ROOT, 'data/conversations'),
  CHAT_HISTORY_DIR: path.join(PROJECT_ROOT, 'data/chat_history'),

  // User home
  USER_HOME: os.homedir(),
  SSH_DIR: path.join(os.homedir(), '.ssh'),
} as const;
```

### 1.3 Update Frontend Config (Enhancement)

**File**: `autobot-vue/src/config/defaults.js` (ALREADY EXISTS - verify comprehensive)

**Action**: Review and ensure all service configurations are present. Current file looks good.

---

## Phase 2: Python Backend Refactoring

### Priority Files (Highest Impact)

#### 2.1 Critical Backend Files (40+ files)

**Group A: Redis Utilities** (10 files)
1. `src/utils/distributed_redis_client.py` - **12 hardcoded references**
2. `src/utils/async_redis_manager.py` - Redis host hardcoded
3. `src/utils/redis_helper.py` - Default host hardcoded in 3 functions
4. `src/utils/redis_client.py` - Hardcoded fallback
5. `src/utils/redis_database_manager.py` - Path hardcoded
6. `src/utils/redis_immediate_test.py` - Test configuration

**Refactoring Pattern**:
```python
# BEFORE:
redis_client = Redis(host="172.16.168.23", port=6379, db=0)

# AFTER:
from src.constants.network_constants import NetworkConstants
redis_client = Redis(
    host=NetworkConstants.REDIS_VM_IP,
    port=NetworkConstants.REDIS_PORT,
    db=0
)
```

**Group B: Backend API Files** (20+ files)
1. `backend/api/service_monitor.py` - Multiple VM IPs hardcoded
2. `backend/api/knowledge.py` - Documentation contains hardcoded IPs
3. `backend/api/cache.py` - Redis IP in comments
4. `backend/api/terminal.py` - Initial directory hardcoded
5. `backend/api/base_terminal.py` - Working directory hardcoded
6. `backend/api/logs.py` - Log directory hardcoded
7. `backend/api/long_running_operations.py` - Multiple path defaults
8. `backend/api/registry_update.py` - Registry file path hardcoded

**Refactoring Pattern**:
```python
# BEFORE:
log_dir = "/home/kali/Desktop/AutoBot/logs"
initial_cwd = "/home/kali/Desktop/AutoBot"

# AFTER:
from src.constants.path_constants import PathConstants
log_dir = PathConstants.LOGS_DIR
initial_cwd = PathConstants.PROJECT_ROOT
```

**Group C: Security Modules** (8 files)
1. `src/security/enterprise/compliance_manager.py`
2. `src/security/enterprise/sso_integration.py`
3. `src/security/enterprise/security_policy_manager.py`
4. `src/security/enterprise/threat_detection.py`
5. `src/security/enterprise/domain_reputation.py`

**Refactoring Pattern**:
```python
# BEFORE:
config_path = "/home/kali/Desktop/AutoBot/config/security/compliance.yaml"
audit_logs = "/home/kali/Desktop/AutoBot/logs/audit"

# AFTER:
from src.constants.path_constants import PathConstants
config_path = PathConstants.SECURITY_CONFIG_DIR / "compliance.yaml"
audit_logs = PathConstants.AUDIT_LOGS_DIR
```

**Group D: Services** (5 files)
1. `backend/services/agent_terminal_service.py`
2. `backend/services/simple_pty.py`
3. `backend/services/infrastructure_db.py`
4. `src/services/codebase_indexing_service.py`

**Group E: Configuration & Analysis** (10+ files)
1. `src/unified_config.py`
2. `src/config_helper.py`
3. `src/config_consolidated.py`
4. `analysis/reorganize_redis_databases.py`
5. `analysis/fix_analytics_redis_timeout.py`
6. `analysis/create_code_vector_knowledge.py`
7. `analysis/migrate_vectors_to_db0.py`

#### 2.2 Systematic Refactoring Process

For each file:

1. **Read** the file to understand current usage
2. **Add imports** at top:
   ```python
   from src.constants.network_constants import NetworkConstants, ServiceURLs
   from src.constants.path_constants import PathConstants
   ```
3. **Replace** all hardcoded values:
   - IPs: Use `NetworkConstants.X_VM_IP`
   - Service URLs: Use `ServiceURLs.X`
   - Paths: Use `PathConstants.X_DIR` or `PathConstants.PROJECT_ROOT / "relative/path"`
4. **Test** the file's functionality
5. **Commit** the change

**Refactoring Checklist Per File**:
- [ ] Import constants modules
- [ ] Replace all IP addresses
- [ ] Replace all port numbers
- [ ] Replace all absolute paths
- [ ] Update function defaults
- [ ] Update docstrings/comments
- [ ] Test functionality
- [ ] Verify no regressions

---

## Phase 3: TypeScript/JavaScript Refactoring

### 3.1 MCP Tools (56+ hardcodes)

**Critical Files**:
1. `mcp-tools/mcp-autobot-tracker/src/background-monitor.ts` - **18 hardcoded IPs**
2. `mcp-tools/mcp-autobot-tracker/src/real-time-ingestion.ts` - 4 paths, 1 IP
3. `mcp-tools/mcp-autobot-tracker/src/index.ts` - Redis IP
4. `mcp-tools/mcp-autobot-tracker/src/tests/mcp-server.test.ts` - Test configs

**Refactoring Pattern**:
```typescript
// BEFORE:
const services = [
  { name: 'frontend', url: 'http://172.16.168.21:5173/health' },
  { name: 'redis', url: 'redis://172.16.168.23:6379' },
];
const logPath = '/home/kali/Desktop/AutoBot/data/logs/backend.log';

// AFTER:
import { NetworkConstants, ServiceURLs } from './constants/network';
import { PathConstants } from './constants/paths';

const services = [
  { name: 'frontend', url: `${ServiceURLs.frontend()}/health` },
  { name: 'redis', url: ServiceURLs.redis() },
];
const logPath = PathConstants.BACKEND_LOG;
```

**Process**:
1. Create `mcp-tools/mcp-autobot-tracker/src/constants/network.ts`
2. Create `mcp-tools/mcp-autobot-tracker/src/constants/paths.ts`
3. Update `background-monitor.ts` (most hardcodes)
4. Update `real-time-ingestion.ts`
5. Update `index.ts`
6. Update test files
7. Rebuild TypeScript: `npm run build`

### 3.2 Frontend Components

**Check**: Most frontend should already use `appConfig` from `autobot-vue/src/config/defaults.js`

**Action**: Audit for any remaining hardcodes
```bash
grep -r "172.16.168\." autobot-vue/src/ --include="*.vue" --include="*.js" --include="*.ts"
grep -r "/home/kali" autobot-vue/src/ --include="*.vue" --include="*.js" --include="*.ts"
```

**If found**: Replace with imports from `@/config/defaults.js`

### 3.3 Temporary Test Files

**Files in** `temp/` directory:
- `debug_frontend_detailed.js`
- `analyze_layout.js`
- Multiple test scripts with hardcoded IPs

**Action**: These are temporary/experimental. Can be refactored if still in use, otherwise document in exclusions.

---

## Phase 4: Configuration Files

### 4.1 YAML Configuration Files

**Files to Review**:
- `config/config.yaml`
- `config/complete.yaml`
- `config/redis-databases.yaml`
- `config/security/*.yaml`

**Action**: Ensure using environment variable references
```yaml
# BEFORE:
redis:
  host: "172.16.168.23"
  port: 6379

# AFTER:
redis:
  host: ${REDIS_HOST:-172.16.168.23}
  port: ${REDIS_PORT:-6379}
```

### 4.2 Environment Files

**Update** `.env.example`:
```bash
# Network Configuration
REDIS_HOST=172.16.168.23
REDIS_PORT=6379
BACKEND_HOST=172.16.168.20
BACKEND_PORT=8001
FRONTEND_HOST=172.16.168.21
FRONTEND_PORT=5173
NPU_WORKER_HOST=172.16.168.22
NPU_WORKER_PORT=8081
AI_STACK_HOST=172.16.168.24
AI_STACK_PORT=8080
BROWSER_HOST=172.16.168.25
BROWSER_PORT=3000

# Path Configuration
AUTOBOT_PROJECT_ROOT=/home/kali/Desktop/AutoBot
AUTOBOT_DATA_DIR=/home/kali/Desktop/AutoBot/data
AUTOBOT_LOGS_DIR=/home/kali/Desktop/AutoBot/logs
```

**Document**: Clear instructions in `.env.example` for users to customize

---

## Phase 5: Testing & Validation

### 5.1 Incremental Testing

**After each file refactoring**:
1. Run affected endpoints/services
2. Check logs for errors
3. Verify connections work

**Critical Tests**:
```bash
# Backend health
curl http://172.16.168.20:8001/api/health

# Redis connection
redis-cli -h 172.16.168.23 ping

# Frontend service
curl http://172.16.168.21:5173/

# Analytics endpoints (use refactored files)
curl http://172.16.168.20:8001/api/analytics/codebase/stats
```

### 5.2 Final Validation

**Run comprehensive hardcode scan**:
```bash
# Should find ZERO in production code
grep -r "172.16.168\." --include="*.py" --include="*.ts" --include="*.js" --include="*.vue" \
  --exclude-dir=venv --exclude-dir=node_modules --exclude-dir=temp --exclude-dir=archive \
  /home/kali/Desktop/AutoBot/

grep -r "/home/kali" --include="*.py" --include="*.ts" --include="*.js" --include="*.vue" \
  --exclude-dir=venv --exclude-dir=node_modules --exclude-dir=temp --exclude-dir=archive \
  /home/kali/Desktop/AutoBot/
```

### 5.3 Validation Report

**Generate** `/home/kali/Desktop/AutoBot/reports/refactoring/HARDCODE_REMOVAL_VALIDATION.md`:

```markdown
# Hardcode Removal Validation Report

## Before Refactoring
- IP addresses: 596
- Paths: 185
- Total: 781 hardcodes

## After Refactoring
- IP addresses: X remaining (justified)
- Paths: Y remaining (justified)
- Total: Z hardcodes

## Remaining Hardcodes (Justified)
1. File: reason
2. File: reason

## Testing Results
- [ ] Backend API: PASS
- [ ] Redis connections: PASS
- [ ] Frontend services: PASS
- [ ] Analytics endpoints: PASS
- [ ] MCP tools: PASS

## Regression Tests
- [ ] Chat functionality: PASS
- [ ] Terminal sessions: PASS
- [ ] Knowledge base: PASS
- [ ] Service monitoring: PASS
```

---

## Exclusions (DO NOT REFACTOR)

### Permanent Exclusions
- `venv/` - Third-party packages
- `node_modules/` - Third-party packages
- `archive/` - Archived/legacy code
- `reports/finished/archives/` - Historical reports

### Temporary Exclusions (Review Later)
- `temp/` - Temporary experimental scripts (if still in use, document)
- Documentation examples (optional - can update for consistency)
- API schema examples in Pydantic models (not critical)

---

## Implementation Timeline

### Estimated Effort
- **Phase 1** (Infrastructure): 2 hours
- **Phase 2** (Python Backend): 8-12 hours (40+ files)
- **Phase 3** (TypeScript/JS): 4-6 hours
- **Phase 4** (Config Files): 1-2 hours
- **Phase 5** (Testing): 3-4 hours
- **Total**: 18-26 hours

### Recommended Approach
1. **Sprint 1** (Day 1): Phase 1 - Create all constants infrastructure
2. **Sprint 2** (Days 2-3): Phase 2 - Refactor Python backend (Group A + B)
3. **Sprint 3** (Day 4): Phase 2 - Refactor Python (Groups C, D, E)
4. **Sprint 4** (Day 5): Phase 3 - Refactor TypeScript MCP tools
5. **Sprint 5** (Day 6): Phase 4 + Phase 5 - Config files + comprehensive testing

---

## Success Criteria

- [ ] All constants infrastructure files created
- [ ] Zero hardcoded IPs in backend API files
- [ ] Zero hardcoded IPs in MCP tools
- [ ] Zero hardcoded paths in security modules
- [ ] All services connect successfully after refactoring
- [ ] No regressions in existing functionality
- [ ] Final validation report shows <10 remaining hardcodes (all justified)
- [ ] Documentation updated with constants usage guidelines

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Create git branch**: `refactor/remove-all-hardcodes`
3. **Start Phase 1**: Create constants infrastructure
4. **Incremental commits**: Commit after each file/module refactored
5. **Continuous testing**: Test after each group of files
6. **Final PR**: Comprehensive code review before merging

---

**Document Created**: 2025-10-21
**Report Location**: `/home/kali/Desktop/AutoBot/reports/refactoring/HARDCODE_REMOVAL_IMPLEMENTATION_PLAN.md`
**Source Analysis**: `/tmp/hardcode_report.txt`
