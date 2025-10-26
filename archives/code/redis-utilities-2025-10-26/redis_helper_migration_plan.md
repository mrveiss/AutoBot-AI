# redis_helper.py Migration Plan

## Current Status

**File**: `src/utils/redis_helper.py` (188 lines)
**Usage**: **1 active file** (not 4 as initially counted)
**Purpose**: Timeout-focused Redis connection wrapper

## Active Dependencies

### 1. tests/integration/test_architecture_compliance.py
**Imports Used:**
```python
from src.utils.redis_helper import REDIS_HOST, REDIS_PORT
from src.utils.redis_helper import TIMEOUT_CONFIG
```

**Usage Pattern:**
- Test file validates Redis configuration
- Imports constants for validation, not actual Redis connections
- Can easily migrate to NetworkConstants and unified config

### Archived (Not Active):
- `archives/code/scripts/.../fix_critical_redis_timeouts.py` - Already archived script
- Self-references in redis_helper.py docstring

## Migration Strategy

### Option 1: Inline Constants (Recommended)
**For**: `test_architecture_compliance.py`

**Change:**
```python
# OLD (redis_helper):
from src.utils.redis_helper import REDIS_HOST, REDIS_PORT, TIMEOUT_CONFIG

# NEW (direct imports):
from src.constants.network_constants import NetworkConstants
from src.utils.redis_client import get_redis_client

REDIS_HOST = NetworkConstants.REDIS_VM_IP
REDIS_PORT = NetworkConstants.REDIS_PORT
```

**Benefits:**
- Direct imports from canonical sources
- No dependency on redis_helper
- Clearer intent

### Option 2: Leave for Now
Since it's only 1 test file and the imports are just constants, we could:
- Leave redis_helper.py as-is (188 lines is small)
- Mark it as "low priority for migration"
- Focus on the 67 direct instantiation files instead

## Recommendation

**Action**: **Option 2 - Leave for Now**

**Rationale:**
1. Only 1 file depends on it
2. That file is a test (low priority)
3. Imports are constants only (REDIS_HOST, REDIS_PORT, TIMEOUT_CONFIG)
4. Not causing actual duplication issues
5. Focus efforts on 67 direct instantiation files instead

**Future Work:**
- Migrate when touching test_architecture_compliance.py for other reasons
- Or migrate during "cleanup sprint" after Phase 4-5 complete

## Files to Migrate Before Deprecation

1. `tests/integration/test_architecture_compliance.py`
   - Complexity: LOW
   - Effort: 5 minutes
   - Impact: None (test file only)

## Post-Migration Actions

Once the 1 test file is migrated:
1. Move redis_helper.py to archives/code/redis-utilities-2025-10-26/
2. Update this migration plan with completion date
3. Update Memory MCP with status change

---

**Created**: 2025-10-26
**Status**: LOW PRIORITY - Only 1 test file affected
**Recommendation**: Focus on high-impact files first (67 direct instantiations)
