# AutoBot Prompt Middleware Developer Guide

This guide explains how to implement custom middleware that intercepts and modifies LLM prompts in AutoBot's chat pipeline.  It covers the full call path from `llm_handler.py` through `ExtensionManager` to your extension, the `HookContext` data contract, dispatch internals, registration, priority ordering, and testing.

## Architecture overview

```
chat_workflow/llm_handler.py
  │
  ├─ _get_system_prompt(session)
  │       ↓
  ├─ _emit_system_prompt_ready(system_prompt, session)    ← HookPoint.SYSTEM_PROMPT_READY
  │       │  ExtensionManager.invoke_with_transform(hook, ctx, "system_prompt")
  │       │  → Extension.on_system_prompt_ready(ctx) in priority order
  │       ↓ returns possibly modified system_prompt
  │
  ├─ _build_full_prompt(system_prompt, knowledge, conversation, message)
  │       ↓
  ├─ _emit_full_prompt_ready(full_prompt, llm_params, context)  ← HookPoint.FULL_PROMPT_READY
  │       │  ExtensionManager.invoke_with_transform(hook, ctx, "prompt")
  │       │  → Extension.on_full_prompt_ready(ctx) in priority order
  │       ↓ returns possibly modified full_prompt
  │
  └─ LLM call with final prompt
```

Both hook emitters use `invoke_with_transform`, which threads the prompt through all registered extensions in priority order — each extension's non-`None` return value becomes the input for the next.

## The two prompt hook points

| HookPoint | Method to override | `ctx.data` keys | Fires after |
|-----------|-------------------|-----------------|-------------|
| `SYSTEM_PROMPT_READY` | `on_system_prompt_ready` | `system_prompt`, `session` | `_get_system_prompt()` |
| `FULL_PROMPT_READY`   | `on_full_prompt_ready`   | `prompt`, `llm_params`, `context` | `_build_full_prompt()` |

Return a `str` to replace the prompt.  Return `None` to leave it unchanged and pass it to the next extension unmodified.

## Call sites in `llm_handler.py`

```python
# autobot-backend/chat_workflow/llm_handler.py (simplified)

system_prompt = self._get_system_prompt(language=language)
system_prompt = await _emit_system_prompt_ready(system_prompt, session)
# ↑ HookPoint.SYSTEM_PROMPT_READY fires here

full_prompt = self._build_full_prompt(
    system_prompt, knowledge_context, conversation_context, message
)
full_prompt = await _emit_full_prompt_ready(
    full_prompt,
    {"endpoint": ollama_endpoint, "model": selected_model},
    {"session_id": session.session_id, "message": message},
)
# ↑ HookPoint.FULL_PROMPT_READY fires here
# full_prompt is now sent to the LLM
```

## `HookContext` reference

`HookContext` is a dataclass defined in `autobot-backend/middleware/base.py`.

```python
@dataclass
class HookContext:
    session_id: str = ""                    # Chat session ID
    message:    str = ""                    # Original user message
    agent_id:   Optional[str] = None       # Agent ID for hierarchical agents
    data: Dict[str, Any] = field(default_factory=dict)  # Hook payload
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `get(key, default=None)` | Read a value from `data` |
| `set` | `set(key, value)` | Write a value into `data` |
| `merge` | `merge(updates: dict)` | Bulk-write multiple values |
| `has` | `has(key) → bool` | Check if key exists |
| `remove` | `remove(key) → value` | Pop and return a key |

### Keys populated for each prompt hook

**`SYSTEM_PROMPT_READY`**
```python
ctx.data = {
    "system_prompt": "<assembled system prompt string>",
    "session":       <WorkflowSession instance>,
}
```

**`FULL_PROMPT_READY`**
```python
ctx.data = {
    "prompt":     "<full assembled prompt string>",
    "llm_params": {"endpoint": "<ollama url>", "model": "<model name>"},
    "context":    {"session_id": "<id>", "message": "<user message>"},
}
```

## Writing a middleware extension

Subclass `Extension` from `autobot-backend/middleware/base.py`.  The hook method name is derived from the `HookPoint` enum name: `SYSTEM_PROMPT_READY` → `on_system_prompt_ready`, `FULL_PROMPT_READY` → `on_full_prompt_ready`.

```python
from typing import Optional
from middleware.base import Extension, HookContext


class MyPromptMiddleware(Extension):
    name     = "my-prompt-middleware"
    priority = 50          # lower = runs first; default is 100

    async def on_system_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Modify the system prompt before prompt assembly."""
        system_prompt = ctx.get("system_prompt", "")
        session       = ctx.get("session")

        # Example: add a technical-detail note for power users
        if getattr(session, "is_power_user", False):
            return system_prompt + "\nYou are talking to a power user — be technical."

        return None  # no change

    async def on_full_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Modify the full assembled prompt before the LLM call."""
        prompt     = ctx.get("prompt", "")
        llm_params = ctx.get("llm_params", {})

        # Example: add a conciseness hint when a small model is selected
        model = llm_params.get("model", "")
        if "3b" in model or "1b" in model:
            return prompt + "\n\n[Note: respond concisely — model has limited capacity.]"

        return None  # no change
```

### Accessing infrastructure telemetry in the hook

```python
import httpx
import os
from typing import Optional
from middleware.base import Extension, HookContext

PROMETHEUS_URL    = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
CPU_THRESHOLD_PCT = float(os.getenv("PROMPT_CPU_THRESHOLD_PCT", "80"))


class TelemetryPromptMiddleware(Extension):
    """Append a concise-response hint when CPU load is high."""

    name     = "telemetry-prompt-middleware"
    priority = 50

    async def on_full_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        prompt = ctx.get("prompt", "")
        if not prompt:
            return None

        cpu = await self._fetch_cpu_percent()
        if cpu is not None and cpu >= CPU_THRESHOLD_PCT:
            hint = (
                f"\n\n[System note: CPU load is {cpu:.0f}% — "
                "please prioritise a concise response.]"
            )
            return prompt + hint

        return None

    async def on_system_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Append a memory-pressure warning to the system prompt."""
        memory_pct = await self._fetch_memory_percent()
        if memory_pct is not None and memory_pct >= 90:
            system_prompt = ctx.get("system_prompt", "")
            return system_prompt + "\n[Memory pressure is high — avoid large data structures.]"
        return None

    async def _fetch_cpu_percent(self) -> Optional[float]:
        query = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
        return await self._prometheus_query(query)

    async def _fetch_memory_percent(self) -> Optional[float]:
        query = (
            "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
        )
        return await self._prometheus_query(query)

    async def _prometheus_query(self, query: str) -> Optional[float]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(
                    f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}
                )
                r.raise_for_status()
                results = r.json().get("data", {}).get("result", [])
                if results:
                    return float(results[0]["value"][1])
        except Exception:
            pass
        return None
```

## `ExtensionManager` dispatch internals

The manager lives in `autobot-backend/middleware/manager.py`.  A global thread-safe singleton is returned by `get_extension_manager()`.

### How `invoke_with_transform` works (used by both prompt hooks)

```python
# Simplified from middleware/manager.py
async def invoke_with_transform(self, hook, ctx, key):
    for extension in self.extensions:           # sorted ascending by priority
        if not extension.enabled:
            continue
        result = await extension.on_hook(hook, ctx)
        if result is not None:
            ctx.set(key, result)   # next extension sees the updated value
    return ctx.get(key)
```

Each extension that returns a non-`None` string **replaces the prompt in the context**, so the next extension in the chain sees the already-modified prompt.  Returning `None` passes the current value through unchanged.

### How `on_hook` routes to your method

```python
# Simplified from middleware/base.py Extension.on_hook()
method_name = f"on_{hook.name.lower()}"
# SYSTEM_PROMPT_READY  →  "on_system_prompt_ready"
# FULL_PROMPT_READY    →  "on_full_prompt_ready"
method = getattr(self, method_name, None)
if method and callable(method):
    return await method(context)
```

Extension errors are caught and logged at ERROR level — they never propagate to the LLM call, so a failing extension cannot break the chat pipeline.

### Other invocation modes

| Method | Used when |
|--------|-----------|
| `invoke_with_transform(hook, ctx, key)` | Prompt hooks — each extension can modify a string in sequence |
| `invoke_hook(hook, ctx)` | General hooks — collect all non-None results from all extensions |
| `invoke_until_handled(hook, ctx)` | Approval hooks — stop at first truthy result |
| `invoke_cancellable(hook, ctx)` | Tool hooks — any `False` return cancels the operation |

## Priority ordering

Extensions are sorted ascending by `priority` — **lower value runs first**.

| Priority range | When to use |
|---------------|-------------|
| 10–49 | Security / filtering middleware (must run before enrichment) |
| 50–99 | Custom business logic (telemetry hints, persona injection) |
| 100 | Default for all `Extension` subclasses |
| 101+ | Post-processing / logging that must run last |

Multiple extensions with the same priority execute in registration order.

## Registering your extension

### Via `plugin.json` (recommended for production)

Create `plugins/my-middleware/plugin.json`:

```json
{
  "name": "my-prompt-middleware",
  "version": "1.0.0",
  "description": "Modify LLM prompts based on infrastructure telemetry",
  "entry_point": "plugin.MyPromptMiddleware",
  "hooks": ["on_system_prompt_ready", "on_full_prompt_ready"],
  "enabled": true,
  "config": {
    "cpu_threshold_pct": 80,
    "prometheus_url": ""
  }
}
```

### Programmatically at startup

```python
from middleware.manager import get_extension_manager
from plugins.my_middleware.plugin import MyPromptMiddleware

get_extension_manager().register(MyPromptMiddleware())
```

### Managing extensions at runtime

```python
mgr = get_extension_manager()

mgr.list_extensions()                    # ["telemetry-prompt-middleware", ...]
mgr.disable_extension("my-middleware")   # pause without removing
mgr.enable_extension("my-middleware")    # resume
mgr.unregister("my-middleware")          # remove permanently
mgr.get_statistics()                     # total/enabled counts + per-extension detail
```

## Testing your middleware

```python
import pytest
from unittest.mock import AsyncMock, patch

from middleware.manager import get_extension_manager, reset_extension_manager
from chat_workflow.llm_handler import _emit_full_prompt_ready, _emit_system_prompt_ready


@pytest.fixture(autouse=True)
def clean_manager():
    reset_extension_manager()
    yield
    reset_extension_manager()


@pytest.mark.asyncio
async def test_hint_injected_when_cpu_high():
    from plugins.core_plugins.telemetry_prompt_middleware.plugin import (
        TelemetryPromptMiddleware,
    )

    mw = TelemetryPromptMiddleware()
    with patch.object(mw, "_fetch_cpu_percent", AsyncMock(return_value=95.0)):
        get_extension_manager().register(mw)
        result = await _emit_full_prompt_ready("You are AutoBot.", {}, {})

    assert "CPU load is 95%" in result


@pytest.mark.asyncio
async def test_no_modification_when_cpu_low():
    from plugins.core_plugins.telemetry_prompt_middleware.plugin import (
        TelemetryPromptMiddleware,
    )

    mw = TelemetryPromptMiddleware()
    with patch.object(mw, "_fetch_cpu_percent", AsyncMock(return_value=40.0)):
        get_extension_manager().register(mw)
        result = await _emit_full_prompt_ready("You are AutoBot.", {}, {})

    assert result == "You are AutoBot."


@pytest.mark.asyncio
async def test_multiple_extensions_chain_in_priority_order():
    """Prompt modifications must chain through extensions sorted by priority."""
    from middleware.base import Extension

    class AddA(Extension):
        name     = "add-a"
        priority = 10

        async def on_full_prompt_ready(self, ctx):
            return ctx.get("prompt") + " [A]"

    class AddB(Extension):
        name     = "add-b"
        priority = 20

        async def on_full_prompt_ready(self, ctx):
            return ctx.get("prompt") + " [B]"

    get_extension_manager().register(AddA())
    get_extension_manager().register(AddB())
    result = await _emit_full_prompt_ready("base", {}, {})
    assert result == "base [A] [B]"


@pytest.mark.asyncio
async def test_extension_error_is_isolated():
    """An exception in one extension must not prevent subsequent extensions from running."""
    from middleware.base import Extension

    class Crasher(Extension):
        name     = "crasher"
        priority = 10

        async def on_full_prompt_ready(self, ctx):
            raise RuntimeError("intentional crash")

    class Appender(Extension):
        name     = "appender"
        priority = 20

        async def on_full_prompt_ready(self, ctx):
            return ctx.get("prompt") + " [ok]"

    get_extension_manager().register(Crasher())
    get_extension_manager().register(Appender())
    result = await _emit_full_prompt_ready("base", {}, {})
    assert result == "base [ok]"


@pytest.mark.asyncio
async def test_system_prompt_hook_receives_session():
    """The session object must be available in on_system_prompt_ready."""
    from middleware.base import Extension

    received = {}

    class Capture(Extension):
        name = "capture"

        async def on_system_prompt_ready(self, ctx):
            received["session"] = ctx.get("session")
            return None

    get_extension_manager().register(Capture())

    class FakeSession:
        session_id = "test-session"

    await _emit_system_prompt_ready("base prompt", FakeSession())
    assert received["session"].session_id == "test-session"
```

## Complete hook reference (all 24 hook points)

| HookPoint | Method | `ctx.data` keys | Return type |
|-----------|--------|-----------------|-------------|
| `BEFORE_MESSAGE_PROCESS` | `on_before_message_process` | `message`, `context` | None |
| `AFTER_PROMPT_BUILD` | `on_after_prompt_build` | `prompt` | str or None |
| `BEFORE_LLM_CALL` | `on_before_llm_call` | `prompt`, `model` | False to cancel, None |
| `DURING_LLM_STREAMING` | `on_during_llm_streaming` | `chunk` | str or None |
| `AFTER_LLM_RESPONSE` | `on_after_llm_response` | `response` | str or None |
| `BEFORE_TOOL_PARSE` | `on_before_tool_parse` | `response` | str or None |
| `BEFORE_TOOL_EXECUTE` | `on_before_tool_execute` | `tool_call` | False to cancel, None |
| `AFTER_TOOL_EXECUTE` | `on_after_tool_execute` | `result` | modified result or None |
| `TOOL_ERROR` | `on_tool_error` | `error` | RepairableException or None |
| `BEFORE_CONTINUATION` | `on_before_continuation` | `prompt`, `context` | False to stop, None |
| `AFTER_CONTINUATION` | `on_after_continuation` | `response` | None |
| `LOOP_COMPLETE` | `on_loop_complete` | `final_response` | None |
| `REPAIRABLE_ERROR` | `on_repairable_error` | `error`, `suggestion` | str or None |
| `CRITICAL_ERROR` | `on_critical_error` | `error` | None |
| `BEFORE_RESPONSE_SEND` | `on_before_response_send` | `response` | str or None |
| `AFTER_RESPONSE_SEND` | `on_after_response_send` | — | None |
| `SESSION_CREATE` | `on_session_create` | `session` | None |
| `SESSION_DESTROY` | `on_session_destroy` | `session` | None |
| `BEFORE_RAG_QUERY` | `on_before_rag_query` | `query` | str or None |
| `AFTER_RAG_RESULTS` | `on_after_rag_results` | `results`, `citations` | list or None |
| `APPROVAL_REQUIRED` | `on_approval_required` | `tool_call`, `message` | True to approve, None |
| `APPROVAL_RECEIVED` | `on_approval_received` | — | None |
| `SYSTEM_PROMPT_READY` | `on_system_prompt_ready` | `system_prompt`, `session` | **str or None** |
| `FULL_PROMPT_READY` | `on_full_prompt_ready` | `prompt`, `llm_params`, `context` | **str or None** |

## Source file reference

| File | Purpose |
|------|---------|
| `autobot-backend/middleware/hooks.py` | `HookPoint` enum (24 values) + `HOOK_METADATA` |
| `autobot-backend/middleware/base.py` | `HookContext` dataclass + `Extension` base class with all 24 stub methods |
| `autobot-backend/middleware/manager.py` | `ExtensionManager` singleton + `invoke_with_transform`, `invoke_hook`, `invoke_until_handled`, `invoke_cancellable` |
| `autobot-backend/chat_workflow/llm_handler.py` | `_emit_system_prompt_ready()` and `_emit_full_prompt_ready()` call sites |
| `autobot-backend/chat_workflow/prompt_hooks_test.py` | Unit tests for both prompt hooks |
| `plugins/core-plugins/telemetry-prompt-middleware/plugin.py` | Reference implementation using Prometheus telemetry |
| `plugins/core-plugins/telemetry-prompt-middleware/plugin.json` | Plugin registration manifest |
