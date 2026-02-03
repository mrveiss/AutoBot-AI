# Single Source of Truth Configuration Architecture

<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss
-->

**Issue**: #599
**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Date**: 2025-12-25
**Status**: Architecture Design

---

## Executive Summary

This document defines the Single Source of Truth (SSOT) configuration architecture for AutoBot. After comprehensive analysis of the current 19+ configuration files across Python backend, Vue/TypeScript frontend, shell scripts, and infrastructure components, this design provides a unified approach that eliminates redundancy while maintaining type safety, environment awareness, and cross-language compatibility.

---

## 1. Current State Analysis

### 1.1 Configuration Sources Inventory

| Category | File/Module | Lines | Purpose | Problems |
|----------|-------------|-------|---------|----------|
| **Backend - Config Package** | | | | |
| | `src/config/manager.py` | ~96 | Core UnifiedConfigManager | Good architecture |
| | `src/config/settings.py` | ~35 | Pydantic settings | Separate from main |
| | `src/config/defaults.py` | ~183 | Default config generation | Hardcoded fallbacks |
| | `src/config/loader.py` | ~192 | Config loading/merging | Complex precedence |
| | `src/config/sync_ops.py` | ~140 | Synchronous operations | Duplicates async |
| | `src/config/async_ops.py` | ~220 | Async operations | Complex |
| | `src/config/model_config.py` | ~120 | LLM model management | Overlaps constants |
| | `src/config/service_config.py` | ~240 | Service host/port config | Overlaps network_constants |
| | `src/config/timeout_config.py` | ~140 | Timeout management | Scattered across files |
| **Backend - Constants** | | | | |
| | `src/constants/network_constants.py` | ~380 | IPs, ports, URLs | CRITICAL: Hardcoded fallbacks |
| | `src/constants/model_constants.py` | ~189 | LLM model names | Overlaps config |
| | `src/constants/path_constants.py` | ~99 | Directory paths | Good isolation |
| | `src/constants/redis_constants.py` | ~? | Redis-specific | Overlaps network |
| | `src/constants/security_constants.py` | ~? | Security settings | |
| | `src/constants/threshold_constants.py` | ~? | Thresholds | |
| **Backend - Models** | | | | |
| | `backend/models/settings.py` | ~389 | Pydantic AutoBotSettings | Separate validation |
| | `backend/services/config_service.py` | ~502 | API layer for config CRUD | Wrapper complexity |
| **Frontend** | | | | |
| | `autobot-vue/src/config/defaults.js` | ~200 | DEFAULT_CONFIG with fallbacks | Hardcoded IPs |
| | `autobot-vue/src/config/ServiceDiscovery.js` | ~488 | Dynamic URL resolution | Complex fallback logic |
| | `autobot-vue/src/constants/network.ts` | ~204 | TypeScript network constants | Mirrors Python |
| | `vite.config.ts` | ~280 | Vite configuration | Hardcoded NETWORK_DEFAULTS |
| **Environment Files** | | | | |
| | `.env` / `.env.example` | ~260 | Environment variables | Multiple sources |
| | `autobot-vue/.env.example` | ~20 | Frontend env vars | Separate from backend |
| | `config/config.yaml` | ~652 | Runtime configuration | Deeply nested, duplicated |

### 1.2 Key Problems Identified

1. **No Single Authority**: 19+ files contain configuration logic with unclear precedence
2. **Hardcoded Fallbacks**: IP addresses (172.16.168.x) hardcoded in 6+ locations
3. **Cross-Language Duplication**: Python `NetworkConstants` duplicated in TypeScript
4. **Complex Precedence**: `config.yaml` -> `settings.json` -> environment variables
5. **Nested Duplication**: `config.yaml` has 5+ levels of nested `unified` blocks (bug)
6. **Environment File Fragmentation**: `.env` and `autobot-vue/.env` not synchronized
7. **Type Safety Gap**: Frontend defaults.js lacks TypeScript types
8. **Hot Reload Complexity**: Multiple file watchers, unclear which triggers updates

### 1.3 Configuration Value Categories

| Category | Example Values | Current Source(s) |
|----------|----------------|-------------------|
| **Network Infrastructure** | VM IPs, ports | `network_constants.py`, `defaults.js`, `.env` |
| **Service URLs** | API endpoints, WebSocket | Built dynamically from IPs/ports |
| **LLM Configuration** | Model names, endpoints, providers | `model_constants.py`, `config.yaml` |
| **Redis Configuration** | Host, port, databases | `network_constants.py`, `redis_constants.py` |
| **Timeouts** | HTTP, LLM, Redis operation timeouts | `config.yaml`, `timeout_config.py` |
| **Paths** | Directories, log files | `path_constants.py`, `.env` |
| **UI Settings** | Theme, language, animations | `config.yaml`, frontend store |
| **Feature Flags** | WebSockets, VNC, debug mode | `config.yaml`, `.env` |
| **Security** | Auth, encryption, session timeout | `config.yaml`, `security_constants.py` |

---

## 2. Architecture Approaches

### 2.1 Approach A: JSON Schema Master with Code Generation

**Concept**: Single JSON Schema file defines ALL configuration. Code generators produce:
- Python Pydantic models
- TypeScript interfaces
- Default YAML templates
- Documentation

```
master-config-schema.json
    |
    +-> generate-python.py -> src/config/generated/models.py
    +-> generate-typescript.ts -> autobot-vue/src/config/generated/types.ts
    +-> generate-yaml.py -> config/config.yaml.template
    +-> generate-docs.py -> docs/configuration-reference.md
```

**Pros**:
- True single source of truth
- Automatic cross-language consistency
- Self-documenting schema
- Validation baked in

**Cons**:
- Build step complexity
- Learning curve for JSON Schema
- Generated code can be hard to debug
- Runtime schema loading adds complexity

**Complexity**: High
**Risk**: Medium (well-established pattern)

---

### 2.2 Approach B: Python-First with TypeScript Export API

**Concept**: Python remains the authority. Backend exposes `/api/config/schema` endpoint that frontend consumes at build/runtime.

```
Python (Authority)                     TypeScript (Consumer)
----------------                       -------------------
src/config/schema.py           ->      GET /api/config/schema
  - Pydantic models                    -> generate types.ts (build time)
  - Validation rules                   -> fetch config (runtime)
  - Defaults                           -> type-safe consumption
```

**Implementation**:
```python
# Backend: src/config/schema.py
class AutoBotConfigSchema(BaseModel):
    """Master configuration schema - exports to TypeScript"""

    network: NetworkSchema
    llm: LLMSchema
    redis: RedisSchema
    timeouts: TimeoutSchema
    ui: UISchema

    class Config:
        json_schema_extra = {
            "title": "AutoBot Configuration",
            "description": "Single source of truth for all AutoBot configuration"
        }

    def export_typescript_types(self) -> str:
        """Generate TypeScript interface from Pydantic model"""
        # Uses pydantic-to-typescript or custom generator
```

**Pros**:
- Python ecosystem leveraged (Pydantic excellent)
- No build step for Python code
- Runtime schema available for UI
- Incremental migration possible

**Cons**:
- TypeScript depends on Python for types
- Build-time code generation still needed
- API must be available for frontend build

**Complexity**: Medium
**Risk**: Low (builds on existing Pydantic)

---

### 2.3 Approach C: Environment-Centric with Layered Defaults (RECOMMENDED)

**Concept**: Single canonical `.env` file as the true source. All other config files are either:
1. **Default providers** (read-only, provide fallbacks)
2. **Schema validators** (validate .env values)
3. **Derived consumers** (build values from .env)

```
                     .env (SSOT)
                         |
           +-------------+-------------+
           |             |             |
     Python Loader   TypeScript     Shell
           |          Loader       Scripts
           v             v             v
    Pydantic Models  Vite Env      Bash vars
    + NetworkConstants  + network.ts
```

**Key Principles**:
1. **All configuration values defined in `.env`** with `AUTOBOT_` prefix
2. **Frozen defaults in code** are only used if `.env` missing (emergency fallback)
3. **No hardcoded values in business logic** - always reference config
4. **Runtime config.yaml for mutable state** (user preferences, not infrastructure)

**Implementation Layers**:

```
Layer 1: .env (Required Configuration)
-----------------------------------------
AUTOBOT_MAIN_MACHINE_IP=172.16.168.20
AUTOBOT_FRONTEND_VM_IP=172.16.168.21
AUTOBOT_REDIS_VM_IP=172.16.168.23
AUTOBOT_BACKEND_PORT=8001
AUTOBOT_DEFAULT_LLM_MODEL=mistral:7b-instruct

Layer 2: Frozen Code Defaults (Emergency Fallback)
--------------------------------------------------
# Only used if .env completely missing
# NEVER for production

Layer 3: Runtime YAML (User Preferences)
----------------------------------------
# Mutable settings like UI theme, not infrastructure
config/user-preferences.yaml

Layer 4: Language-Specific Loaders
----------------------------------
# Python: src/config/env_loader.py
# TypeScript: src/config/env-loader.ts
# Both read same .env, validate, provide typed access
```

**Pros**:
- Simple mental model (env vars = config)
- Standard 12-factor app pattern
- No code generation required
- Docker/K8s friendly
- Easy to override per environment

**Cons**:
- Flat namespace (mitigated by prefix convention)
- Secrets need special handling
- Complex nested config awkward in env vars

**Complexity**: Low
**Risk**: Very Low (proven pattern)

---

## 3. Recommended Approach: Environment-Centric (Approach C)

### 3.1 Rationale

After analyzing the current state and considering AutoBot's distributed 6-VM architecture:

1. **Simplicity Wins**: The current 19-file fragmentation is a maintenance nightmare. A single `.env` file with clear prefixes is immediately understandable.

2. **Docker/VM Friendly**: Each VM can have its own `.env` with overrides. This matches the distributed deployment model.

3. **No Build Step**: Approach A requires code generation. Approach C works immediately.

4. **Incremental Migration**: Can migrate file-by-file without breaking changes.

5. **Existing Foundation**: The `.env.example` already has most configuration defined.

### 3.2 Master Configuration Schema

The canonical `.env` structure with all configuration values:

```bash
# =============================================================================
# AUTOBOT MASTER CONFIGURATION - SINGLE SOURCE OF TRUTH
# =============================================================================
# Version: 1.0.0
#
# This file defines ALL configuration for AutoBot.
# All other configuration files derive from these values.
#
# Naming Convention: AUTOBOT_{CATEGORY}_{NAME}
# Categories: NETWORK, VM, LLM, REDIS, TIMEOUT, PATH, UI, FEATURE, SECURITY
# =============================================================================

# -----------------------------------------------------------------------------
# NETWORK INFRASTRUCTURE (6-VM Architecture)
# -----------------------------------------------------------------------------

# Main Machine (WSL) - Backend API + VNC Desktop
AUTOBOT_VM_MAIN_IP=172.16.168.20

# VM1 Frontend - Web interface (SINGLE FRONTEND SERVER)
AUTOBOT_VM_FRONTEND_IP=172.16.168.21

# VM2 NPU Worker - Hardware AI acceleration
AUTOBOT_VM_NPU_IP=172.16.168.22

# VM3 Redis - Data layer
AUTOBOT_VM_REDIS_IP=172.16.168.23

# VM4 AI Stack - AI processing
AUTOBOT_VM_AISTACK_IP=172.16.168.24

# VM5 Browser - Web automation (Playwright)
AUTOBOT_VM_BROWSER_IP=172.16.168.25

# -----------------------------------------------------------------------------
# SERVICE PORTS
# -----------------------------------------------------------------------------
AUTOBOT_PORT_BACKEND=8001
AUTOBOT_PORT_FRONTEND=5173
AUTOBOT_PORT_REDIS=6379
AUTOBOT_PORT_OLLAMA=11434
AUTOBOT_PORT_VNC=6080
AUTOBOT_PORT_BROWSER=3000
AUTOBOT_PORT_AISTACK=8080
AUTOBOT_PORT_NPU=8081
AUTOBOT_PORT_NPU_WINDOWS=8082
AUTOBOT_PORT_PROMETHEUS=9090
AUTOBOT_PORT_GRAFANA=3000

# -----------------------------------------------------------------------------
# LLM CONFIGURATION
# -----------------------------------------------------------------------------
AUTOBOT_LLM_DEFAULT_MODEL=mistral:7b-instruct
AUTOBOT_LLM_EMBEDDING_MODEL=nomic-embed-text:latest
AUTOBOT_LLM_CLASSIFICATION_MODEL=gemma2:2b
AUTOBOT_LLM_PROVIDER=ollama
AUTOBOT_LLM_TIMEOUT=120

# Optional cloud providers
AUTOBOT_LLM_OPENAI_KEY=
AUTOBOT_LLM_OPENAI_MODEL=gpt-4
AUTOBOT_LLM_ANTHROPIC_KEY=
AUTOBOT_LLM_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# -----------------------------------------------------------------------------
# REDIS CONFIGURATION
# -----------------------------------------------------------------------------
AUTOBOT_REDIS_PASSWORD=
AUTOBOT_REDIS_DB_MAIN=0
AUTOBOT_REDIS_DB_KNOWLEDGE=1
AUTOBOT_REDIS_DB_CACHE=2
AUTOBOT_REDIS_DB_SESSIONS=3
AUTOBOT_REDIS_DB_METRICS=4
AUTOBOT_REDIS_DB_VECTORS=8

# -----------------------------------------------------------------------------
# TIMEOUTS (in seconds)
# -----------------------------------------------------------------------------
AUTOBOT_TIMEOUT_HTTP=30
AUTOBOT_TIMEOUT_HTTP_LONG=120
AUTOBOT_TIMEOUT_WEBSOCKET=300
AUTOBOT_TIMEOUT_REDIS_CONNECT=2
AUTOBOT_TIMEOUT_REDIS_OP=1
AUTOBOT_TIMEOUT_LLM_DEFAULT=120
AUTOBOT_TIMEOUT_LLM_REASONING=300
AUTOBOT_TIMEOUT_HEALTH_CHECK=3

# -----------------------------------------------------------------------------
# DEPLOYMENT MODE
# -----------------------------------------------------------------------------
AUTOBOT_DEPLOYMENT_MODE=distributed
AUTOBOT_ENVIRONMENT=development
AUTOBOT_DEBUG=false

# -----------------------------------------------------------------------------
# FEATURE FLAGS
# -----------------------------------------------------------------------------
AUTOBOT_FEATURE_WEBSOCKETS=true
AUTOBOT_FEATURE_VNC=true
AUTOBOT_FEATURE_NPU=true
AUTOBOT_FEATURE_DEBUG=false

# -----------------------------------------------------------------------------
# SECURITY
# -----------------------------------------------------------------------------
AUTOBOT_SECURITY_AUTH_ENABLED=false
AUTOBOT_SECURITY_SESSION_TIMEOUT=30
AUTOBOT_SECURITY_ENCRYPTION=false
```

### 3.3 Python Loader Implementation

```python
# src/config/ssot_config.py
"""
SSOT Configuration Loader for Python
Single source of truth - reads from .env
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class VMConfig(BaseSettings):
    """VM IP addresses"""
    main: str = Field(alias="AUTOBOT_VM_MAIN_IP", default="172.16.168.20")
    frontend: str = Field(alias="AUTOBOT_VM_FRONTEND_IP", default="172.16.168.21")
    npu: str = Field(alias="AUTOBOT_VM_NPU_IP", default="172.16.168.22")
    redis: str = Field(alias="AUTOBOT_VM_REDIS_IP", default="172.16.168.23")
    aistack: str = Field(alias="AUTOBOT_VM_AISTACK_IP", default="172.16.168.24")
    browser: str = Field(alias="AUTOBOT_VM_BROWSER_IP", default="172.16.168.25")


class PortConfig(BaseSettings):
    """Service ports"""
    backend: int = Field(alias="AUTOBOT_PORT_BACKEND", default=8001)
    frontend: int = Field(alias="AUTOBOT_PORT_FRONTEND", default=5173)
    redis: int = Field(alias="AUTOBOT_PORT_REDIS", default=6379)
    ollama: int = Field(alias="AUTOBOT_PORT_OLLAMA", default=11434)
    vnc: int = Field(alias="AUTOBOT_PORT_VNC", default=6080)
    browser: int = Field(alias="AUTOBOT_PORT_BROWSER", default=3000)
    aistack: int = Field(alias="AUTOBOT_PORT_AISTACK", default=8080)
    npu: int = Field(alias="AUTOBOT_PORT_NPU", default=8081)


class LLMConfig(BaseSettings):
    """LLM configuration"""
    default_model: str = Field(alias="AUTOBOT_LLM_DEFAULT_MODEL", default="mistral:7b-instruct")
    embedding_model: str = Field(alias="AUTOBOT_LLM_EMBEDDING_MODEL", default="nomic-embed-text:latest")
    provider: str = Field(alias="AUTOBOT_LLM_PROVIDER", default="ollama")
    timeout: int = Field(alias="AUTOBOT_LLM_TIMEOUT", default=120)


class TimeoutConfig(BaseSettings):
    """Timeout configuration"""
    http: int = Field(alias="AUTOBOT_TIMEOUT_HTTP", default=30)
    http_long: int = Field(alias="AUTOBOT_TIMEOUT_HTTP_LONG", default=120)
    websocket: int = Field(alias="AUTOBOT_TIMEOUT_WEBSOCKET", default=300)
    redis_connect: float = Field(alias="AUTOBOT_TIMEOUT_REDIS_CONNECT", default=2.0)
    redis_op: float = Field(alias="AUTOBOT_TIMEOUT_REDIS_OP", default=1.0)
    llm_default: int = Field(alias="AUTOBOT_TIMEOUT_LLM_DEFAULT", default=120)


class FeatureConfig(BaseSettings):
    """Feature flags"""
    websockets: bool = Field(alias="AUTOBOT_FEATURE_WEBSOCKETS", default=True)
    vnc: bool = Field(alias="AUTOBOT_FEATURE_VNC", default=True)
    npu: bool = Field(alias="AUTOBOT_FEATURE_NPU", default=True)
    debug: bool = Field(alias="AUTOBOT_FEATURE_DEBUG", default=False)


class AutoBotConfig(BaseSettings):
    """Master configuration - SINGLE SOURCE OF TRUTH"""

    vm: VMConfig = Field(default_factory=VMConfig)
    port: PortConfig = Field(default_factory=PortConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)
    feature: FeatureConfig = Field(default_factory=FeatureConfig)

    deployment_mode: str = Field(alias="AUTOBOT_DEPLOYMENT_MODE", default="distributed")
    environment: str = Field(alias="AUTOBOT_ENVIRONMENT", default="development")
    debug: bool = Field(alias="AUTOBOT_DEBUG", default=False)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    # Computed properties for backward compatibility
    @property
    def backend_url(self) -> str:
        return f"http://{self.vm.main}:{self.port.backend}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.vm.redis}:{self.port.redis}"

    @property
    def ollama_url(self) -> str:
        return f"http://{self.vm.aistack}:{self.port.ollama}"


@lru_cache()
def get_config() -> AutoBotConfig:
    """Get singleton configuration instance"""
    return AutoBotConfig()


# Convenience exports for backward compatibility
config = get_config()
```

### 3.4 TypeScript Loader Implementation

```typescript
// autobot-vue/src/config/ssot-config.ts
/**
 * SSOT Configuration Loader for TypeScript
 * Single source of truth - reads from Vite environment
 */

interface VMConfig {
  main: string;
  frontend: string;
  npu: string;
  redis: string;
  aistack: string;
  browser: string;
}

interface PortConfig {
  backend: number;
  frontend: number;
  redis: number;
  ollama: number;
  vnc: number;
  browser: number;
  aistack: number;
  npu: number;
}

interface LLMConfig {
  defaultModel: string;
  embeddingModel: string;
  provider: string;
  timeout: number;
}

interface TimeoutConfig {
  http: number;
  httpLong: number;
  websocket: number;
  redisConnect: number;
  redisOp: number;
  llmDefault: number;
}

interface FeatureConfig {
  websockets: boolean;
  vnc: boolean;
  npu: boolean;
  debug: boolean;
}

export interface AutoBotConfig {
  vm: VMConfig;
  port: PortConfig;
  llm: LLMConfig;
  timeout: TimeoutConfig;
  feature: FeatureConfig;
  deploymentMode: string;
  environment: string;
  debug: boolean;

  // Computed URLs
  backendUrl: string;
  redisUrl: string;
  ollamaUrl: string;
  websocketUrl: string;
}

// Environment variable helper
function getEnv(key: string, defaultValue: string): string {
  return import.meta.env[key] ?? defaultValue;
}

function getEnvNumber(key: string, defaultValue: number): number {
  const value = import.meta.env[key];
  return value ? parseInt(value, 10) : defaultValue;
}

function getEnvBoolean(key: string, defaultValue: boolean): boolean {
  const value = import.meta.env[key];
  if (value === undefined) return defaultValue;
  return value === 'true' || value === '1';
}

// Singleton configuration
let _config: AutoBotConfig | null = null;

export function getConfig(): AutoBotConfig {
  if (_config) return _config;

  const vm: VMConfig = {
    main: getEnv('VITE_VM_MAIN_IP', '172.16.168.20'),
    frontend: getEnv('VITE_VM_FRONTEND_IP', '172.16.168.21'),
    npu: getEnv('VITE_VM_NPU_IP', '172.16.168.22'),
    redis: getEnv('VITE_VM_REDIS_IP', '172.16.168.23'),
    aistack: getEnv('VITE_VM_AISTACK_IP', '172.16.168.24'),
    browser: getEnv('VITE_VM_BROWSER_IP', '172.16.168.25'),
  };

  const port: PortConfig = {
    backend: getEnvNumber('VITE_PORT_BACKEND', 8001),
    frontend: getEnvNumber('VITE_PORT_FRONTEND', 5173),
    redis: getEnvNumber('VITE_PORT_REDIS', 6379),
    ollama: getEnvNumber('VITE_PORT_OLLAMA', 11434),
    vnc: getEnvNumber('VITE_PORT_VNC', 6080),
    browser: getEnvNumber('VITE_PORT_BROWSER', 3000),
    aistack: getEnvNumber('VITE_PORT_AISTACK', 8080),
    npu: getEnvNumber('VITE_PORT_NPU', 8081),
  };

  const llm: LLMConfig = {
    defaultModel: getEnv('VITE_LLM_DEFAULT_MODEL', 'mistral:7b-instruct'),
    embeddingModel: getEnv('VITE_LLM_EMBEDDING_MODEL', 'nomic-embed-text:latest'),
    provider: getEnv('VITE_LLM_PROVIDER', 'ollama'),
    timeout: getEnvNumber('VITE_LLM_TIMEOUT', 120),
  };

  const timeout: TimeoutConfig = {
    http: getEnvNumber('VITE_TIMEOUT_HTTP', 30000),
    httpLong: getEnvNumber('VITE_TIMEOUT_HTTP_LONG', 120000),
    websocket: getEnvNumber('VITE_TIMEOUT_WEBSOCKET', 300000),
    redisConnect: getEnvNumber('VITE_TIMEOUT_REDIS_CONNECT', 2000),
    redisOp: getEnvNumber('VITE_TIMEOUT_REDIS_OP', 1000),
    llmDefault: getEnvNumber('VITE_TIMEOUT_LLM_DEFAULT', 120000),
  };

  const feature: FeatureConfig = {
    websockets: getEnvBoolean('VITE_FEATURE_WEBSOCKETS', true),
    vnc: getEnvBoolean('VITE_FEATURE_VNC', true),
    npu: getEnvBoolean('VITE_FEATURE_NPU', true),
    debug: getEnvBoolean('VITE_FEATURE_DEBUG', false),
  };

  _config = {
    vm,
    port,
    llm,
    timeout,
    feature,
    deploymentMode: getEnv('VITE_DEPLOYMENT_MODE', 'distributed'),
    environment: getEnv('VITE_ENVIRONMENT', 'development'),
    debug: getEnvBoolean('VITE_DEBUG', false),

    // Computed URLs
    get backendUrl() { return `http://${vm.main}:${port.backend}`; },
    get redisUrl() { return `redis://${vm.redis}:${port.redis}`; },
    get ollamaUrl() { return `http://${vm.aistack}:${port.ollama}`; },
    get websocketUrl() { return `ws://${vm.main}:${port.backend}/ws`; },
  };

  return _config;
}

// Default export for convenience
export default getConfig();
```

### 3.5 Environment File Synchronization

Create a shared `.env` generation script:

```bash
#!/bin/bash
# scripts/sync-env.sh
# Generates both backend and frontend .env files from master

MASTER_ENV=".env"
FRONTEND_ENV="autobot-vue/.env"

if [[ ! -f "$MASTER_ENV" ]]; then
    echo "Error: Master .env not found. Copy from .env.example"
    exit 1
fi

# Generate frontend .env with VITE_ prefixes
echo "# AUTO-GENERATED from $MASTER_ENV - DO NOT EDIT DIRECTLY" > "$FRONTEND_ENV"
echo "# Run: ./scripts/sync-env.sh to regenerate" >> "$FRONTEND_ENV"
echo "" >> "$FRONTEND_ENV"

# Map AUTOBOT_ variables to VITE_ variables
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    # Convert AUTOBOT_VM_ to VITE_VM_
    if [[ "$key" == AUTOBOT_VM_* ]]; then
        new_key="${key/AUTOBOT_/VITE_}"
        echo "$new_key=$value" >> "$FRONTEND_ENV"
    # Convert AUTOBOT_PORT_ to VITE_PORT_
    elif [[ "$key" == AUTOBOT_PORT_* ]]; then
        new_key="${key/AUTOBOT_/VITE_}"
        echo "$new_key=$value" >> "$FRONTEND_ENV"
    # Convert AUTOBOT_LLM_ to VITE_LLM_
    elif [[ "$key" == AUTOBOT_LLM_* ]]; then
        new_key="${key/AUTOBOT_/VITE_}"
        echo "$new_key=$value" >> "$FRONTEND_ENV"
    # Convert AUTOBOT_TIMEOUT_ to VITE_TIMEOUT_
    elif [[ "$key" == AUTOBOT_TIMEOUT_* ]]; then
        new_key="${key/AUTOBOT_/VITE_}"
        echo "$new_key=$value" >> "$FRONTEND_ENV"
    # Convert AUTOBOT_FEATURE_ to VITE_FEATURE_
    elif [[ "$key" == AUTOBOT_FEATURE_* ]]; then
        new_key="${key/AUTOBOT_/VITE_}"
        echo "$new_key=$value" >> "$FRONTEND_ENV"
    # Convert deployment mode
    elif [[ "$key" == "AUTOBOT_DEPLOYMENT_MODE" ]]; then
        echo "VITE_DEPLOYMENT_MODE=$value" >> "$FRONTEND_ENV"
    elif [[ "$key" == "AUTOBOT_ENVIRONMENT" ]]; then
        echo "VITE_ENVIRONMENT=$value" >> "$FRONTEND_ENV"
    elif [[ "$key" == "AUTOBOT_DEBUG" ]]; then
        echo "VITE_DEBUG=$value" >> "$FRONTEND_ENV"
    fi
done < "$MASTER_ENV"

echo "Frontend .env synchronized from master .env"
```

### 3.6 Shell Script Usage Pattern

Shell scripts in `scripts/` must also consume configuration from the SSOT `.env` file:

```bash
#!/bin/bash
# scripts/example-script.sh
# Example of SSOT-compliant shell script

# Load configuration from master .env
set -a  # Automatically export all variables
source "$(dirname "$0")/../.env"
set +a

# Now use AUTOBOT_ prefixed variables
echo "Backend URL: http://${AUTOBOT_VM_MAIN_IP}:${AUTOBOT_PORT_BACKEND}"
echo "Redis URL: redis://${AUTOBOT_VM_REDIS_IP}:${AUTOBOT_PORT_REDIS}"
echo "Default LLM: ${AUTOBOT_LLM_DEFAULT_MODEL}"

# Example: Health check using SSOT config
curl -s "http://${AUTOBOT_VM_MAIN_IP}:${AUTOBOT_PORT_BACKEND}/api/health"
```

**Shell Script Standards**:

1. **Always source `.env`** at script start
2. **Never hardcode** IPs, ports, or model names
3. **Use AUTOBOT_ prefix** for all configuration variables
4. **Provide fallbacks** only for non-critical scripts (testing/development)

**Scripts Requiring Migration**:

| Script | Current Status | Required Changes |
| ------ | -------------- | ---------------- |
| `run_autobot.sh` | Partial SSOT | Source .env, remove hardcoded IPs |
| `setup.sh` | Hardcoded | Source .env for all network config |
| `scripts/utilities/sync-to-vm.sh` | Hardcoded IPs | Use AUTOBOT_VM_* variables |
| `scripts/utilities/sync-frontend.sh` | Hardcoded | Use AUTOBOT_VM_FRONTEND_IP |

### 3.7 Documentation Requirements

All configuration-related documentation must be updated during SSOT migration:

**Documents to Update**:

| Document | Update Required |
| -------- | --------------- |
| `CLAUDE.md` | Update Redis/Network sections to reference SSOT |
| `docs/developer/HARDCODING_PREVENTION.md` | Add SSOT config pattern as canonical |
| `docs/developer/REDIS_CLIENT_USAGE.md` | Reference SSOT for connection strings |
| `docs/developer/INFRASTRUCTURE_DEPLOYMENT.md` | Update VM IP references |
| `.env.example` | Complete rewrite with SSOT structure |
| `autobot-vue/.env.example` | Auto-generated from master |
| `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md` | Add /api/config endpoints |

**New Documentation Required**:

1. **`docs/developer/SSOT_CONFIG_GUIDE.md`** - Developer guide for using SSOT config
2. **`docs/developer/CONFIG_MIGRATION_CHECKLIST.md`** - Checklist for migrating existing code

---

## 4. Implementation Strategy

### 4.1 Phase 1: Foundation (Week 1-2)

**Objective**: Create new SSOT infrastructure without breaking existing code.

**Tasks**:
1. Create `src/config/ssot_config.py` with Pydantic models
2. Create `autobot-vue/src/config/ssot-config.ts` with TypeScript types
3. Create `scripts/sync-env.sh` for environment synchronization
4. Update `.env.example` with new canonical structure
5. Add validation tests for both loaders

**Files to Create**:
- `/home/kali/Desktop/AutoBot/src/config/ssot_config.py`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/config/ssot-config.ts`
- `/home/kali/Desktop/AutoBot/scripts/sync-env.sh`

**Backward Compatibility**: Old config modules remain functional.

### 4.2 Phase 2: Backend Migration (Week 3-4)

**Objective**: Migrate Python code to use new SSOT config.

**Tasks**:
1. Update `network_constants.py` to read from SSOT config
2. Update `model_constants.py` to read from SSOT config
3. Update `UnifiedConfigManager` to use SSOT as base
4. Migrate `config_service.py` to wrap SSOT
5. Add deprecation warnings to old accessors

**Migration Pattern**:
```python
# Before
from src.constants.network_constants import NetworkConstants
host = NetworkConstants.REDIS_VM_IP

# After
from src.config.ssot_config import config
host = config.vm.redis
```

### 4.3 Phase 3: Frontend Migration (Week 5-6)

**Objective**: Migrate TypeScript/Vue code to use new SSOT config.

**Tasks**:
1. Update `defaults.js` to import from `ssot-config.ts`
2. Update `network.ts` to use SSOT config
3. Update `ServiceDiscovery.js` to use SSOT config
4. Update `vite.config.ts` to use SSOT config
5. Remove hardcoded fallbacks

**Migration Pattern**:
```typescript
// Before
import { DEFAULT_CONFIG } from './defaults.js';
const host = DEFAULT_CONFIG.network.backend.host;

// After
import { config } from './ssot-config';
const host = config.vm.main;
```

### 4.4 Phase 4: Cleanup (Week 7-8)

**Objective**: Remove deprecated code and finalize architecture.

**Tasks**:
1. Remove deprecated config modules
2. Consolidate `config.yaml` to user preferences only
3. Update all documentation
4. Add pre-commit validation for hardcoded values
5. Create migration guide

**Files to Deprecate**:
- `autobot-vue/src/config/defaults.js` (merge into ssot-config.ts)
- `vite.config.ts` NETWORK_DEFAULTS block

---

## 5. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Breaking existing code during migration | High | Medium | Phased migration with backward compatibility shims |
| Frontend build fails if .env missing | High | Low | Fallback defaults in TypeScript loader |
| Environment variable sprawl | Medium | Medium | Clear naming convention, documentation |
| Secret exposure in .env | High | Low | Separate `.env.secrets` for sensitive values |
| VM IP changes break config | Medium | Medium | Service discovery for production |

---

## 6. Success Metrics

1. **File Count**: Reduce from 19+ config files to 5 canonical files
2. **Hardcoded Values**: Zero hardcoded IPs/ports in business logic
3. **Cross-Language Consistency**: 100% parity between Python and TypeScript config
4. **Hot Reload**: Single file change triggers config update
5. **Onboarding Time**: New developer can understand config in < 30 minutes
6. **Test Coverage**: 90%+ coverage on config loaders

---

## 7. Appendix: File Structure After Implementation

```
/home/kali/Desktop/AutoBot/
├── .env                                    # MASTER CONFIG - SINGLE SOURCE OF TRUTH
├── .env.example                            # Template with all values documented
├── .env.secrets.example                    # Template for secrets (gitignored)
│
├── config/
│   ├── user-preferences.yaml              # Mutable user settings (theme, etc.)
│   └── config.yaml                         # DEPRECATED - redirect to .env
│
├── src/config/
│   ├── ssot_config.py                      # NEW: Python SSOT loader
│   ├── manager.py                          # UPDATED: Uses SSOT as base
│   ├── compat.py                           # UPDATED: Backward compatibility shims
│   └── ... (other modules - thin wrappers)
│
├── src/constants/
│   ├── network_constants.py                # UPDATED: Reads from SSOT config
│   ├── model_constants.py                  # UPDATED: Reads from SSOT config
│   └── ... (other constants - derive from SSOT)
│
├── autobot-vue/
│   ├── .env                                # AUTO-GENERATED from master .env
│   └── src/config/
│       ├── ssot-config.ts                  # NEW: TypeScript SSOT loader
│       ├── defaults.js                     # DEPRECATED - redirect to ssot-config
│       └── ServiceDiscovery.js             # UPDATED: Uses SSOT config
│
└── scripts/
    └── sync-env.sh                         # NEW: Syncs .env to frontend
```

---

## 8. Conclusion

The Environment-Centric approach (Approach C) provides the optimal balance of simplicity, maintainability, and compatibility for AutoBot's configuration needs. By establishing `.env` as the single source of truth with typed loaders in both Python and TypeScript, we eliminate the current fragmentation while maintaining type safety and environment awareness.

The phased implementation strategy ensures zero disruption to the running system while progressively consolidating configuration management. The 8-week timeline allows for thorough testing and validation at each phase.

---

**Document Status**: Ready for Review
**Next Steps**: Create GitHub issue for Phase 1 implementation
