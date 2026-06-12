# AutoBot Hook System Developer Guide

**Introduced:** Issue #658  
**Invoker redesign:** Issue #4202  
**Prompt pipeline hooks:** Issue #3405

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Complete Hook Reference](#complete-hook-reference)
4. [Writing an Extension](#writing-an-extension)
5. [Adding a Hook to New Code](#adding-a-hook-to-new-code)
6. [Hook Lifecycle](#hook-lifecycle)
7. [Error Handling](#error-handling)
8. [Testing Hooks](#testing-hooks)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The hook system lets you modify or observe AutoBot's agent lifecycle at 25 defined points without touching core code. It follows the extension pattern from Agent Zero: you subclass `Extension`, override the methods you need, and register the instance with the global `ExtensionManager`. The core code calls `invoke_hook` (or the `HookInvoker` wrapper) at each lifecycle point; your methods are called in priority order.

### Extension vs. hook — the distinction

A **hook point** (`HookPoint` enum value) is a named location in the execution pipeline where extensions can participate. An **extension** (`Extension` subclass) is the object that contains the logic you want to run. One extension can respond to many hook points; one hook point can be handled by many extensions.

You never call hook methods directly. You register extensions; the runtime calls them.

---

## Architecture

### Core classes

| Class | File | Purpose |
|---|---|---|
| `HookPoint` | `middleware/hooks.py` | Enum of all 25 lifecycle points |
| `HookContext` | `middleware/base.py` | Shared data bag passed to every hook call |
| `Extension` | `middleware/base.py` | Base class for all extensions |
| `ExtensionManager` | `middleware/manager.py` | Registry and invocation coordinator (singleton) |
| `HookInvoker` | `middleware/hook_invoker.py` | Declarative invocation strategies (Issue #4202) |
| `InvocationMode` | `middleware/hook_invoker.py` | Enum of invocation strategies |

### HookContext

`HookContext` is a dataclass passed to every hook invocation. Extensions read input from it and write results back into it.

```python
from middleware.base import HookContext

ctx = HookContext(
    session_id="sess-abc123",   # always set by the caller
    message="User's message",   # set during message processing
    agent_id=None,              # set for hierarchical agents
    data={},                    # free-form dict for all hook data
)

# Read a value
prompt = ctx.get("prompt", "")

# Write a value (for chained transforms)
ctx.set("prompt", modified_prompt)

# Bulk update
ctx.merge({"key1": "v1", "key2": "v2"})

# Check presence
if ctx.has("tool_name"):
    ...

# Remove (pop)
old = ctx.remove("key")
```

The `data` dict is the primary channel. Keys are documented per-hook in the reference table below.

### ExtensionManager

The global singleton is accessed via `get_extension_manager()`. Extensions are kept in a list sorted by `priority` (lower number = runs first).

```python
from middleware.manager import get_extension_manager

manager = get_extension_manager()
manager.register(MyExtension())
```

Key manager methods:

| Method | Description |
|---|---|
| `register(ext)` | Add extension; returns `False` if name already registered |
| `unregister(name)` | Remove extension by name |
| `enable_extension(name)` | Set `enabled = True` |
| `disable_extension(name)` | Set `enabled = False` without removing |
| `load_extensions([classes])` | Instantiate and register a list of classes |
| `invoke_hook(hook, ctx)` | COLLECT — call all, return list of non-None results |
| `invoke_with_transform(hook, ctx, key)` | TRANSFORM — chain modifications to `ctx.data[key]` |
| `invoke_until_handled(hook, ctx)` | UNTIL_HANDLED — stop at first truthy result |
| `invoke_cancellable(hook, ctx)` | CANCELLABLE — stop and return `False` if any ext returns `False` |
| `get_statistics()` | Dict with counts and per-extension status |

### InvocationMode

Issue #4202 introduced `HookInvoker` to eliminate per-hook `_emit_*` wrapper boilerplate. Each hook has a registered `InvocationMode` that controls how multiple extension results are combined.

| Mode | Behaviour | Return type |
|---|---|---|
| `COLLECT` | All enabled extensions are called; non-None results gathered | `List[Any]` |
| `TRANSFORM` | Extensions are called in order; each can modify `ctx.data[key]`; final value returned | `Any` (type-checked if `expected_type` set) |
| `UNTIL_HANDLED` | Extensions called in order; first truthy result short-circuits the loop | `Optional[Any]` |
| `CANCELLABLE` | Extensions called in order; explicit `False` from any ext cancels and returns `False` | `bool` |

Using `HookInvoker`:

```python
from middleware import HookInvoker, HookInvocationConfig, InvocationMode, get_extension_manager
from middleware.base import HookContext
from middleware.hooks import HookPoint

manager = get_extension_manager()
invoker = HookInvoker(manager)

ctx = HookContext(session_id="sess-123", message="hello")

# Use the registered default config for the hook
results = await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

# Override the config inline
modified = await invoker.invoke(
    HookPoint.AFTER_PROMPT_BUILD,
    ctx,
    config=HookInvocationConfig(
        mode=InvocationMode.TRANSFORM,
        transform_key="prompt",
        expected_type=str,
    ),
)
```

The default configs registered in `HookInvoker._register_default_configs()` are the canonical invocation modes. See the reference table below for each hook's assigned mode.

---

## Complete Hook Reference

25 hook points across 7 groups. The "context key(s)" column lists the `ctx.data` keys the caller populates before invoking; "return type" is what your method should return.

### Message Preparation

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_MESSAGE_PROCESS` | `on_before_message_process` | COLLECT | `message` | `None` | Pre-process message, initialise per-session state |
| `BEFORE_PROMPT_BUILD` | `on_before_prompt_build` | COLLECT | `context` | `None` | Validate inputs before prompt construction |
| `AFTER_PROMPT_BUILD` | `on_after_prompt_build` | TRANSFORM (`prompt`) | `prompt` | `str \| None` | Append instructions; modify prompt before LLM call |

### LLM Interaction

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_LLM_CALL` | `on_before_llm_call` | CANCELLABLE | `prompt`, `llm_params` | `False` to cancel, `None` to continue | Rate limiting, content policy, cost gating |
| `DURING_LLM_STREAMING` | `on_during_llm_streaming` | COLLECT | `chunk`, `context` | `str \| None` | Real-time monitoring, stream filtering |
| `AFTER_LLM_RESPONSE` | `on_after_llm_response` | TRANSFORM (`response`) | `response`, `llm_params` | `str \| None` | Post-process full response before tool parsing |

### Prompt Pipeline (Issue #3405)

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `SYSTEM_PROMPT_READY` | `on_system_prompt_ready` | TRANSFORM (`system_prompt`) | `system_prompt`, `session` | `str \| None` | Inject per-tenant instructions into system prompt |
| `FULL_PROMPT_READY` | `on_full_prompt_ready` | TRANSFORM (`prompt`) | `prompt`, `llm_params`, `context` | `str \| None` | Final prompt modification before LLM receives it |

### Tool Execution

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_TOOL_PARSE` | `on_before_tool_parse` | TRANSFORM (`llm_response`) | `llm_response` (raw LLM text) | `str \| None` | Fix malformed tool call syntax before parsing |
| `BEFORE_TOOL_EXECUTE` | `on_before_tool_execute` | CANCELLABLE | `tool_call`, `tool_name` | `False` to cancel, `None` to continue | Approval gates, sandboxing, argument validation |
| `AFTER_TOOL_EXECUTE` | `on_after_tool_execute` | TRANSFORM (`tool_result`) | `tool_result` | `Any \| None` | Sanitise or enrich tool output |
| `TOOL_ERROR` | `on_tool_error` | COLLECT | `error` | `RepairableException \| None` | Convert third-party errors into retryable form |

### Continuation Loop

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_CONTINUATION` | `on_before_continuation` | CANCELLABLE | `prompt`, `context` | `False` to stop, `None` to continue | Iteration budget enforcement, loop guards |
| `AFTER_CONTINUATION` | `on_after_continuation` | TRANSFORM (`response`) | `response` | `str \| None` | Per-iteration response cleanup |
| `LOOP_COMPLETE` | `on_loop_complete` | TRANSFORM (`final_response`) | `final_response` | `str \| None` | Final response cleanup, metrics recording |

### Error Handling

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `REPAIRABLE_ERROR` | `on_repairable_error` | COLLECT | `error`, `suggestion` | `str \| None` | Improve error suggestion shown to LLM for retry |
| `CRITICAL_ERROR` | `on_critical_error` | COLLECT | `error` | `None` | Alerting, incident logging — observation only |

### Response

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_RESPONSE_SEND` | `on_before_response_send` | TRANSFORM (`response`) | `response` | `str \| None` | Secret masking, content filtering before WebSocket send |
| `AFTER_RESPONSE_SEND` | `on_after_response_send` | COLLECT | _(none)_ | `None` | Metrics, logging — side effects only |

### Session Lifecycle

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `SESSION_CREATE` | `on_session_create` | COLLECT | `session_id`, `context` | `None` | Initialise per-session resources |
| `SESSION_DESTROY` | `on_session_destroy` | COLLECT | `session_id`, `message_count`, `context` | `None` | Cleanup caches, flush buffers |

### Knowledge Integration

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `BEFORE_RAG_QUERY` | `on_before_rag_query` | TRANSFORM (`query`) | `query` | `str \| None` | Rewrite, expand or translate the search query |
| `AFTER_RAG_RESULTS` | `on_after_rag_results` | TRANSFORM (`results`) | `results`, `citations` | `List[Dict] \| None` | Re-rank, filter, or annotate retrieved documents |

### Approval Flow

| Hook | Method | Mode | Context key(s) | Return type | Typical use |
|---|---|---|---|---|---|
| `APPROVAL_REQUIRED` | `on_approval_required` | UNTIL_HANDLED | `tool_call`, `message` | `True` to auto-approve, `None` for normal flow | Automated approval for trusted tools or trusted users |
| `APPROVAL_RECEIVED` | `on_approval_received` | COLLECT | _(approval info)_ | `None` | Audit logging |

---

## Writing an Extension

### Step 1 — Subclass Extension

```python
# autobot-backend/middleware/builtin/my_extension.py

import logging
from typing import Optional
from middleware.base import Extension, HookContext

logger = logging.getLogger(__name__)


class RateLimitExtension(Extension):
    """Block LLM calls that exceed a per-session token budget."""

    name = "rate_limit"
    priority = 20  # Run early — before most other extensions

    def __init__(self, max_calls_per_minute: int = 30) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self._call_counts: dict = {}  # session_id -> list of timestamps

    async def on_before_llm_call(self, ctx: HookContext) -> Optional[bool]:
        """Return False to cancel when budget exceeded."""
        import time

        session_id = ctx.session_id
        now = time.monotonic()
        window = 60.0

        timestamps = self._call_counts.setdefault(session_id, [])
        # Evict old timestamps
        self._call_counts[session_id] = [t for t in timestamps if now - t < window]

        if len(self._call_counts[session_id]) >= self.max_calls_per_minute:
            logger.warning(
                "rate_limit: session %s exceeded %d calls/min",
                session_id,
                self.max_calls_per_minute,
            )
            return False  # Cancels the LLM call

        self._call_counts[session_id].append(now)
        return None  # Allow the call

    async def on_session_destroy(self, ctx: HookContext) -> None:
        """Clean up state when session ends."""
        self._call_counts.pop(ctx.session_id, None)
```

### Step 2 — Implement only the methods you need

The base `Extension` class provides no-op implementations for all 25 hook methods. Override only what is relevant. You do not need to call `super()`.

Key contracts:

- Return `None` (or nothing) to leave the current value unchanged.
- Return a new value from a TRANSFORM hook to replace `ctx.data[key]`.
- Return `False` from a CANCELLABLE hook to veto the operation.
- Return `True` from `on_approval_required` to auto-approve.
- For COLLECT hooks, return value is collected but not acted on unless the calling code inspects it.

### Step 3 — Register the extension

Register at application startup, after the `ExtensionManager` singleton is initialised.

```python
from middleware.manager import get_extension_manager
from middleware.builtin.my_extension import RateLimitExtension

manager = get_extension_manager()
manager.register(RateLimitExtension(max_calls_per_minute=20))
```

To load built-in extensions in bulk:

```python
from middleware.builtin.logging_extension import LoggingExtension
from middleware.builtin.secret_masking import SecretMaskingExtension

manager.load_extensions([LoggingExtension, SecretMaskingExtension])
```

### Complete working example — secret masking built-in

The `SecretMaskingExtension` at `middleware/builtin/secret_masking.py` is the canonical example. It:

- Sets `priority = 90` to run near the end (after most transforms are done).
- Implements `on_before_response_send` with TRANSFORM semantics: reads `ctx.data["response"]`, applies regex masking, returns the masked string.
- Provides `add_pattern()` for consumers to register additional patterns without subclassing.
- Tracks `total_masks_applied` via `get_statistics()`.

The `LoggingExtension` at `middleware/builtin/logging_extension.py` shows:

- `priority = 1` to capture the earliest view of every event.
- Stateful timing: stores `_session_start_times[session_id]` on `BEFORE_MESSAGE_PROCESS`, reads it on `LOOP_COMPLETE`.

---

## Adding a Hook to New Code

Follow this pattern when wiring a hook invocation into new backend code. Use the existing `_emit_before_llm_call` in `chat_workflow/llm_handler.py` as reference.

### Import

```python
from middleware.base import HookContext
from middleware.hooks import HookPoint
from middleware.manager import get_extension_manager
```

### COLLECT invocation (observation, no result needed)

```python
async def _emit_my_event(value: str, session_id: str) -> None:
    """Emit MY_EVENT hook.

    Args:
        value: The value being processed.
        session_id: Session identifier.
    """
    ctx = HookContext(
        session_id=session_id,
        data={"value": value},
    )
    await get_extension_manager().invoke_hook(HookPoint.MY_EVENT, ctx)
```

### CANCELLABLE invocation (veto pattern)

```python
async def _emit_before_my_action(payload: dict, session_id: str) -> bool:
    """Return False to cancel the action.

    Args:
        payload: The action payload.
        session_id: Session identifier.

    Returns:
        False if any extension vetoed, True otherwise.
    """
    ctx = HookContext(
        session_id=session_id,
        data={"payload": payload},
    )
    results = await get_extension_manager().invoke_hook(HookPoint.BEFORE_MY_ACTION, ctx)
    return not any(result is False for result in results)
```

Alternatively, use `invoke_cancellable` directly:

```python
should_proceed = await get_extension_manager().invoke_cancellable(
    HookPoint.BEFORE_MY_ACTION, ctx
)
if not should_proceed:
    logger.info("Action cancelled by hook")
    return
```

### TRANSFORM invocation (modify a value)

```python
async def _emit_transform_my_value(value: str, session_id: str) -> str:
    """Allow extensions to modify value.

    Args:
        value: Initial value.
        session_id: Session identifier.

    Returns:
        Possibly modified value.
    """
    ctx = HookContext(
        session_id=session_id,
        data={"my_value": value},
    )
    result = await get_extension_manager().invoke_with_transform(
        HookPoint.MY_TRANSFORM_HOOK, ctx, "my_value"
    )
    return result if isinstance(result, str) else value
```

### Adding a new HookPoint

1. Add the enum value to `HookPoint` in `middleware/hooks.py`:

```python
class HookPoint(Enum):
    # ... existing values ...
    MY_NEW_HOOK = auto()  # Method: on_my_new_hook
```

2. Add metadata to `HOOK_METADATA` in the same file:

```python
HookPoint.MY_NEW_HOOK: {
    "description": "Called when X happens",
    "can_modify": ["my_value"],
    "return_type": "Modified value or None",
},
```

3. Add the no-op stub to `Extension` in `middleware/base.py`:

```python
async def on_my_new_hook(self, ctx: HookContext) -> Optional[str]:
    """
    Called when X happens.

    Args:
        ctx: Hook context with data["my_value"].

    Returns:
        Modified value or None to keep unchanged.
    """
```

4. Register the default invocation config in `HookInvoker._register_default_configs()` in `middleware/hook_invoker.py`:

```python
self._configs[HookPoint.MY_NEW_HOOK] = HookInvocationConfig(
    mode=InvocationMode.TRANSFORM,
    transform_key="my_value",
    expected_type=str,
)
```

5. Update the hook count assertion in `extension_hooks_test.py`:

```python
def test_hook_count(self):
    assert len(HookPoint) == 26  # was 25
```

---

## Hook Lifecycle

The following shows the order hooks fire for a typical chat message that triggers one tool call:

```
Incoming message
      |
      v
BEFORE_MESSAGE_PROCESS         [COLLECT]
      |
      v
BEFORE_PROMPT_BUILD            [COLLECT]
      |
      v
  (knowledge retrieval)
      |
BEFORE_RAG_QUERY               [TRANSFORM: query]
      |
      v
  (ChromaDB search)
      |
AFTER_RAG_RESULTS              [TRANSFORM: results]
      |
      v
AFTER_PROMPT_BUILD             [TRANSFORM: prompt]
      |
      v
SYSTEM_PROMPT_READY            [TRANSFORM: system_prompt]
      |
      v
FULL_PROMPT_READY              [TRANSFORM: prompt]
      |
      v
  [continuation loop starts]
      |
BEFORE_CONTINUATION            [CANCELLABLE]  ------> stop loop if False
      |
      v
BEFORE_LLM_CALL                [CANCELLABLE]  ------> cancel call if False
      |
      v
  (LLM call + streaming)
      |
DURING_LLM_STREAMING           [COLLECT]      (fired per chunk)
      |
      v
AFTER_LLM_RESPONSE             [TRANSFORM: response]
      |
      v
BEFORE_TOOL_PARSE              [TRANSFORM: llm_response]
      |
      v
  (parse tool calls from response)
      |
BEFORE_TOOL_EXECUTE            [CANCELLABLE]  ------> cancel tool if False
      |
      v
  (tool runs)
      |                         \
AFTER_TOOL_EXECUTE             [TRANSFORM: tool_result]
      |                          \
      |                    TOOL_ERROR [COLLECT]   (if tool raised)
      |
AFTER_CONTINUATION             [TRANSFORM: response]
      |
      v
  [loop again if LLM wants more tools]
      |
LOOP_COMPLETE                  [TRANSFORM: final_response]
      |
      v
BEFORE_RESPONSE_SEND           [TRANSFORM: response]
      |
      v
  (WebSocket send)
      |
AFTER_RESPONSE_SEND            [COLLECT]

Session boundaries (fired independently of message flow):
  SESSION_CREATE               [COLLECT]   -- on new WebSocket session
  SESSION_DESTROY              [COLLECT]   -- on session close / timeout

Error paths (fired instead of / alongside normal flow):
  REPAIRABLE_ERROR             [COLLECT]   -- retryable error during loop
  CRITICAL_ERROR               [COLLECT]   -- unrecoverable error

Approval path (inserted before BEFORE_TOOL_EXECUTE when tool needs approval):
  APPROVAL_REQUIRED            [UNTIL_HANDLED]   -- auto-approve check
  APPROVAL_RECEIVED            [COLLECT]         -- after user approves
```

---

## Error Handling

### Extension errors are non-fatal by design

Both `Extension.on_hook()` and `ExtensionManager.invoke_hook()` catch all exceptions from extension methods and log them without re-raising. This is intentional: a misbehaving extension must never crash a user's session.

From `middleware/base.py`:

```python
try:
    return await method(context)
except Exception as e:
    logger.error(
        "[Issue #658] Extension %s error on %s: %s",
        self.name,
        hook.name,
        str(e),
    )
    return None  # Not re-raised
```

From `middleware/manager.py` (`invoke_hook`):

```python
except Exception as e:
    logger.error(
        "[Issue #658] Extension %s failed on %s: %s",
        extension.name,
        hook.name,
        str(e),
    )
    # Continue with other extensions
```

### What this means for you

- An extension that raises will have its result treated as `None`.
- For TRANSFORM hooks, this means the value is not modified by the failing extension; subsequent extensions still run with the current (unmodified) value.
- For CANCELLABLE hooks, a raised exception is not treated as `False` — the operation proceeds.
- Errors appear in `backend-error.log` tagged with `[Issue #658]`.

### The `CRITICAL_ERROR` and `REPAIRABLE_ERROR` hooks

These hooks are fired by the core pipeline when it catches errors — they are not about extension errors. Use them to add alerting or improve error messages:

```python
async def on_critical_error(self, ctx: HookContext) -> None:
    error = ctx.get("error")
    # Send to your alerting system — do not raise here
    await send_alert(str(error))
```

---

## Testing Hooks

### Resetting the singleton between tests

`reset_extension_manager()` wipes the global singleton. Call it in `setup_method` or a fixture:

```python
from middleware.manager import reset_extension_manager

class TestMyExtension:
    def setup_method(self):
        reset_extension_manager()
```

### Testing that a hook fires and modifies a value

```python
import pytest
from middleware.base import Extension, HookContext
from middleware.hooks import HookPoint
from middleware.manager import ExtensionManager

class TestRateLimitExtension:
    @pytest.mark.asyncio
    async def test_cancels_when_budget_exceeded(self):
        from middleware.builtin.my_extension import RateLimitExtension

        manager = ExtensionManager()
        ext = RateLimitExtension(max_calls_per_minute=2)
        manager.register(ext)

        ctx = HookContext(session_id="sess-test", data={"prompt": "hi", "llm_params": {}})

        # First two calls: allowed
        r1 = await manager.invoke_hook(HookPoint.BEFORE_LLM_CALL, ctx)
        r2 = await manager.invoke_hook(HookPoint.BEFORE_LLM_CALL, ctx)
        # Third call: should veto
        r3 = await manager.invoke_hook(HookPoint.BEFORE_LLM_CALL, ctx)

        assert False not in r1
        assert False not in r2
        assert False in r3
```

### Testing transform chaining

Based on the pattern in `extension_hooks_test.py`:

```python
@pytest.mark.asyncio
async def test_transform_chains(self):
    class AppendExtension(Extension):
        def __init__(self, suffix: str, name: str, priority: int):
            self.suffix = suffix
            self.name = name
            self.priority = priority

        async def on_after_prompt_build(self, ctx: HookContext):
            return ctx.get("prompt", "") + self.suffix

    manager = ExtensionManager()
    manager.register(AppendExtension("-A", "ext1", 10))
    manager.register(AppendExtension("-B", "ext2", 20))

    ctx = HookContext()
    ctx.set("prompt", "base")

    result = await manager.invoke_with_transform(
        HookPoint.AFTER_PROMPT_BUILD, ctx, "prompt"
    )

    assert result == "base-A-B"
```

### Testing that errors do not propagate

```python
@pytest.mark.asyncio
async def test_failing_extension_does_not_crash(self):
    class BrokenExtension(Extension):
        name = "broken"

        async def on_before_message_process(self, ctx: HookContext):
            raise RuntimeError("intentional failure")

    manager = ExtensionManager()
    manager.register(BrokenExtension())

    ctx = HookContext(session_id="sess-1")
    # Must not raise
    results = await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
    assert results == []
```

### Test file locations

Unit tests for the extension system live in the `middleware/` directory alongside the modules they test:

- `autobot-backend/middleware/extension_hooks_test.py` — HookPoint, HookContext, Extension, ExtensionManager, built-in extensions
- `autobot-backend/middleware/hook_invoker_test.py` — HookInvoker, InvocationMode, HookInvocationConfig

Follow the co-location rule: tests for a new extension go in the same directory as the extension file.

---

## Troubleshooting

### Hook not firing

1. Verify the extension is registered: `get_extension_manager().list_extensions()` should include its name.
2. Check `extension.enabled` is `True`. The manager skips disabled extensions silently.
3. Confirm the method name matches the hook exactly. The dispatch in `Extension.on_hook()` derives the method name as `f"on_{hook.name.lower()}"`. For `HookPoint.BEFORE_LLM_CALL` the method must be `on_before_llm_call`.
4. Verify the hook is actually wired in the calling code. Search `grep -rn "HookPoint.YOUR_HOOK"` in `autobot-backend/` to confirm an `invoke_hook` call exists.

### Hook fires but return value is ignored

1. Check the `InvocationMode` for the hook in `HookInvoker._register_default_configs()`. A COLLECT hook does not apply your return value automatically — the calling code must inspect the results list.
2. For TRANSFORM hooks, verify the `transform_key` matches the key you used in `ctx.set()` / the key the caller placed in `ctx.data`.
3. Returning a value other than `None` from a COLLECT-mode hook adds it to the results list; it does not modify `ctx.data`. Use `ctx.set(key, value)` explicitly if you want downstream extensions or the caller to see it.

### Wrong return type warning in logs

TRANSFORM mode logs a warning when the returned type does not match `expected_type`:

```
[Issue #4202] AFTER_PROMPT_BUILD returned int, expected str
```

Ensure your hook method returns the correct type or `None`. Returning an integer where `str` is expected causes `invoke_transform` to log but still store the value — the caller's `isinstance` guard in the `_emit_*` wrapper will then fall back to the original.

### session_id is empty string

The `session_id` field defaults to `""`. If your extension relies on it for keying state, add a guard:

```python
if not ctx.session_id:
    return None  # cannot proceed without session identity
```

The callers in `chat_workflow/llm_handler.py` and `chat_workflow/session_handler.py` always populate `session_id` — an empty value indicates your extension is being called from a test or an unwired code path.

### Duplicate extension name rejected

`ExtensionManager.register()` returns `False` and logs a warning when an extension with the same `name` is already registered. Assign distinct `name` class attributes to each extension. The built-in names `"logging"` and `"secret_masking"` are reserved.

### Extension priority conflicts

Two extensions with the same `priority` are ordered by registration order within that priority bucket (Python `list.sort` is stable). If ordering within a priority level matters, assign distinct values.
