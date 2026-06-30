# Platform Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 6 architectural improvements — parallel startup, lazy loading, feature flags, unified tool SDK, per-operation permissions, and shared workflow memory.

**Architecture:** Extends existing SSOT config, plugin SDK, extension system, and workflow executor. New `tool_sdk` package in `autobot-shared/` provides schema-validated tool contracts. Permission enforcement wires into existing `BEFORE_TOOL_EXECUTE` extension hook.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, Redis, asyncio, Vue 3 + Vite

**Spec:** `docs/superpowers/specs/2026-03-31-platform-hardening-design.md`

---

## File Structure

### New files
- `autobot-shared/tool_sdk/__init__.py` — Package re-exports
- `autobot-shared/tool_sdk/base.py` — BaseTool, ToolPermission, ToolResult
- `autobot-shared/tool_sdk/registry.py` — ToolSDKRegistry singleton
- `autobot-shared/tool_sdk/base_test.py` — Tests for tool SDK base classes
- `autobot-shared/tool_sdk/registry_test.py` — Tests for registry
- `autobot-shared/workflow_memory.py` — WorkflowMemory Redis-backed KV store
- `autobot-shared/workflow_memory_test.py` — Tests for workflow memory
- `autobot-backend/extensions/builtin/__init__.py` — Builtin extensions package
- `autobot-backend/extensions/builtin/permission_enforcement.py` — Permission extension
- `autobot-backend/extensions/builtin/permission_enforcement_test.py` — Tests

### Modified files
- `autobot-backend/initialization/lifespan.py` — Parallel startup tiers
- `autobot-shared/ssot_config.py` — Add subsystem feature flags to FeatureConfig
- `autobot-backend/tools/tool_registry.py` — SDK dispatch fallback
- `autobot-backend/auth_middleware.py` — WebSocket auth helper
- `autobot-backend/api/websockets.py` — Auth check before accept
- `autobot-frontend/src/services/GlobalWebSocketService.ts` — Pass JWT token
- `autobot-frontend/vite.config.ts` — Compile-time feature defines
- `autobot-backend/orchestration/workflow_executor.py` — WorkflowMemory integration
- ~19 backend files — Lazy import deferral (torch, chromadb, PIL, cv2)

---

## Task 1: Parallel Startup Init

**Files:**
- Modify: `autobot-backend/initialization/lifespan.py:330-377`
- Test: manual — verify via startup log timestamps

- [ ] **Step 1: Read current `initialize_critical_services` function**

Confirm the sequential steps at lines 352-369 match the expected dependency graph before editing.

- [ ] **Step 2: Replace sequential init with tiered asyncio.gather**

In `autobot-backend/initialization/lifespan.py`, replace the body of `initialize_critical_services()` (inside the try block, lines 353-369) with:

```python
        # Tier 0: No dependencies
        await _check_env_drift()

        # Tier 1: Config must complete before anything else
        await _init_config(app)

        # Tier 2: Independent of each other, only need config
        await asyncio.gather(
            _init_security_layer(app),
            _init_database(),
            _init_telemetry_and_redis(),
        )

        # Tier 3: Need DB/Redis from Tier 2
        await asyncio.gather(
            _init_chat_history_manager(app),
            _init_conversation_file_manager(app),
            _init_chat_workflow_manager(app),
        )

        # Tier 4: Need managers from Tier 3
        await asyncio.gather(
            _init_cache_coordinator(),
            _init_skills(app),
        )
```

- [ ] **Step 3: Verify `asyncio` is already imported**

Check the imports at the top of `lifespan.py`. Confirm `import asyncio` is present (it is — line 14).

- [ ] **Step 4: Run backend startup and verify logs**

Run: `cd autobot-backend && python -c "from initialization.lifespan import initialize_critical_services; print('Import OK')"`
Expected: `Import OK` (no syntax errors)

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/initialization/lifespan.py
git commit -m "perf(startup): parallelize Phase 1 init with asyncio.gather (#ISSUE)"
```

---

## Task 2: Feature Flags — Extend FeatureConfig

**Files:**
- Modify: `autobot-shared/ssot_config.py:943-960`

- [ ] **Step 1: Write test to verify new flags exist on config**

Create `autobot-shared/feature_flags_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for subsystem feature flags in FeatureConfig."""

from autobot_shared.ssot_config import get_config


class TestFeatureFlags:
    """Test that subsystem feature flags are accessible and have correct defaults."""

    def test_default_flags_exist(self):
        config = get_config()
        assert hasattr(config.feature, "npu")
        assert hasattr(config.feature, "voice")
        assert hasattr(config.feature, "browser_automation")
        assert hasattr(config.feature, "computer_vision")
        assert hasattr(config.feature, "training")
        assert hasattr(config.feature, "graph_rag")
        assert hasattr(config.feature, "mcp")

    def test_heavy_features_off_by_default(self):
        config = get_config()
        assert config.feature.computer_vision is False
        assert config.feature.training is False

    def test_standard_features_on_by_default(self):
        config = get_config()
        assert config.feature.npu is True
        assert config.feature.voice is True
        assert config.feature.browser_automation is True
        assert config.feature.graph_rag is True
        assert config.feature.mcp is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-shared && python -m pytest feature_flags_test.py -v`
Expected: FAIL — `AttributeError: 'FeatureConfig' object has no attribute 'npu'`

- [ ] **Step 3: Add subsystem flags to FeatureConfig**

In `autobot-shared/ssot_config.py`, add new fields to the existing `FeatureConfig` class (after line 959):

```python
class FeatureConfig(BaseSettings):
    """Feature flags configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    unified_config: bool = Field(default=True, alias="AUTOBOT_USE_UNIFIED_CONFIG")
    semantic_chunking: bool = Field(default=True, alias="AUTOBOT_SEMANTIC_CHUNKING")
    debug_mode: bool = Field(default=False, alias="AUTOBOT_DEBUG_MODE")
    hot_reload: bool = Field(default=True, alias="AUTOBOT_HOT_RELOAD")
    single_user_mode: bool = Field(default=True, alias="AUTOBOT_SINGLE_USER_MODE")
    permission_system_v2: bool = Field(
        default=False, alias="AUTOBOT_PERMISSION_SYSTEM_V2"
    )

    # Subsystem feature flags — gate optional subsystems per-node
    npu: bool = Field(default=True, alias="AUTOBOT_FEATURE_NPU")
    voice: bool = Field(default=True, alias="AUTOBOT_FEATURE_VOICE")
    browser_automation: bool = Field(
        default=True, alias="AUTOBOT_FEATURE_BROWSER_AUTOMATION"
    )
    computer_vision: bool = Field(
        default=False, alias="AUTOBOT_FEATURE_COMPUTER_VISION"
    )
    training: bool = Field(default=False, alias="AUTOBOT_FEATURE_TRAINING")
    graph_rag: bool = Field(default=True, alias="AUTOBOT_FEATURE_GRAPH_RAG")
    mcp: bool = Field(default=True, alias="AUTOBOT_FEATURE_MCP")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-shared && python -m pytest feature_flags_test.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add autobot-shared/ssot_config.py autobot-shared/feature_flags_test.py
git commit -m "feat(config): add subsystem feature flags to FeatureConfig (#ISSUE)"
```

---

## Task 3: Feature Flags — Frontend Vite Defines

**Files:**
- Modify: `autobot-frontend/vite.config.ts`

- [ ] **Step 1: Add compile-time feature defines to Vite config**

In `autobot-frontend/vite.config.ts`, inside the `return { ... }` object of `defineConfig`, add a `define` block. Find the line with `server:` and add `define` before it:

```typescript
    define: {
      __FEATURE_VOICE__: JSON.stringify(env.VITE_FEATURE_VOICE !== 'false'),
      __FEATURE_VNC__: JSON.stringify(env.VITE_FEATURE_VNC !== 'false'),
      __FEATURE_BROWSER__: JSON.stringify(env.VITE_FEATURE_BROWSER !== 'false'),
    },
```

- [ ] **Step 2: Add TypeScript declarations for feature flags**

Create type declarations so TypeScript knows about the globals. Add to `autobot-frontend/src/shims-vue.d.ts` (or create `autobot-frontend/src/env.d.ts` if preferred):

```typescript
declare const __FEATURE_VOICE__: boolean
declare const __FEATURE_VNC__: boolean
declare const __FEATURE_BROWSER__: boolean
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd autobot-frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds without errors

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/vite.config.ts autobot-frontend/src/shims-vue.d.ts
git commit -m "feat(frontend): add compile-time feature flag defines (#ISSUE)"
```

---

## Task 4: Lazy Loading Audit — torch imports

**Files:**
- Modify: `autobot-backend/ai_hardware_accelerator.py`
- Modify: `autobot-backend/api/multimodal.py`
- Modify: `autobot-backend/multimodal_processor/processor.py`
- Modify: `autobot-backend/multimodal_processor/processors/voice.py`
- Modify: `autobot-backend/multimodal_processor/processors/vision.py`
- Modify: `autobot-backend/services/incremental_trainer.py`
- Modify: `autobot-backend/llm_interface_pkg/optimization/flash_attention.py`

- [ ] **Step 1: For each file, move top-level `import torch` and `from torch` to function-level**

Pattern for each file:

**Before:**
```python
import torch
import torch.nn.functional as F
from PIL import Image

class SomeProcessor:
    def process(self, data):
        tensor = torch.from_numpy(data)
```

**After:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch

class SomeProcessor:
    def process(self, data):
        import torch
        import torch.nn.functional as F

        tensor = torch.from_numpy(data)
```

Apply this to each of the 7 files listed above. For each file:
1. Remove top-level `import torch` / `from torch` / `from PIL import Image` lines
2. Add the imports inside the first method that uses them
3. If multiple methods in the same class use torch, add the import to each method (Python caches it after first import — negligible overhead)
4. Add `TYPE_CHECKING` guard only if torch types appear in type annotations

- [ ] **Step 2: Verify no syntax errors**

Run: `cd autobot-backend && python -c "import ai_hardware_accelerator; import api.multimodal; print('OK')"`
Expected: `OK` (no import-time crash since torch is now deferred)

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/ai_hardware_accelerator.py autobot-backend/api/multimodal.py autobot-backend/multimodal_processor/processor.py autobot-backend/multimodal_processor/processors/voice.py autobot-backend/multimodal_processor/processors/vision.py autobot-backend/services/incremental_trainer.py autobot-backend/llm_interface_pkg/optimization/flash_attention.py
git commit -m "perf(imports): defer torch imports to function-level (#ISSUE)"
```

---

## Task 5: Lazy Loading Audit — chromadb, PIL, cv2

**Files:**
- Modify: `autobot-backend/utils/chromadb_client.py`
- Modify: `autobot-backend/utils/async_chromadb_client.py`
- Modify: `autobot-backend/computer_vision/screen_analyzer.py`
- Modify: `autobot-backend/services/captcha_solver.py`

- [ ] **Step 1: Defer chromadb imports in both client files**

In `autobot-backend/utils/chromadb_client.py` and `autobot-backend/utils/async_chromadb_client.py`:

Move `import chromadb` and `from chromadb.config import Settings as ChromaSettings` from top-level into the factory functions (`get_chromadb_client()`, `get_async_chromadb_client()`).

- [ ] **Step 2: Defer PIL and cv2 imports**

In `autobot-backend/computer_vision/screen_analyzer.py`:
Move `import cv2` and `from PIL import Image` into the methods that use them.

In `autobot-backend/services/captcha_solver.py`:
Move `from PIL import Image, ImageEnhance, ImageFilter` into the method that uses them.

- [ ] **Step 3: Verify no syntax errors**

Run: `cd autobot-backend && python -c "import utils.chromadb_client; import computer_vision.screen_analyzer; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add autobot-backend/utils/chromadb_client.py autobot-backend/utils/async_chromadb_client.py autobot-backend/computer_vision/screen_analyzer.py autobot-backend/services/captcha_solver.py
git commit -m "perf(imports): defer chromadb/PIL/cv2 imports to function-level (#ISSUE)"
```

---

## Task 6: Tool SDK — Base Classes

**Files:**
- Create: `autobot-shared/tool_sdk/__init__.py`
- Create: `autobot-shared/tool_sdk/base.py`
- Test: `autobot-shared/tool_sdk/base_test.py`

- [ ] **Step 1: Write failing test for BaseTool and ToolResult**

Create `autobot-shared/tool_sdk/base_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for tool SDK base classes."""

import pytest
from pydantic import BaseModel, ValidationError

from tool_sdk.base import BaseTool, ToolPermission, ToolResult


class EchoInput(BaseModel):
    message: str


class EchoTool(BaseTool):
    name = "echo"
    description = "Echoes input back"
    permission = ToolPermission.PUBLIC
    input_schema = EchoInput
    category = "test"

    async def execute(self, params: EchoInput) -> ToolResult:
        return ToolResult(success=True, data=params.message)


class TestToolPermission:
    def test_permission_values(self):
        assert ToolPermission.PUBLIC == "public"
        assert ToolPermission.AUTHENTICATED == "authenticated"
        assert ToolPermission.OPERATOR == "operator"
        assert ToolPermission.ADMIN == "admin"

    def test_permission_ordering(self):
        levels = [
            ToolPermission.PUBLIC,
            ToolPermission.AUTHENTICATED,
            ToolPermission.OPERATOR,
            ToolPermission.ADMIN,
        ]
        assert len(levels) == 4


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(success=False, error="Something failed")
        assert result.success is False
        assert result.error == "Something failed"
        assert result.data is None

    def test_metadata(self):
        result = ToolResult(success=True, metadata={"elapsed_ms": 42})
        assert result.metadata["elapsed_ms"] == 42


class TestBaseTool:
    @pytest.mark.asyncio
    async def test_echo_tool_execute(self):
        tool = EchoTool()
        params = EchoInput(message="hello")
        result = await tool.execute(params)
        assert result.success is True
        assert result.data == "hello"

    def test_tool_attributes(self):
        tool = EchoTool()
        assert tool.name == "echo"
        assert tool.description == "Echoes input back"
        assert tool.permission == ToolPermission.PUBLIC
        assert tool.input_schema is EchoInput
        assert tool.category == "test"

    def test_input_validation(self):
        with pytest.raises(ValidationError):
            EchoInput(message=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-shared && python -m pytest tool_sdk/base_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tool_sdk'`

- [ ] **Step 3: Create tool_sdk package**

Create `autobot-shared/tool_sdk/__init__.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool SDK — standardized tool contracts with schema validation.

Provides BaseTool base class, ToolPermission levels, ToolResult model,
and ToolSDKRegistry for auto-discovery of schema-validated tools.
"""

from tool_sdk.base import BaseTool, ToolPermission, ToolResult
from tool_sdk.registry import ToolSDKRegistry, get_tool_sdk_registry

__all__ = [
    "BaseTool",
    "ToolPermission",
    "ToolResult",
    "ToolSDKRegistry",
    "get_tool_sdk_registry",
]
```

Create `autobot-shared/tool_sdk/base.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool SDK base classes.

Provides the BaseTool abstract class, ToolPermission enum, and ToolResult model
for building schema-validated, permission-aware tools.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolPermission(str, Enum):
    """Permission level required to execute a tool."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    OPERATOR = "operator"
    ADMIN = "admin"


# Ordered list for comparison — higher index = more privilege
_PERMISSION_ORDER = [
    ToolPermission.PUBLIC,
    ToolPermission.AUTHENTICATED,
    ToolPermission.OPERATOR,
    ToolPermission.ADMIN,
]


def permission_satisfies(user_level: ToolPermission, required: ToolPermission) -> bool:
    """Check if user_level meets or exceeds required permission.

    Args:
        user_level: The permission level the user has.
        required: The permission level the tool requires.

    Returns:
        True if user_level >= required.
    """
    return _PERMISSION_ORDER.index(user_level) >= _PERMISSION_ORDER.index(required)


class ToolResult(BaseModel):
    """Standardized result returned by all BaseTool implementations."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class BaseTool(ABC):
    """Abstract base class for schema-validated tools.

    Subclasses must define class attributes and implement execute().

    Example::

        class MyInput(BaseModel):
            query: str

        class SearchTool(BaseTool):
            name = "search"
            description = "Search the knowledge base"
            permission = ToolPermission.AUTHENTICATED
            input_schema = MyInput
            category = "knowledge"

            async def execute(self, params: MyInput) -> ToolResult:
                results = await kb.search(params.query)
                return ToolResult(success=True, data=results)
    """

    name: str = ""
    description: str = ""
    permission: ToolPermission = ToolPermission.AUTHENTICATED
    input_schema: Type[BaseModel] = BaseModel
    category: str = "general"

    @abstractmethod
    async def execute(self, params: BaseModel) -> ToolResult:
        """Execute the tool with validated parameters.

        Args:
            params: Validated input (instance of self.input_schema).

        Returns:
            ToolResult with success/error and data.
        """
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-shared && python -m pytest tool_sdk/base_test.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add autobot-shared/tool_sdk/__init__.py autobot-shared/tool_sdk/base.py autobot-shared/tool_sdk/base_test.py
git commit -m "feat(tool-sdk): add BaseTool, ToolPermission, ToolResult base classes (#ISSUE)"
```

---

## Task 7: Tool SDK — Registry

**Files:**
- Create: `autobot-shared/tool_sdk/registry.py`
- Test: `autobot-shared/tool_sdk/registry_test.py`

- [ ] **Step 1: Write failing test for ToolSDKRegistry**

Create `autobot-shared/tool_sdk/registry_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for ToolSDKRegistry."""

import pytest
from pydantic import BaseModel

from tool_sdk.base import BaseTool, ToolPermission, ToolResult
from tool_sdk.registry import ToolSDKRegistry, get_tool_sdk_registry


class PingInput(BaseModel):
    pass


class PingTool(BaseTool):
    name = "ping"
    description = "Returns pong"
    permission = ToolPermission.PUBLIC
    input_schema = PingInput
    category = "system"

    async def execute(self, params: PingInput) -> ToolResult:
        return ToolResult(success=True, data="pong")


class AdminInput(BaseModel):
    target: str


class AdminTool(BaseTool):
    name = "admin_reset"
    description = "Admin-only reset"
    permission = ToolPermission.ADMIN
    input_schema = AdminInput
    category = "admin"

    async def execute(self, params: AdminInput) -> ToolResult:
        return ToolResult(success=True, data=f"reset {params.target}")


class TestToolSDKRegistry:
    def setup_method(self):
        """Reset singleton state between tests."""
        ToolSDKRegistry._tools = {}

    def test_register_and_get(self):
        registry = get_tool_sdk_registry()
        tool = PingTool()
        registry.register(tool)
        assert registry.get("ping") is tool

    def test_get_nonexistent_returns_none(self):
        registry = get_tool_sdk_registry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = get_tool_sdk_registry()
        registry.register(PingTool())
        registry.register(AdminTool())
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_list_tools_by_category(self):
        registry = get_tool_sdk_registry()
        registry.register(PingTool())
        registry.register(AdminTool())
        admin_tools = registry.list_tools(category="admin")
        assert len(admin_tools) == 1
        assert admin_tools[0].name == "admin_reset"

    def test_get_schemas(self):
        registry = get_tool_sdk_registry()
        registry.register(PingTool())
        schemas = registry.get_schemas()
        assert "ping" in schemas
        assert schemas["ping"]["permission"] == "public"

    def test_duplicate_register_warns(self):
        registry = get_tool_sdk_registry()
        registry.register(PingTool())
        registry.register(PingTool())  # Should warn, not crash
        assert len(registry.list_tools()) == 1

    def test_singleton(self):
        r1 = get_tool_sdk_registry()
        r2 = get_tool_sdk_registry()
        assert r1 is r2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-shared && python -m pytest tool_sdk/registry_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tool_sdk.registry'`

- [ ] **Step 3: Implement ToolSDKRegistry**

Create `autobot-shared/tool_sdk/registry.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool SDK Registry — singleton for BaseTool registration and discovery.
"""

import logging
from typing import Any, Dict, List, Optional

from tool_sdk.base import BaseTool

logger = logging.getLogger(__name__)


class ToolSDKRegistry:
    """Singleton registry for BaseTool implementations.

    Usage::

        from tool_sdk.registry import get_tool_sdk_registry

        registry = get_tool_sdk_registry()
        registry.register(MyTool())
        tool = registry.get("my_tool")
    """

    _instance: Optional["ToolSDKRegistry"] = None
    _tools: Dict[str, BaseTool] = {}

    def __new__(cls) -> "ToolSDKRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Warns on duplicate names."""
        if tool.name in self._tools:
            logger.warning("Tool '%s' already registered, skipping", tool.name)
            return
        self._tools[tool.name] = tool
        logger.info(
            "Registered tool '%s' (category=%s, permission=%s)",
            tool.name,
            tool.category,
            tool.permission.value,
        )

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[BaseTool]:
        """List all registered tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def get_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Export all tool schemas as a dict keyed by tool name.

        Returns:
            Dict mapping tool name to schema info including input JSON schema,
            description, permission level, and category.
        """
        schemas = {}
        for name, tool in self._tools.items():
            schemas[name] = {
                "description": tool.description,
                "permission": tool.permission.value,
                "category": tool.category,
                "input_schema": tool.input_schema.model_json_schema(),
            }
        return schemas


def get_tool_sdk_registry() -> ToolSDKRegistry:
    """Get the global ToolSDKRegistry singleton."""
    return ToolSDKRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-shared && python -m pytest tool_sdk/registry_test.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add autobot-shared/tool_sdk/registry.py autobot-shared/tool_sdk/registry_test.py
git commit -m "feat(tool-sdk): add ToolSDKRegistry singleton (#ISSUE)"
```

---

## Task 8: Tool SDK — Integration with Existing ToolRegistry

**Files:**
- Modify: `autobot-backend/tools/tool_registry.py`

- [ ] **Step 1: Add SDK dispatch fallback to ToolRegistry.execute_tool**

Find the `execute_tool` method in `autobot-backend/tools/tool_registry.py`. It uses a dispatch dict with lambda handlers. Add SDK lookup at the top of the method, before the dispatch table:

```python
    async def execute_tool(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool by name with given arguments.

        Checks ToolSDKRegistry first for schema-validated tools,
        then falls back to legacy dispatch table.
        """
        # Try SDK-registered tools first
        sdk_result = await self._try_sdk_dispatch(tool_name, tool_args)
        if sdk_result is not None:
            return sdk_result

        # Legacy dispatch table (existing code below)
        ...
```

Add the `_try_sdk_dispatch` method to the `ToolRegistry` class:

```python
    async def _try_sdk_dispatch(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Attempt to dispatch via ToolSDKRegistry.

        Returns None if tool not found in SDK registry (falls through to legacy).
        """
        try:
            from tool_sdk.registry import get_tool_sdk_registry

            registry = get_tool_sdk_registry()
            tool = registry.get(tool_name)
            if tool is None:
                return None

            # Validate input against schema
            params = tool.input_schema(**tool_args)
            result = await tool.execute(params)

            return {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result.data if result.success else result.error,
                "status": "success" if result.success else "error",
                "metadata": result.metadata,
            }
        except Exception as e:
            self.logger.error("SDK tool dispatch failed for '%s': %s", tool_name, e)
            return None
```

- [ ] **Step 2: Verify import works**

Run: `cd autobot-backend && python -c "from tools.tool_registry import ToolRegistry; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/tools/tool_registry.py
git commit -m "feat(tools): integrate ToolSDKRegistry into legacy ToolRegistry dispatch (#ISSUE)"
```

---

## Task 9: Per-Operation Permission Extension

**Files:**
- Create: `autobot-backend/extensions/builtin/__init__.py`
- Create: `autobot-backend/extensions/builtin/permission_enforcement.py`
- Test: `autobot-backend/extensions/builtin/permission_enforcement_test.py`

- [ ] **Step 1: Write failing test**

Create `autobot-backend/extensions/builtin/permission_enforcement_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for PermissionEnforcementExtension."""

import pytest

from extensions.base import HookContext
from extensions.builtin.permission_enforcement import PermissionEnforcementExtension


class TestPermissionEnforcement:
    def setup_method(self):
        self.ext = PermissionEnforcementExtension()

    @pytest.mark.asyncio
    async def test_legacy_tool_allowed(self):
        """Tools without permission level (legacy) should be allowed."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("user_role", "user")
        # No tool_permission set — legacy tool
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None  # No block

    @pytest.mark.asyncio
    async def test_public_tool_no_auth(self):
        """Public tools should work without authentication."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "public")
        # No user_role — unauthenticated
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticated_tool_with_user(self):
        """Authenticated tools should work for any logged-in user."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "authenticated")
        ctx.set("user_role", "user")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_admin_tool_blocked_for_user(self):
        """Admin tools should be blocked for regular users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "admin")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError, match="admin"):
            await self.ext.on_before_tool_execute(ctx)

    @pytest.mark.asyncio
    async def test_admin_tool_allowed_for_admin(self):
        """Admin tools should work for admin users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "admin")
        ctx.set("user_role", "admin")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_operator_tool_allowed_for_admin(self):
        """Operator tools should work for admin (higher privilege)."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "operator")
        ctx.set("user_role", "admin")
        result = await self.ext.on_before_tool_execute(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_operator_tool_blocked_for_user(self):
        """Operator tools should be blocked for regular users."""
        ctx = HookContext(session_id="s1", message="test")
        ctx.set("tool_permission", "operator")
        ctx.set("user_role", "user")
        with pytest.raises(PermissionError):
            await self.ext.on_before_tool_execute(ctx)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest extensions/builtin/permission_enforcement_test.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create builtin extensions package**

Create `autobot-backend/extensions/builtin/__init__.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Built-in extensions that ship with AutoBot."""
```

Create `autobot-backend/extensions/builtin/permission_enforcement.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Permission Enforcement Extension

Built-in extension that checks tool permission levels against user roles
before allowing tool execution. Wires into BEFORE_TOOL_EXECUTE hook.
"""

import logging
from typing import Optional

from extensions.base import Extension, HookContext

logger = logging.getLogger(__name__)

# Role hierarchy — higher index = more privilege
_ROLE_LEVELS = {
    "public": 0,
    "readonly": 1,
    "user": 2,
    "editor": 3,
    "analyst": 3,
    "operator": 4,
    "admin": 5,
}

# Permission to minimum role level
_PERMISSION_MIN_LEVEL = {
    "public": 0,
    "authenticated": 2,
    "operator": 4,
    "admin": 5,
}


def _role_satisfies(user_role: Optional[str], tool_permission: str) -> bool:
    """Check if user role meets tool permission requirement.

    Args:
        user_role: User's role string (e.g., "user", "admin"). None = unauthenticated.
        tool_permission: Required permission (e.g., "public", "admin").

    Returns:
        True if user has sufficient privilege.
    """
    if tool_permission == "public":
        return True

    if user_role is None:
        return False

    user_level = _ROLE_LEVELS.get(user_role.lower(), 0)
    required_level = _PERMISSION_MIN_LEVEL.get(tool_permission, 5)
    return user_level >= required_level


class PermissionEnforcementExtension(Extension):
    """Enforces tool-level permissions before execution.

    Reads ``tool_permission`` and ``user_role`` from HookContext.data.
    Legacy tools without ``tool_permission`` are allowed through (backward compat).
    """

    name = "permission_enforcement"
    priority = 0  # Runs first — before any other extension

    async def on_before_tool_execute(self, ctx: HookContext) -> Optional[bool]:
        """Check permission before tool execution.

        Raises:
            PermissionError: If user lacks required permission.
        """
        tool_permission = ctx.get("tool_permission")
        if tool_permission is None:
            return None  # Legacy tool — no schema, allow through

        user_role = ctx.get("user_role")

        if not _role_satisfies(user_role, tool_permission):
            logger.warning(
                "Permission denied: tool requires '%s', user has role '%s'",
                tool_permission,
                user_role,
            )
            raise PermissionError(
                f"Tool requires '{tool_permission}' permission, "
                f"user has role '{user_role}'"
            )

        return None  # Allow execution
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-backend && python -m pytest extensions/builtin/permission_enforcement_test.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/extensions/builtin/__init__.py autobot-backend/extensions/builtin/permission_enforcement.py autobot-backend/extensions/builtin/permission_enforcement_test.py
git commit -m "feat(security): add PermissionEnforcementExtension for tool-level RBAC (#ISSUE)"
```

---

## Task 10: WebSocket Authentication

**Files:**
- Modify: `autobot-backend/auth_middleware.py`
- Modify: `autobot-backend/api/websockets.py`
- Modify: `autobot-frontend/src/services/GlobalWebSocketService.ts`

- [ ] **Step 1: Add `authenticate_websocket` to auth_middleware.py**

Add a new standalone function at the end of `autobot-backend/auth_middleware.py` (before any `if __name__` block). This uses `AuthMiddleware().verify_jwt_token()` which is the existing JWT decode method:

```python
async def authenticate_websocket(websocket) -> Optional[dict]:
    """Authenticate a WebSocket connection.

    Checks for JWT token in query params. Falls back to synthetic admin
    in single-user mode. Returns None if unauthenticated.

    Args:
        websocket: FastAPI WebSocket instance.

    Returns:
        User dict or None if authentication fails.
    """
    # Check query param token
    token = websocket.query_params.get("token")
    if token:
        try:
            auth = AuthMiddleware()
            token_data = auth.verify_jwt_token(token)
            if token_data:
                return {
                    "username": token_data["username"],
                    "role": token_data["role"],
                    "email": token_data.get("email", ""),
                    "auth_method": "jwt_websocket",
                }
        except Exception:
            logger.warning("WebSocket JWT authentication failed")
            return None

    # Single-user mode bypass
    config = ConfigManager()
    if config.get("security.single_user_mode", True):
        return {
            "username": "admin",
            "role": "admin",
            "email": "admin@autobot.local",
            "source": "single_user_mode",
        }

    return None
```

- [ ] **Step 2: Add auth check to WebSocket endpoints**

In `autobot-backend/api/websockets.py`, modify the `/ws` endpoint (around line 500-510). Add the import at the top of the file:

```python
from auth_middleware import authenticate_websocket
```

Then modify the endpoint function to add auth before `websocket.accept()`:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event stream between backend and frontend."""
    # Issue #2818: Authenticate before accepting connection
    user = await authenticate_websocket(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        await websocket.accept()
        # ... rest of existing code unchanged
```

Apply the same pattern to `/ws/npu-workers` (around line 548) and `/ws-test` (around line 400).

- [ ] **Step 3: Pass JWT token in frontend WebSocket client**

In `autobot-frontend/src/services/GlobalWebSocketService.ts`, find the method that constructs the WebSocket URL (around lines 136-149). Modify to append the token:

```typescript
    // After constructing wsUrl, append auth token
    const userStore = useUserStore()
    const token = userStore.token
    if (token) {
      const separator = wsUrl.includes('?') ? '&' : '?'
      wsUrl = `${wsUrl}${separator}token=${encodeURIComponent(token)}`
    }
```

Add the import at the top of the file:

```typescript
import { useUserStore } from '@/stores/useUserStore'
```

- [ ] **Step 4: Verify import works**

Run: `cd autobot-backend && python -c "from auth_middleware import authenticate_websocket; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/auth_middleware.py autobot-backend/api/websockets.py autobot-frontend/src/services/GlobalWebSocketService.ts
git commit -m "fix(security): authenticate WebSocket connections (#2818, #ISSUE)"
```

---

## Task 11: Shared Workflow Memory

**Files:**
- Create: `autobot-shared/workflow_memory.py`
- Test: `autobot-shared/workflow_memory_test.py`
- Modify: `autobot-backend/orchestration/workflow_executor.py`

- [ ] **Step 1: Write failing test**

Create `autobot-shared/workflow_memory_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for WorkflowMemory."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from autobot_shared.workflow_memory import WorkflowMemory


class TestWorkflowMemory:
    def setup_method(self):
        self.memory = WorkflowMemory("wf-123")

    def test_key_format(self):
        assert self.memory._key == "autobot:workflow:wf-123:memory"

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_write(self, mock_get_redis):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await self.memory.write("step1:result", '{"status": "done"}')

        mock_redis.hset.assert_called_once_with(
            "autobot:workflow:wf-123:memory", "step1:result", '{"status": "done"}'
        )
        mock_redis.expire.assert_called_once_with(
            "autobot:workflow:wf-123:memory", 3600
        )

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_read(self, mock_get_redis):
        mock_redis = AsyncMock()
        mock_redis.hget.return_value = '{"status": "done"}'
        mock_get_redis.return_value = mock_redis

        result = await self.memory.read("step1:result")

        assert result == '{"status": "done"}'
        mock_redis.hget.assert_called_once_with(
            "autobot:workflow:wf-123:memory", "step1:result"
        )

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_read_all(self, mock_get_redis):
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"k1": "v1", "k2": "v2"}
        mock_get_redis.return_value = mock_redis

        result = await self.memory.read_all()

        assert result == {"k1": "v1", "k2": "v2"}

    @pytest.mark.asyncio
    @patch("autobot_shared.workflow_memory.get_redis_client")
    async def test_clear(self, mock_get_redis):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await self.memory.clear()

        mock_redis.delete.assert_called_once_with(
            "autobot:workflow:wf-123:memory"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-shared && python -m pytest workflow_memory_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'autobot_shared.workflow_memory'`

- [ ] **Step 3: Implement WorkflowMemory**

Create `autobot-shared/workflow_memory.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Workflow Memory — Redis-backed KV store for multi-agent collaboration.

Enables agents working on parallel workflow steps to share findings
through a lightweight Redis hash scoped to the workflow ID.

Usage::

    from autobot_shared.workflow_memory import WorkflowMemory

    memory = WorkflowMemory("wf-abc123")
    await memory.write("step1:findings", json.dumps(results))
    prior = await memory.read("step1:findings")
    await memory.clear()  # Call when workflow completes
"""

import logging
from typing import Dict, Optional

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Auto-expire stuck workflows after 1 hour
_DEFAULT_TTL_SECONDS = 3600


class WorkflowMemory:
    """Shared KV memory for agents within a single workflow.

    Storage: Redis hash at ``autobot:workflow:{workflow_id}:memory``
    TTL: 1 hour after last write (auto-expires stuck workflows).
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        self._key = f"autobot:workflow:{workflow_id}:memory"

    async def write(self, key: str, value: str, agent_id: str = "") -> None:
        """Store a key-value pair in shared workflow memory.

        Args:
            key: Memory key (convention: ``{step_id}:result`` or ``shared:*``).
            value: String value (JSON-encode complex data).
            agent_id: Optional agent identifier for audit logging.
        """
        redis = await get_redis_client(async_client=True, database="main")
        await redis.hset(self._key, key, value)
        await redis.expire(self._key, _DEFAULT_TTL_SECONDS)
        if agent_id:
            logger.debug(
                "WorkflowMemory[%s] agent=%s wrote key=%s",
                self.workflow_id,
                agent_id,
                key,
            )

    async def read(self, key: str) -> Optional[str]:
        """Read a specific key from shared workflow memory.

        Args:
            key: Memory key to read.

        Returns:
            Value string or None if not found.
        """
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hget(self._key, key)

    async def read_all(self) -> Dict[str, str]:
        """Read all shared memory for this workflow.

        Returns:
            Dict of all key-value pairs.
        """
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hgetall(self._key)

    async def clear(self) -> None:
        """Clean up workflow memory. Call when workflow completes."""
        redis = await get_redis_client(async_client=True, database="main")
        await redis.delete(self._key)
        logger.debug("WorkflowMemory[%s] cleared", self.workflow_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd autobot-shared && python -m pytest workflow_memory_test.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Integrate with WorkflowExecutor**

In `autobot-backend/orchestration/workflow_executor.py`, add the import at the top:

```python
from autobot_shared.workflow_memory import WorkflowMemory
```

Modify the `WorkflowExecutor.__init__` to accept an optional `memory` parameter:

```python
    def __init__(
        self,
        agent_registry,
        agent_interactions,
        reserve_agent_callback,
        release_agent_callback,
        update_performance_callback,
        memory: Optional[WorkflowMemory] = None,
    ):
        # ... existing init code ...
        self.memory = memory
```

Add `Optional` to the typing imports if not already present. Add `WorkflowMemory` to `TYPE_CHECKING` imports if preferred.

- [ ] **Step 6: Commit**

```bash
git add autobot-shared/workflow_memory.py autobot-shared/workflow_memory_test.py autobot-backend/orchestration/workflow_executor.py
git commit -m "feat(orchestration): add shared WorkflowMemory for multi-agent collaboration (#ISSUE)"
```

---

## Task 12: Register Permission Extension in Lifespan

**Files:**
- Modify: `autobot-backend/initialization/lifespan.py`

- [ ] **Step 1: Register the built-in permission extension during Phase 1**

In `autobot-backend/initialization/lifespan.py`, add a new helper function (near the other `_init_*` helpers):

```python
async def _init_builtin_extensions(app: FastAPI) -> None:
    """Register built-in extensions (permission enforcement, etc.)."""
    try:
        from extensions.builtin.permission_enforcement import (
            PermissionEnforcementExtension,
        )
        from extensions.manager import ExtensionManager

        manager = getattr(app.state, "extension_manager", None)
        if manager is None:
            manager = ExtensionManager()
            app.state.extension_manager = manager

        manager.register(PermissionEnforcementExtension())
        logger.info("✅ Built-in extensions registered (permission_enforcement)")
    except Exception as ext_error:
        logger.warning("Built-in extension registration failed (non-critical): %s", ext_error)
```

Call it in `initialize_critical_services()` in Tier 4 (alongside skills):

```python
        # Tier 4: Need managers from Tier 3
        await asyncio.gather(
            _init_cache_coordinator(),
            _init_skills(app),
            _init_builtin_extensions(app),
        )
```

- [ ] **Step 2: Verify import works**

Run: `cd autobot-backend && python -c "from extensions.builtin.permission_enforcement import PermissionEnforcementExtension; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/initialization/lifespan.py
git commit -m "feat(startup): register PermissionEnforcementExtension at boot (#ISSUE)"
```

---

## Task 13: Create GitHub Issues

**Files:** None (GitHub operations only)

- [ ] **Step 1: Create umbrella issue for platform hardening**

```bash
gh issue create \
  --title "Platform Hardening: 6 architecture improvements" \
  --body "## Overview
Implement 6 architectural improvements from spec analysis.

See: docs/superpowers/specs/2026-03-31-platform-hardening-design.md
Plan: docs/superpowers/plans/2026-03-31-platform-hardening.md

## Items
- [ ] A: Parallel startup init (asyncio.gather in Phase 1)
- [ ] F: Lazy loading audit (defer torch/chromadb/PIL/cv2)
- [ ] C: Feature flags (extend FeatureConfig + Vite defines)
- [ ] B: Unified Tool SDK (BaseTool + ToolSDKRegistry)
- [ ] D: Per-operation permission hooks (PermissionEnforcementExtension + WS auth)
- [ ] E: Shared workflow memory (WorkflowMemory Redis hash)

## Related
- Closes #2818 (WebSocket auth)" \
  --label "enhancement,backend,frontend,priority: high"
```

- [ ] **Step 2: Note the issue number and use it in all commit messages**

Replace `#ISSUE` in all prior commit messages with the actual issue number. If commits were already made with `#ISSUE`, amend is not needed — the closing summary on the issue will link everything.

---

## Summary

| Task | Description | Effort |
|------|-------------|--------|
| 1 | Parallel startup init | 5 min |
| 2 | Feature flags — backend | 10 min |
| 3 | Feature flags — frontend | 5 min |
| 4 | Lazy loading — torch | 15 min |
| 5 | Lazy loading — chromadb/PIL/cv2 | 10 min |
| 6 | Tool SDK — base classes | 10 min |
| 7 | Tool SDK — registry | 10 min |
| 8 | Tool SDK — integration | 5 min |
| 9 | Permission enforcement extension | 10 min |
| 10 | WebSocket authentication | 10 min |
| 11 | Shared workflow memory | 10 min |
| 12 | Register extension in lifespan | 5 min |
| 13 | Create GitHub issues | 5 min |

**Dependency order:** Task 13 first (to get issue number), then 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12. Tasks 4-5 are independent of 6-8. Tasks 1-5 can run as one parallel track, 6-8-9-10 as another.
