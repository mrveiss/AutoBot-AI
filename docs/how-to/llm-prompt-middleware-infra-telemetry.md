# Implement a custom middleware in AutoBot to intercept and modify LLM prompts based on real-time infrastructure telemetry

AutoBot's extension system exposes two hook points in the chat pipeline where a **middleware** (an `Extension` subclass — see [`plugin-vs-extension-vs-skill.md`](../developer/plugin-vs-extension-vs-skill.md)) can intercept the assembled prompt and inject dynamic content — for example, a concise-response hint when CPU load is high.  No core code changes are needed; write an `Extension` subclass and register it explicitly with `ExtensionManager` — **there is no manifest-driven loader for middleware**. `HookPoint.FULL_PROMPT_READY` and `HookPoint.SYSTEM_PROMPT_READY` are dispatched exclusively by `middleware.manager.ExtensionManager`; they are not in the plugin system's `HOOK_REGISTRY`, so a `plugins/**/plugin.json` manifest can never make one of these fire (#14280).

## Hook points

| Hook | When it fires | What you can modify |
|------|--------------|---------------------|
| `HookPoint.SYSTEM_PROMPT_READY` | After the base system prompt is built in `_get_system_prompt()` | System prompt string |
| `HookPoint.FULL_PROMPT_READY` | After the full prompt (system + knowledge + conversation) is assembled | Full prompt string |

Return a `str` from the hook method to replace the prompt; return `None` to leave it unchanged.

## Minimal example — inject CPU load hint

```python
"""
Custom LLM prompt middleware that intercepts prompts and appends a
concise-response hint when CPU load exceeds a configurable threshold.

Place this file in autobot-backend/middleware/builtin/ and register it
explicitly with ExtensionManager (see "Registering the middleware" below) —
middleware has no manifest-driven discovery.
"""
import asyncio
import logging
import os
from typing import Optional

import httpx

from middleware.base import Extension, HookContext

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
CPU_THRESHOLD = float(os.getenv("PROMPT_CPU_THRESHOLD_PCT", "80"))


class TelemetryPromptMiddleware(Extension):
    """Intercept LLM prompts and modify them based on real-time infra telemetry.

    Registers the FULL_PROMPT_READY hook.  When CPU usage is above the
    threshold, appends a brief hint asking the model to prioritise concise
    output — reducing token usage during high-load periods.
    """

    name = "telemetry_prompt_middleware"
    priority = 50  # run before default (100) extensions

    async def on_full_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Intercept the assembled prompt and inject infra telemetry hints.

        Args:
            ctx: HookContext with ctx.data["prompt"], ctx.data["llm_params"],
                 ctx.data["context"].

        Returns:
            Modified prompt string, or None to leave unchanged.
        """
        prompt = ctx.get("prompt", "")
        if not prompt:
            return None

        cpu = await self._fetch_cpu_percent()
        if cpu is None:
            return None  # Prometheus unreachable — no modification

        if cpu >= CPU_THRESHOLD:
            hint = (
                f"\n\n[System note: CPU load is {cpu:.0f}% — "
                "please prioritise a concise response.]"
            )
            logger.debug(
                "[telemetry-middleware] CPU %.0f%% ≥ threshold %.0f%% — injecting hint",
                cpu, CPU_THRESHOLD,
            )
            return prompt + hint

        return None  # load is fine — pass prompt through unchanged

    async def on_system_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Optionally modify the system prompt based on infrastructure state.

        Args:
            ctx: HookContext with ctx.data["system_prompt"] and ctx.data["session"].

        Returns:
            Modified system prompt string, or None to leave unchanged.
        """
        # Example: append a memory-pressure warning to the system prompt
        memory_pct = await self._fetch_memory_percent()
        if memory_pct is not None and memory_pct >= 90:
            system_prompt = ctx.get("system_prompt", "")
            return system_prompt + "\n[Memory pressure is high — avoid large data structures.]"
        return None

    async def _fetch_cpu_percent(self) -> Optional[float]:
        """Query Prometheus for current CPU usage percentage."""
        query = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
        return await self._prometheus_query(query)

    async def _fetch_memory_percent(self) -> Optional[float]:
        """Query Prometheus for current memory usage percentage."""
        query = (
            "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
        )
        return await self._prometheus_query(query)

    async def _prometheus_query(self, query: str) -> Optional[float]:
        """Run an instant PromQL query; return the scalar value or None."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(
                    f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}
                )
                r.raise_for_status()
                results = r.json().get("data", {}).get("result", [])
                if results:
                    return float(results[0]["value"][1])
        except Exception as exc:
            logger.debug("[telemetry-middleware] Prometheus query failed: %s", exc)
        return None
```

## Registering the middleware

Middleware has no manifest-driven loader — a `plugins/**/plugin.json` file is
the **Plugin** system's contract (`autobot_shared/plugin_sdk/loader.py`,
`kind: "plugin"`), and that loader is never consulted when
`HookPoint.FULL_PROMPT_READY` fires. Shipping a `plugin.json` next to an
`Extension` subclass is exactly the #14280 bug: the manifest gets discovered,
`PluginLoader` finds no `BasePlugin` subclass in the module, logs "No plugin
class found in module", and the middleware never runs.

Register the class explicitly, alongside the other built-in middleware in
`autobot-backend/middleware/builtin/__init__.py` and
`initialization/lifespan.py`'s `_init_builtin_extensions` (the actual
registration point every hook call site reads from, via
`middleware.manager.get_extension_manager()`):

```python
# autobot-backend/middleware/builtin/__init__.py
from middleware.builtin.telemetry_prompt_middleware import TelemetryPromptMiddleware

__all__ = [..., "TelemetryPromptMiddleware"]
```

```python
# autobot-backend/initialization/lifespan.py, inside _init_builtin_extensions
from middleware.builtin import TelemetryPromptMiddleware
from middleware.manager import get_extension_manager

manager = get_extension_manager()
manager.register(TelemetryPromptMiddleware())
```

A one-off or third-party middleware that cannot be added to the built-in
list can still be registered the same way from any code that runs during
startup:

```python
from middleware.manager import get_extension_manager
from my_module import TelemetryPromptMiddleware

get_extension_manager().register(TelemetryPromptMiddleware())
```

## How the hook dispatch works

The extension manager calls `on_{hook_name}` on every registered extension for that hook point.  The return value of the **last** extension that returns a non-`None` string replaces the prompt.  If no extension returns a string, the original prompt is used unchanged.

```python
# autobot-backend/chat_workflow/llm_handler.py (simplified)

system_prompt = self._get_system_prompt(session)
# Hook fires here — extensions can modify system_prompt
system_prompt = await _emit_system_prompt_ready(system_prompt, session)

full_prompt = self._build_full_prompt(system_prompt, knowledge, conversation)
# Hook fires here — extensions can modify full_prompt
full_prompt = await _emit_full_prompt_ready(full_prompt, llm_params, context)
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus server base URL |
| `PROMPT_CPU_THRESHOLD_PCT` | `80` | CPU % above which the hint is injected |

## Testing the middleware

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from middleware.manager import get_extension_manager, reset_extension_manager
from chat_workflow.llm_handler import _emit_full_prompt_ready


@pytest.fixture(autouse=True)
def reset():
    reset_extension_manager()
    yield
    reset_extension_manager()


@pytest.mark.asyncio
async def test_hint_injected_when_cpu_high():
    from middleware.builtin.telemetry_prompt_middleware import TelemetryPromptMiddleware

    mw = TelemetryPromptMiddleware()
    with patch.object(mw, "_fetch_cpu_percent", AsyncMock(return_value=95.0)):
        get_extension_manager().register(mw)
        result = await _emit_full_prompt_ready("You are AutoBot.", {}, {})

    assert "CPU load is 95%" in result


@pytest.mark.asyncio
async def test_no_modification_when_cpu_low():
    from middleware.builtin.telemetry_prompt_middleware import TelemetryPromptMiddleware

    mw = TelemetryPromptMiddleware()
    with patch.object(mw, "_fetch_cpu_percent", AsyncMock(return_value=40.0)):
        get_extension_manager().register(mw)
        original = "You are AutoBot."
        result = await _emit_full_prompt_ready(original, {}, {})

    assert result == original
```

## Architecture reference

- **Hook definitions** — `autobot-backend/middleware/hooks.py` (`HookPoint.SYSTEM_PROMPT_READY`, `HookPoint.FULL_PROMPT_READY`)
- **Extension base class** — `autobot-backend/middleware/base.py`
- **Hook call sites** — `autobot-backend/chat_workflow/llm_handler.py`
- **Reference middleware** — `autobot-backend/middleware/builtin/telemetry_prompt_middleware.py` (moved from `plugins/core-plugins/telemetry-prompt-middleware/plugin.py` by #14280; that directory now holds only a `kind: "extension"` manifest for capability/config-schema documentation, excluded from `PluginLoader.discover_plugins`)
- **Full developer guide** — `docs/developer/PROMPT_MIDDLEWARE_GUIDE.md`
