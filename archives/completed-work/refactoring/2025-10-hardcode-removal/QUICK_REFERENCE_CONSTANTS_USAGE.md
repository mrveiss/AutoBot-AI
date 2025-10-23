# Quick Reference: Using Constants in AutoBot

**Purpose**: Replace hardcoded IPs, ports, and paths with centralized constants
**Status**: Ready for implementation

---

## Python: Network Constants

### Import
```python
from src.constants.network_constants import NetworkConstants, ServiceURLs, DatabaseConstants
```

### VM IP Addresses
```python
# BEFORE (DON'T DO THIS):
redis_host = "172.16.168.23"
backend_host = "172.16.168.20"

# AFTER (CORRECT):
redis_host = NetworkConstants.REDIS_VM_IP
backend_host = NetworkConstants.MAIN_MACHINE_IP
```

### Service Ports
```python
# BEFORE:
redis_port = 6379
backend_port = 8001

# AFTER:
redis_port = NetworkConstants.REDIS_PORT
backend_port = NetworkConstants.BACKEND_PORT
```

### Complete Service URLs
```python
# BEFORE:
backend_url = "http://172.16.168.20:8001"
redis_url = "redis://172.16.168.23:6379"

# AFTER:
backend_url = ServiceURLs.BACKEND_API
redis_url = ServiceURLs.REDIS_VM
```

### Redis Database Numbers
```python
# BEFORE:
redis_db = 0  # What's this for?
vector_db = 8  # Why 8?

# AFTER:
redis_db = DatabaseConstants.MAIN_DB
vector_db = DatabaseConstants.VECTORS_DB
```

### Available Constants

**VM IPs**:
- `NetworkConstants.MAIN_MACHINE_IP` - 172.16.168.20
- `NetworkConstants.FRONTEND_VM_IP` - 172.16.168.21
- `NetworkConstants.NPU_WORKER_VM_IP` - 172.16.168.22
- `NetworkConstants.REDIS_VM_IP` - 172.16.168.23
- `NetworkConstants.AI_STACK_VM_IP` - 172.16.168.24
- `NetworkConstants.BROWSER_VM_IP` - 172.16.168.25

**Ports**:
- `NetworkConstants.BACKEND_PORT` - 8001
- `NetworkConstants.FRONTEND_PORT` - 5173
- `NetworkConstants.REDIS_PORT` - 6379
- `NetworkConstants.OLLAMA_PORT` - 11434
- `NetworkConstants.VNC_PORT` - 6080
- `NetworkConstants.NPU_WORKER_PORT` - 8081
- `NetworkConstants.AI_STACK_PORT` - 8080
- `NetworkConstants.BROWSER_SERVICE_PORT` - 3000

**Service URLs**:
- `ServiceURLs.BACKEND_API`
- `ServiceURLs.FRONTEND_VM`
- `ServiceURLs.REDIS_VM`
- `ServiceURLs.OLLAMA_LOCAL`
- `ServiceURLs.VNC_DESKTOP`
- `ServiceURLs.BROWSER_SERVICE`
- `ServiceURLs.AI_STACK_SERVICE`
- `ServiceURLs.NPU_WORKER_SERVICE`

---

## Python: Path Constants

### Import
```python
from src.constants.path_constants import PathConstants
```

### Project Paths
```python
# BEFORE (DON'T DO THIS):
project_root = "/home/kali/Desktop/AutoBot"
data_dir = "/home/kali/Desktop/AutoBot/data"
logs_dir = "/home/kali/Desktop/AutoBot/logs"

# AFTER (CORRECT):
project_root = PathConstants.PROJECT_ROOT
data_dir = PathConstants.DATA_DIR
logs_dir = PathConstants.LOGS_DIR
```

### Building Paths
```python
# BEFORE:
log_file = "/home/kali/Desktop/AutoBot/logs/backend.log"
config_file = "/home/kali/Desktop/AutoBot/config/settings.yaml"

# AFTER:
log_file = PathConstants.LOGS_DIR / "backend.log"
config_file = PathConstants.CONFIG_DIR / "settings.yaml"
```

### Available Path Constants

**Core Directories**:
- `PathConstants.PROJECT_ROOT` - Auto-detected project root
- `PathConstants.SRC_DIR` - src/
- `PathConstants.BACKEND_DIR` - backend/
- `PathConstants.FRONTEND_DIR` - autobot-vue/

**Data Directories**:
- `PathConstants.DATA_DIR` - data/
- `PathConstants.LOGS_DIR` - logs/
- `PathConstants.TEMP_DIR` - temp/

**Configuration**:
- `PathConstants.CONFIG_DIR` - config/
- `PathConstants.SECURITY_CONFIG_DIR` - config/security/

**Security**:
- `PathConstants.SECURITY_DIR` - data/security/
- `PathConstants.AUDIT_LOGS_DIR` - logs/audit/

**Database**:
- `PathConstants.DATABASE_DIR` - database/
- `PathConstants.MIGRATIONS_DIR` - database/migrations/

**Tests**:
- `PathConstants.TESTS_DIR` - tests/
- `PathConstants.TEST_RESULTS_DIR` - tests/results/

**User Paths**:
- `PathConstants.USER_HOME` - User's home directory
- `PathConstants.SSH_DIR` - ~/.ssh/
- `PathConstants.AUTOBOT_CONFIG_DIR` - ~/.autobot/

---

## TypeScript: Network Constants

### Import (MCP Tools)
```typescript
import { NetworkConstants, ServiceURLs } from './constants/network';
```

### Service URLs
```typescript
// BEFORE:
const frontendUrl = 'http://172.16.168.21:5173/health';
const redisUrl = 'redis://172.16.168.23:6379';

// AFTER:
const frontendUrl = `${ServiceURLs.frontend()}/health`;
const redisUrl = ServiceURLs.redis();
```

### Building Custom URLs
```typescript
// BEFORE:
const customUrl = `http://172.16.168.20:8001/api/endpoint`;

// AFTER:
const customUrl = `${ServiceURLs.backend()}/api/endpoint`;
```

### Available TypeScript Constants

**ServiceURLs Functions** (call them):
- `ServiceURLs.backend()` - http://172.16.168.20:8001
- `ServiceURLs.frontend()` - http://172.16.168.21:5173
- `ServiceURLs.redis()` - redis://172.16.168.23:6379
- `ServiceURLs.npuWorker()` - http://172.16.168.22:8081
- `ServiceURLs.aiStack()` - http://172.16.168.24:8080
- `ServiceURLs.browser()` - http://172.16.168.25:3000

**NetworkConstants** (direct access):
- `NetworkConstants.MAIN_MACHINE_IP`
- `NetworkConstants.FRONTEND_VM_IP`
- `NetworkConstants.REDIS_VM_IP`
- etc.

---

## TypeScript: Path Constants

### Import (MCP Tools)
```typescript
import { PathConstants } from './constants/paths';
```

### File Paths
```typescript
// BEFORE:
const backendLog = '/home/kali/Desktop/AutoBot/data/logs/backend.log';
const dataDir = '/home/kali/Desktop/AutoBot/data';

// AFTER:
const backendLog = PathConstants.BACKEND_LOG;
const dataDir = PathConstants.DATA_DIR;
```

### Building Paths
```typescript
import * as path from 'path';

// BEFORE:
const customFile = '/home/kali/Desktop/AutoBot/data/custom.json';

// AFTER:
const customFile = path.join(PathConstants.DATA_DIR, 'custom.json');
```

### Available TypeScript Path Constants

**Specific Log Files**:
- `PathConstants.BACKEND_LOG`
- `PathConstants.FRONTEND_LOG`
- `PathConstants.REDIS_LOG`
- `PathConstants.CHAT_LOG`

**Data Directories**:
- `PathConstants.DATA_DIR`
- `PathConstants.LOGS_DIR`
- `PathConstants.CONVERSATIONS_DIR`
- `PathConstants.CHAT_HISTORY_DIR`

**User Paths**:
- `PathConstants.USER_HOME`
- `PathConstants.SSH_DIR`

---

## JavaScript/Vue: Frontend Config

### Import (Frontend Components)
```javascript
import appConfig from '@/config/app';
import { DEFAULT_CONFIG } from '@/config/defaults';
```

### Service URLs
```javascript
// BEFORE:
const backendUrl = 'http://172.16.168.20:8001';

// AFTER:
const backendUrl = await appConfig.getServiceUrl('backend');
```

### Available Services
```javascript
const backendUrl = await appConfig.getServiceUrl('backend');
const frontendUrl = await appConfig.getServiceUrl('frontend');
const redisUrl = await appConfig.getServiceUrl('redis');
const npuWorkerUrl = await appConfig.getServiceUrl('npu_worker');
const aiStackUrl = await appConfig.getServiceUrl('ai_stack');
const browserUrl = await appConfig.getServiceUrl('browser');
const ollamaUrl = await appConfig.getServiceUrl('ollama');
```

### Direct Access to Defaults
```javascript
const backendHost = DEFAULT_CONFIG.network.backend.host;
const backendPort = DEFAULT_CONFIG.network.backend.port;
```

---

## Common Patterns

### Redis Connection (Python)
```python
from redis import Redis
from src.constants.network_constants import NetworkConstants, DatabaseConstants

redis_client = Redis(
    host=NetworkConstants.REDIS_VM_IP,
    port=NetworkConstants.REDIS_PORT,
    db=DatabaseConstants.MAIN_DB
)
```

### HTTP Request (Python)
```python
import requests
from src.constants.network_constants import ServiceURLs

response = requests.get(f"{ServiceURLs.BACKEND_API}/api/health")
```

### File Operations (Python)
```python
from src.constants.path_constants import PathConstants

log_file = PathConstants.LOGS_DIR / "application.log"
with open(log_file, 'a') as f:
    f.write("Log entry\n")
```

### Service Health Check (TypeScript)
```typescript
import { ServiceURLs } from './constants/network';

const services = [
  { name: 'frontend', url: `${ServiceURLs.frontend()}/health` },
  { name: 'backend', url: `${ServiceURLs.backend()}/api/health` },
  { name: 'redis', url: ServiceURLs.redis(), type: 'redis' },
];
```

### Redis Connection (TypeScript)
```typescript
import { createClient } from 'redis';
import { NetworkConstants } from './constants/network';

const redisClient = createClient({
  socket: {
    host: NetworkConstants.REDIS_VM_IP,
    port: NetworkConstants.REDIS_PORT,
  }
});
```

---

## Function Signatures

### Before (with hardcoded defaults)
```python
def connect_redis(host: str = "172.16.168.23", port: int = 6379):
    pass

def get_log_path(base: str = "/home/kali/Desktop/AutoBot/logs"):
    pass
```

### After (with constant defaults)
```python
from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PathConstants

def connect_redis(
    host: str = NetworkConstants.REDIS_VM_IP,
    port: int = NetworkConstants.REDIS_PORT
):
    pass

def get_log_path(base: Path = PathConstants.LOGS_DIR):
    pass
```

---

## Environment Variables (Optional Override)

### Python
```python
import os
from src.constants.network_constants import NetworkConstants

# Constants provide defaults, but can be overridden by env vars
redis_host = os.getenv("REDIS_HOST", NetworkConstants.REDIS_VM_IP)
```

### TypeScript
```typescript
import { NetworkConstants } from './constants/network';

// Environment variable override
const redisHost = process.env.REDIS_HOST || NetworkConstants.REDIS_VM_IP;
```

---

## Anti-Patterns (DON'T DO THIS)

### ❌ Hardcoding IPs
```python
# WRONG
redis = Redis(host="172.16.168.23")

# CORRECT
from src.constants.network_constants import NetworkConstants
redis = Redis(host=NetworkConstants.REDIS_VM_IP)
```

### ❌ Hardcoding Paths
```python
# WRONG
log_file = "/home/kali/Desktop/AutoBot/logs/app.log"

# CORRECT
from src.constants.path_constants import PathConstants
log_file = PathConstants.LOGS_DIR / "app.log"
```

### ❌ Magic Numbers for Databases
```python
# WRONG
redis = Redis(host=redis_host, db=8)  # What is 8?

# CORRECT
from src.constants.network_constants import DatabaseConstants
redis = Redis(host=redis_host, db=DatabaseConstants.VECTORS_DB)
```

### ❌ String Concatenation for Paths
```python
# WRONG
config_path = "/home/kali/Desktop/AutoBot/config/" + "settings.yaml"

# CORRECT
from src.constants.path_constants import PathConstants
config_path = PathConstants.CONFIG_DIR / "settings.yaml"
```

---

## Testing Your Changes

### After Refactoring a File

1. **Import test** (Python):
   ```python
   python -c "from src.constants.network_constants import NetworkConstants; print(NetworkConstants.REDIS_VM_IP)"
   python -c "from src.constants.path_constants import PathConstants; print(PathConstants.PROJECT_ROOT)"
   ```

2. **Import test** (TypeScript):
   ```bash
   cd mcp-tools/mcp-autobot-tracker
   npm run build
   ```

3. **Functionality test**:
   - Run the service/endpoint that uses the refactored file
   - Verify connections work
   - Check logs for errors

### Validation Commands

```bash
# Check for remaining hardcoded IPs
grep -r "172.16.168\." --include="*.py" src/ backend/

# Check for remaining hardcoded paths
grep -r "/home/kali/Desktop/AutoBot" --include="*.py" src/ backend/

# Check TypeScript
grep -r "172.16.168\." --include="*.ts" mcp-tools/
```

---

## Quick Migration Checklist

When refactoring a file:

- [ ] Add imports for constants modules
- [ ] Replace hardcoded IPs with `NetworkConstants.X_VM_IP`
- [ ] Replace hardcoded ports with `NetworkConstants.X_PORT`
- [ ] Replace service URLs with `ServiceURLs.X`
- [ ] Replace paths with `PathConstants.X_DIR` or `PathConstants.PROJECT_ROOT / "path"`
- [ ] Replace Redis DB numbers with `DatabaseConstants.X_DB`
- [ ] Update docstrings/comments
- [ ] Test the changes
- [ ] Commit with descriptive message

---

## Need Help?

**Documentation**:
- Implementation Plan: `/home/kali/Desktop/AutoBot/reports/refactoring/HARDCODE_REMOVAL_IMPLEMENTATION_PLAN.md`
- Detailed Checklist: `/home/kali/Desktop/AutoBot/reports/refactoring/REFACTORING_CHECKLIST.md`

**Source Files**:
- Python Network: `src/constants/network_constants.py`
- Python Paths: `src/constants/path_constants.py` (to be created)
- TypeScript Network: `mcp-tools/mcp-autobot-tracker/src/constants/network.ts` (to be created)
- TypeScript Paths: `mcp-tools/mcp-autobot-tracker/src/constants/paths.ts` (to be created)
- Frontend Config: `autobot-vue/src/config/defaults.js`

---

**Last Updated**: 2025-10-21
**Status**: Ready for use after Phase 1 infrastructure creation
