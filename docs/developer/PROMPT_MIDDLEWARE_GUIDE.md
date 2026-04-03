# Prompt Middleware Guide

> Issue #3405 — `ON_SYSTEM_PROMPT_READY` and `ON_FULL_PROMPT_READY` plugin hooks

This guide explains how to intercept and modify LLM prompts at two points in
the chat pipeline using the extension hook system.

---

## Overview

AutoBot's chat pipeline assembles prompts in two stages:

1. **System prompt** — personality preamble + base system prompt + language
   instruction.  Built inside `LLMHandlerMixin._get_system_prompt()`.
2. **Full prompt** — system prompt + knowledge context (RAG) + conversation
   history + current user message.  Built inside
   `LLMHandlerMixin._build_full_prompt()`.

After each stage the pipeline fires a hook that lets registered extensions
inspect and optionally rewrite the output before it reaches the LLM.

---

## Hook signatures

### `HookPoint.ON_SYSTEM_PROMPT_READY`

Fired after `_get_system_prompt()` returns.

| Context key | Type | Description |
|---|---|---|
| `system_prompt` | `str` | Assembled system prompt |
| `session` | `WorkflowSession` | Current session instance |

**Return value:** Return a `str` to replace the system prompt.  Return `None`
to leave it unchanged.  The pipeline uses the last non-`None` value from all
registered extensions (pipeline chaining via `invoke_with_transform`).

### `HookPoint.ON_FULL_PROMPT_READY`

Fired after `_build_full_prompt()` returns.

| Context key | Type | Description |
|---|---|---|
| `prompt` | `str` | Fully assembled prompt |
| `llm_params` | `dict` | `{"model": ..., "endpoint": ...}` |
| `context` | `dict` | `{"session_id": ..., "message": ...}` |

**Return value:** Return a `str` to replace the full prompt.  Return `None`
to leave it unchanged.

---

## Graceful degradation

Both hooks are no-ops when no extension is registered.  A failing extension is
logged at `ERROR` level but does **not** propagate an exception — the original
prompt is returned unchanged.  This guarantees the chat pipeline always
completes even if middleware is misconfigured.

---

## Writing an extension

Extensions live in `extensions/base.py`.  Override the hook method that
corresponds to the `HookPoint` name, converted to `on_<hook_name_lower>`.

Because the new hooks already contain the prefix `on_`, the method names are:

- `on_on_system_prompt_ready` — for `ON_SYSTEM_PROMPT_READY`
- `on_on_full_prompt_ready` — for `ON_FULL_PROMPT_READY`

```python
from extensions.base import Extension, HookContext
from typing import Optional


class MyPromptExtension(Extension):
    name = "my_prompt_extension"
    priority = 150  # lower = runs first

    async def on_on_full_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        prompt = ctx.get("prompt", "")
        # append a custom hint
        return prompt + "\n\n[Always respond in bullet points.]"
```

Register the extension on application startup:

```python
from extensions.manager import get_extension_manager
from my_module import MyPromptExtension

get_extension_manager().register(MyPromptExtension())
```

---

## Worked example: Telemetry Prompt Middleware

`plugins/core-plugins/telemetry-prompt-middleware/plugin.py` ships as a
reference implementation.  It queries Prometheus for the current cluster-wide
CPU usage.  When usage exceeds a configurable threshold the plugin appends a
one-sentence hint asking the model to keep its response concise, reducing
time-to-first-token on a loaded host.

### How it works

```
LLM pipeline
  |
  +-- _build_full_prompt()
  |
  +-- ON_FULL_PROMPT_READY fires
        |
        +-- TelemetryPromptMiddleware.on_on_full_prompt_ready()
              |
              +-- GET /api/v1/query  (Prometheus, 2 s timeout)
              |
              +-- CPU > threshold?
                    yes -> return prompt + hint
                    no  -> return None  (no change)
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `PROMETHEUS_URL` (env) | `""` | Prometheus base URL |
| `TELEMETRY_CPU_THRESHOLD` (env) | `80` | CPU % threshold |
| `cpu_threshold_pct` (plugin config) | `80` | Same, via plugin config API |
| `prometheus_url` (plugin config) | `""` | Same, overrides env var |

If `PROMETHEUS_URL` is not set the plugin silently skips hint injection.

### Registering the plugin

```python
import os
from extensions.manager import get_extension_manager
from plugins.core_plugins.telemetry_prompt_middleware.plugin import (
    TelemetryPromptMiddleware,
)

plugin = TelemetryPromptMiddleware(
    config={
        "prometheus_url": os.getenv("PROMETHEUS_URL", ""),
        "cpu_threshold_pct": 80,
    }
)
get_extension_manager().register(plugin)
```

Or load it via the Plugin Manager API (POST `/plugins/telemetry-prompt-middleware/load`).

---

## Testing

Unit tests for the hooks live in:

```
autobot-backend/chat_workflow/prompt_hooks_test.py
```

Run them with:

```bash
cd autobot-backend
pytest chat_workflow/prompt_hooks_test.py -v
```

The test suite covers:

- Both `HookPoint` members exist.
- `ON_SYSTEM_PROMPT_READY` fires with the correct `system_prompt` arg.
- `ON_FULL_PROMPT_READY` fires with `prompt`, `llm_params`, and `context`.
- A returned `str` replaces the prompt.
- `None` return keeps the original prompt unchanged.
- An extension that raises an exception does not crash the pipeline.

---

## Related

- `extensions/hooks.py` — `HookPoint` enum
- `extensions/base.py` — `Extension` base class with hook methods
- `extensions/manager.py` — `ExtensionManager` and `invoke_with_transform`
- `chat_workflow/llm_handler.py` — hook call sites
- `docs/developer/PLUGIN_SDK.md` — Plugin SDK lifecycle docs
- Issue #3405
