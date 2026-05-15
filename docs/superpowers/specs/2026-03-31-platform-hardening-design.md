# Platform Hardening: Architecture Adoptions

**Date:** 2026-03-31
**Status:** Approved
**Scope:** 6 architectural improvements inspired by analysis of modern CLI agent patterns

---

## Overview

Six targeted improvements to AutoBot's architecture, ordered by implementation priority:

| ID | Item | Effort | Impact | Priority |
|----|------|--------|--------|----------|
| A | Parallel startup init | Trivial | Medium | 1 |
| F | Lazy loading audit | Trivial | Low-Medium | 2 |
| C | Feature flags | Moderate | Medium | 3 |
| B | Unified Tool Registry with Pydantic schemas | Significant | High | 4 |
| D | Per-operation permission hooks | Moderate | High | 5 |
| E | Shared workflow memory | Moderate | Medium | 6 |

Items A and F are quick wins. C provides infrastructure that B and D build on. B provides the schema that D enforces. E is independent.

---

## A. Parallel Startup Init

**Goal:** Reduce Phase 1 cold-start time by running independent init steps concurrently.

**File:** `autobot-backend/initialization/lifespan.py`

**Current:** 9 sequential `await` calls in `initialize_critical_services()` (lines 352-369).

**Change:** Replace flat sequential list with 5 dependency tiers using `asyncio.gather()`:

```
Tier 0: _check_env_drift()                           — no deps
Tier 1: _init_config(app)                             — no deps
Tier 2: _init_security_layer(app)                     — needs config
         _init_database()                              — needs config
         _init_telemetry_and_redis()                   — needs config
Tier 3: _init_chat_history_manager(app)                — needs DB/Redis
         _init_conversation_file_manager(app)           — needs DB
         _init_chat_workflow_manager(app)               — needs Redis
Tier 4: _init_cache_coordinator()                      — needs managers
         _init_skills(app)                              — needs DB
```

Tiers 2, 3, and 4 each use `asyncio.gather()` to run their steps concurrently. Error handling unchanged — first exception propagates and aborts startup.

**Estimated startup improvement:** 30-50% reduction in Phase 1 time (Tier 2 alone saves ~2 steps worth of serial I/O).

---

## F. Lazy Loading Audit

**Goal:** Reduce memory footprint and import time by deferring heavy dependency imports.

**Targets (non-test files only):**

| Dependency | Files | Import time |
|------------|-------|-------------|
| `torch` | 12 files (ai_hardware_accelerator, training/*, multimodal_processor/*, api/multimodal, services/incremental_trainer, llm_interface_pkg/optimization/*) | ~2s |
| `chromadb` | 2 files (utils/chromadb_client, utils/async_chromadb_client) | ~0.5s |
| `PIL` | 4 files (ai_hardware_accelerator, computer_vision/screen_analyzer, multimodal_processor/processors/vision, services/captcha_solver) | ~0.3s |
| `cv2` | 1 file (computer_vision/screen_analyzer) | ~0.3s |

**Pattern:** Move heavy imports from module-level to function-level (inside `execute()`, `process()`, `__init__()` methods). Follow established codebase pattern from `routers/feedback.py` and `routers/code_completion.py`.

**Rules:**
- Only defer imports that are measurably heavy (torch, chromadb, PIL, cv2)
- Keep lightweight imports (stdlib, pydantic, logging) at top level
- Test files excluded (only run during test execution)
- Type annotations use `TYPE_CHECKING` guard

**Files affected:** ~19 non-test `.py` files. Each is a mechanical change.

---

## C. Feature Flags (Build-time + Runtime)

**Goal:** Gate optional subsystems so they can be disabled per-node without code changes.

### Backend

**File:** `autobot-shared/ssot_config.py`

Add `FeatureFlags` Pydantic model:

```python
class FeatureFlags(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTOBOT_FEATURE_")

    npu: bool = True
    voice: bool = True
    browser_automation: bool = True
    computer_vision: bool = False   # Heavy deps, off by default
    training: bool = False          # torch training, off by default
    graph_rag: bool = True
    mcp: bool = True
```

Accessed via `config.features.npu`, `config.features.voice`, etc.

**Usage pattern (replaces try/except ImportError):**

```python
from autobot_shared.ssot_config import config

if config.features.computer_vision:
    from computer_vision.screen_analyzer import ScreenAnalyzer
```

**Lifespan integration:** Phase 2 background services check flags before init:

```python
if config.features.npu:
    await _init_npu_worker_websocket()
    await _warmup_npu_connection()
```

### Frontend

**File:** `autobot-frontend/vite.config.ts`

Add compile-time constants:

```typescript
define: {
    __FEATURE_VOICE__: JSON.stringify(env.VITE_FEATURE_VOICE !== 'false'),
    __FEATURE_VNC__: JSON.stringify(env.VITE_FEATURE_VNC !== 'false'),
    __FEATURE_BROWSER__: JSON.stringify(env.VITE_FEATURE_BROWSER !== 'false'),
}
```

Vite tree-shakes dead branches at build time.

### .env additions

```env
AUTOBOT_FEATURE_NPU=true
AUTOBOT_FEATURE_VOICE=true
AUTOBOT_FEATURE_BROWSER_AUTOMATION=true
AUTOBOT_FEATURE_COMPUTER_VISION=false
AUTOBOT_FEATURE_TRAINING=false
AUTOBOT_FEATURE_GRAPH_RAG=true
AUTOBOT_FEATURE_MCP=true
```

---

## B. Unified Tool Registry with Pydantic Schemas

**Goal:** Provide a standardized tool contract with input validation, permission declaration, and auto-discovery.

### New package: `autobot-shared/tool_sdk/`

**`base.py` — Core abstractions:**

```python
class ToolPermission(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    OPERATOR = "operator"
    ADMIN = "admin"


class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class BaseTool(ABC):
    name: str
    description: str
    permission: ToolPermission = ToolPermission.AUTHENTICATED
    input_schema: Type[BaseModel]
    category: str = "general"

    @abstractmethod
    async def execute(self, params: BaseModel) -> ToolResult:
        ...
```

**`registry.py` — Singleton registry:**

```python
class ToolSDKRegistry:
    _instance = None
    _tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None: ...
    def get(self, name: str) -> Optional[BaseTool]: ...
    def list_tools(self, category: str = None) -> List[BaseTool]: ...
    def get_schemas(self) -> Dict[str, dict]: ...
    def discover(self, package: str) -> int: ...
```

### Integration

**`tools/tool_registry.py`:** Add `_try_sdk_dispatch()` at the top of `execute_tool()`. Check `ToolSDKRegistry` first; if tool found, validate input against `input_schema`, then call `execute()`. Fall back to existing dispatch table for unregistered tools.

**`chat_workflow/tool_handler.py`:** When dispatching a tool, look up its `BaseTool` instance and inject `tool_permission` and `user_role` into the `HookContext` data dict before invoking `BEFORE_TOOL_EXECUTE`.

### Migration path

- New tools written as `BaseTool` subclasses with full schemas
- Existing tools continue working through legacy dispatch table
- Incremental migration — no big-bang rewrite required

---

## D. Per-Operation Permission Hooks

**Goal:** Enforce tool-level permissions and authenticate WebSocket connections. Addresses issue #2818.

### Part 1: PermissionEnforcementExtension

**New file:** `autobot-backend/extensions/builtin/permission_enforcement.py`

```python
class PermissionEnforcementExtension(Extension):
    name = "permission_enforcement"
    version = "1.0.0"
    priority = 0  # Runs first

    async def on_before_tool_execute(self, ctx: HookContext) -> None:
        tool_permission = ctx.get("tool_permission")
        user_role = ctx.get("user_role")

        if tool_permission is None:
            return  # Legacy tool — allow (backward compat)

        if not _role_satisfies(user_role, tool_permission):
            raise PermissionError(
                f"Tool requires {tool_permission}, user has {user_role}"
            )
```

**Role mapping:**

| ToolPermission | Allowed Roles |
|----------------|---------------|
| PUBLIC | any (including unauthenticated) |
| AUTHENTICATED | USER, EDITOR, ANALYST, OPERATOR, ADMIN |
| OPERATOR | OPERATOR, ADMIN |
| ADMIN | ADMIN |

Single-user mode bypass applies (consistent with existing RBAC).

**Registration:** Auto-registered during lifespan Phase 1 after extension manager init.

### Part 2: WebSocket Authentication (#2818)

**Modified file:** `autobot-backend/auth_middleware.py`

Add `authenticate_websocket()`:

```python
async def authenticate_websocket(websocket: WebSocket) -> Optional[dict]:
    token = websocket.query_params.get("token")
    if token:
        return _extract_user_from_jwt_token(token)
    if _is_single_user_mode():
        return _synthetic_admin_user()
    return None
```

**Modified file:** `autobot-backend/api/websockets.py`

Applied before `websocket.accept()` on all WS endpoints:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user = await authenticate_websocket(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return
    await websocket.accept()
```

**Frontend WebSocket client:** The existing `GlobalWebSocketService` in the frontend must pass the JWT token as a query parameter when connecting:

```typescript
const wsUrl = `${baseWsUrl}/ws?token=${authStore.token}`
```

This is a one-line change in the WebSocket service initialization.

### Files affected

- New: `autobot-backend/extensions/builtin/permission_enforcement.py`
- Modified: `autobot-backend/auth_middleware.py`
- Modified: `autobot-backend/api/websockets.py`
- Modified: `autobot-backend/chat_workflow/tool_handler.py`
- Modified: `autobot-backend/initialization/lifespan.py`

---

## E. Shared Workflow Memory

**Goal:** Enable agents in the same workflow to share findings via a lightweight Redis-backed key-value store.

### New file: `autobot-shared/workflow_memory.py`

```python
class WorkflowMemory:
    """Shared KV memory for agents within a single workflow.

    Storage: Redis hash at autobot:workflow:{workflow_id}:memory
    TTL: 1 hour after last write (auto-expires stuck workflows)
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self._key = f"autobot:workflow:{workflow_id}:memory"

    async def write(self, key: str, value: str, agent_id: str = "") -> None:
        redis = await get_redis_client(async_client=True, database="main")
        await redis.hset(self._key, key, value)
        await redis.expire(self._key, 3600)

    async def read(self, key: str) -> Optional[str]:
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hget(self._key, key)

    async def read_all(self) -> Dict[str, str]:
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hgetall(self._key)

    async def clear(self) -> None:
        redis = await get_redis_client(async_client=True, database="main")
        await redis.delete(self._key)
```

### Integration

**`orchestration/workflow_executor.py`:** Create `WorkflowMemory` at workflow start, pass to each step's execution context, call `memory.clear()` on workflow completion.

**Key conventions:**
- Step-scoped: `{step_id}:result`, `{step_id}:findings`
- Workflow-global: `shared:entities_found`, `shared:decision_log`

### Files affected

- New: `autobot-shared/workflow_memory.py`
- Modified: `autobot-backend/orchestration/workflow_executor.py`

---

## Implementation Order

```
A  Parallel startup        ─── trivial, standalone
F  Lazy loading audit      ─── trivial, standalone
C  Feature flags           ─── moderate, enables B/D gating
B  Unified Tool Registry   ─── significant, provides schema for D
D  Permission hooks        ─── moderate, builds on B's schema + C's flags
E  Workflow memory         ─── moderate, independent
```

A and F can run in parallel. C must precede B and D. B must precede D. E is independent of all others.

---

## Success Criteria

- **A:** Phase 1 startup time reduced (measurable via log timestamps)
- **F:** No top-level `import torch/chromadb/PIL/cv2` in non-test backend files
- **C:** `config.features.*` flags respected; disabling a flag skips its init
- **B:** At least 1 tool migrated to `BaseTool` with working schema validation
- **D:** WebSocket `/ws` rejects unauthenticated connections in multi-user mode; `BaseTool` permission levels enforced via extension hook
- **E:** Agents in parallel workflow steps can read findings from prior steps via `WorkflowMemory`
