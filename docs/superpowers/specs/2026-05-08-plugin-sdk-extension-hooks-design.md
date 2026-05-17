# Plugin SDK — Extension-Point Hooks (API + Celery)

**Date:** 2026-05-08
**Author:** mrveiss
**Status:** Draft (pending review)
**Issue:** #6970
**Discovered during:** ARC Prize plugin design ([`docs/superpowers/specs/2026-05-05-arc-prize-plugin-design.md`](2026-05-05-arc-prize-plugin-design.md))

---

## Problem Statement

`HookRegistry` ([`autobot_shared/plugin_sdk/hooks.py`](../../autobot_shared/plugin_sdk/hooks.py)) has full register/dispatch machinery for event-style hooks (`ON_STARTUP`, `ON_AGENT_EXECUTE`, `ON_KB_SEARCH`, etc.). What it does **not** have:

1. Canonical hook **names** for extension points (mounting routers, registering Celery tasks, mounting frontend routes).
2. Host-side **dispatch sites** for those extension points. Even if a plugin registered a callback under `Hook.CUSTOM` with name `"api_router_register"`, nothing in FastAPI startup, Celery worker init, or the Vite build invokes it.

Concrete consequence: the upcoming ARC Prize plugin needs to mount a FastAPI router at `/api/arc` and register Celery tasks for the run-execution lifecycle. With no extension-point hooks, every plugin that has ever needed this has either monkey-patched the host or forced manual wiring in core code. That fragments the plugin contract and turns plugins into core-coupled modules.

## Goals

- Define two canonical extension-point hooks: `API_ROUTER_REGISTER` and `CELERY_TASK_REGISTER`.
- Wire host-side dispatch sites so registered handlers actually fire at the right runtime moment (FastAPI lifespan startup, Celery `worker_init` signal).
- Provide a uniform handler contract: plugin authors always write `async def`. The SDK bridges async-to-sync internally where the host runtime is sync (Celery signals).
- Surface dispatch failures loudly (logged at ERROR, plugin marked `status=ERROR`) without aborting host startup.
- Stay 100% backward compatible with the 5 in-tree plugins (none use these hooks).

## Non-Goals

- Frontend extension hooks (`FRONTEND_ROUTE_REGISTER`, `PLUGIN_SETTINGS_VIEW_REGISTER`) — deferred; depends on #6972 (frontend module mounting). Tracked as a follow-up issue.
- Hook ordering / priority. First-registered first-called is good enough.
- Route-collision detection at `API_ROUTER_REGISTER` time. Filed as follow-up if it becomes a problem.
- Migrating existing plugins to use the new hooks. None of the in-tree plugins need them today.
- Public hook discovery / introspection endpoint.

---

## Design

### 1. Extension-point hook contract

Two new entries on the existing `Hook` enum in `autobot_shared/plugin_sdk/hooks.py`:

```python
class Hook(str, Enum):
    # ... existing event-style hooks unchanged ...

    # Extension-point hooks (this PR)
    API_ROUTER_REGISTER = "api_router_register"
    CELERY_TASK_REGISTER = "celery_task_register"
```

**Handler contract — always async, regardless of host runtime:**

| Hook | Handler signature | When fired |
| --- | --- | --- |
| `API_ROUTER_REGISTER` | `async def(app: FastAPI) -> None` | FastAPI lifespan startup, after core routers mount, before yield |
| `CELERY_TASK_REGISTER` | `async def(celery_app: Celery) -> None` | Celery `worker_init` signal (sync), via `AsyncSyncBridge` |

**Push pattern.** Plugins receive the live runtime instance and call its registration methods directly:

```python
async def on_api_router_register(self, app: FastAPI) -> None:
    app.include_router(my_router, prefix="/api/myplugin", tags=["MyPlugin"])

async def on_celery_task_register(self, celery_app: Celery) -> None:
    celery_app.task(name="myplugin.do_thing")(my_task_fn)
```

**Failure isolation.** Plugin handler raises → the dispatcher (`PluginManager.dispatch_extension_point`, see Section 7) catches, logs at ERROR with plugin name, marks plugin `status=ERROR`, and continues with the next plugin. Host startup completes normally. `HookRegistry.call_hook` is **not** modified — event-style hooks keep their existing log-and-ignore semantics.

### 2. `BasePlugin.register_extension_point` sugar

Added to `autobot_shared/plugin_sdk/base.py`:

```python
def register_extension_point(self, hook: Hook, callback) -> None:
    """Register a handler for an extension-point hook.

    All extension-point handlers MUST be async (`async def`). The SDK
    invokes them at the host's lifecycle moment (FastAPI lifespan or
    Celery worker init). Plugin authors never need to know which underlying
    runtime is sync vs async — the host bridges internally.

    Args:
        hook: A Hook enum value (e.g. Hook.API_ROUTER_REGISTER)
        callback: An async function matching the hook's signature

    Raises:
        TypeError: if callback is not a coroutine function
    """
    if not asyncio.iscoroutinefunction(callback):
        raise TypeError(
            f"Extension-point handler for {hook.value} must be async. "
            f"Plugin '{self.manifest.name}' provided a sync callable."
        )
    HookRegistry().register_hook(
        hook.value, callback, plugin_name=self.manifest.name
    )
```

This avoids plugins importing `HookRegistry` directly, and rejects sync handlers loudly at registration time (not at dispatch time).

### 3. `AsyncSyncBridge` — internal async→sync adapter

New file: `autobot_shared/plugin_sdk/async_bridge.py`. Singleton owning a daemon-thread event loop. Plugin authors never see this; only host runtimes do.

```python
import asyncio
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AsyncSyncBridge:
    """Singleton bridge for invoking async code from sync host contexts.

    Owns a daemon-thread event loop running forever. Sync callers submit
    coroutines via run_coro(); the call blocks until the coroutine completes
    (or raises). The daemon thread is auto-killed at process exit.

    Plugin authors never touch this — only host runtimes (e.g., Celery
    signal handlers) do.
    """

    _instance: Optional["AsyncSyncBridge"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="AsyncSyncBridge",
        )
        self._thread.start()
        logger.debug("AsyncSyncBridge initialized — daemon loop thread started")

    def run_coro(self, coro) -> Any:
        """Submit coro to the bridge loop and block until it completes.

        Exceptions raised in the coro propagate to the caller.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    @classmethod
    def reset_for_tests(cls) -> None:
        """Test-only — tear down the singleton + thread for clean test state."""
        with cls._lock:
            if cls._instance is not None and cls._instance._loop.is_running():
                cls._instance._loop.call_soon_threadsafe(cls._instance._loop.stop)
                cls._instance._thread.join(timeout=2.0)
            cls._instance = None
```

**Why singleton + persistent loop and not `asyncio.run` per call:**

1. No setup/teardown churn per call (matters if hooks are dispatched repeatedly).
2. No risk of "loop is already running" `RuntimeError` if Celery later runs in an async-aware mode.
3. Future host runtimes (any sync context) reuse the same bridge.
4. Daemon thread is auto-reaped at process exit — no shutdown plumbing needed.

### 4. Dispatch site 1 — FastAPI lifespan

Modify `autobot-backend/initialization/lifespan.py`. Inside the lifespan async-context manager, after Phase-1 critical services are initialized, dispatch the API hook via the new `PluginManager.dispatch_extension_point` method (Section 7):

```python
from plugin_sdk.hooks import Hook
from plugin_sdk.plugin_manager import get_plugin_manager  # see Section 6

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing Phase 1 startup ...

    # Plugin extension-point dispatch (Issue #6970)
    plugin_manager = get_plugin_manager()
    if not plugin_manager.is_started:
        await plugin_manager.startup()  # discovers + loads plugins
    await plugin_manager.dispatch_extension_point(Hook.API_ROUTER_REGISTER, app)

    # ... existing Phase 2 background services ...

    yield

    # ... existing shutdown ...
```

**Position rationale:** AFTER core routers mount but BEFORE yield (i.e., before requests are accepted). This guarantees plugin routes are present in the app before the first request lands.

### 5. Dispatch site 2 — Celery `worker_init`

Modify `autobot-backend/celery_app.py`. After the `celery_app = Celery(...)` instantiation, register a `worker_init` signal handler that uses `AsyncSyncBridge` to invoke the async dispatcher:

```python
from celery.signals import worker_init
from plugin_sdk.async_bridge import AsyncSyncBridge
from plugin_sdk.hooks import Hook
from plugin_sdk.plugin_manager import get_plugin_manager


@worker_init.connect
def on_worker_init(sender, **kwargs):
    """Dispatch CELERY_TASK_REGISTER hook at worker startup.

    Celery's worker_init signal is sync by Celery's design. We bridge to
    the async dispatcher via AsyncSyncBridge so plugin authors write
    uniform `async def` handlers.

    Issue #6970.
    """
    plugin_manager = get_plugin_manager()

    async def _dispatch():
        if not plugin_manager.is_started:
            await plugin_manager.startup()
        await plugin_manager.dispatch_extension_point(
            Hook.CELERY_TASK_REGISTER, sender.app
        )

    AsyncSyncBridge().run_coro(_dispatch())
```

The `_dispatch` coroutine wraps both the plugin manager bootstrap and the dispatch so the entire registration is one atomic submit-and-block.

### 6. `get_plugin_manager()` accessor

If not already present in `autobot-backend/plugin_manager.py`, add:

```python
_plugin_manager_singleton: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Return the shared PluginManager singleton."""
    global _plugin_manager_singleton
    if _plugin_manager_singleton is None:
        _plugin_manager_singleton = PluginManager(plugin_dirs=_default_plugin_dirs())
    return _plugin_manager_singleton
```

This mirrors the existing `get_plugin_loader()` pattern in the same file. **Plan resolves whether the accessor exists today via grep before implementation.**

### 7. Failure semantics — `PluginManager.dispatch_extension_point`

Extension-point hooks are dispatched through a NEW method on `PluginManager`, NOT through `HookRegistry.call_hook` directly. This isolates the per-plugin status-tracking behavior to one-time startup hooks; event-style hooks (`ON_KB_DOCUMENT_ADDED`, `ON_AGENT_EXECUTE`, etc.) keep their existing semantics where a transient exception is logged and ignored without flipping plugin status.

```python
# autobot_shared/plugin_sdk/plugin_manager.py

class PluginManager:
    # ... existing fields/methods ...

    async def dispatch_extension_point(self, hook: Hook, *args, **kwargs) -> None:
        """Dispatch an extension-point hook with per-plugin status tracking.

        Use for one-time startup hooks (API_ROUTER_REGISTER, CELERY_TASK_REGISTER)
        where a handler failure means the plugin is broken for this run.
        Event-style hooks should continue to use HookRegistry.call_hook directly.

        On handler exception:
          - Log at ERROR with plugin name + traceback
          - Mark plugin.status = PluginStatus.ERROR
          - Continue dispatching remaining plugins (failure isolation)

        Args:
            hook: A Hook enum value (must be an extension-point hook).
            *args, **kwargs: Forwarded to each handler.
        """
        registry = self._hook_registry
        plugin_registry = self._registry
        handlers = registry._hooks.get(hook.value, [])
        for cb_info in handlers:
            cb = cb_info["callback"]
            plugin_name = cb_info["plugin_name"]
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(*args, **kwargs)
                else:
                    cb(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "Plugin '%s' failed to handle %s: %s",
                    plugin_name, hook.value, e, exc_info=True,
                )
                plugin = plugin_registry.get_plugin(plugin_name)
                if plugin is not None:
                    plugin.status = PluginStatus.ERROR
```

**Why a new method instead of modifying `call_hook`:**

- `HookRegistry.call_hook` continues to be the right primitive for event-style hooks, where a handler raising for a single bad input shouldn't permanently mark the plugin as ERROR.
- Extension-point hooks are categorically different (one-time startup; failure means the plugin is broken for this run). The new method makes the distinction explicit.
- Existing callers of `call_hook` are unaffected. Only the two new dispatch sites use `dispatch_extension_point`.

**Note on `registry._hooks` access:** the dispatcher reads the hook table directly. If the underscore-prefixed access is uncomfortable, the plan can promote `_hooks` access to a public iterator on `HookRegistry` (e.g. `iter_handlers(hook_name)`) — that's an implementation detail to be settled when writing the plan.

---

## Testing

**Files:**

- `autobot_shared/plugin_sdk/plugin_sdk_test.py` — extends with new test groups
- `autobot_shared/plugin_sdk/async_bridge_test.py` — NEW; tests for the bridge in isolation
- `autobot-backend/tests/api/test_plugin_extension_hooks.py` — NEW; end-to-end via real FastAPI/Celery instances

**Test groups:**

| Test | Verifies |
| --- | --- |
| `test_register_extension_point_accepts_async_handler` | `BasePlugin.register_extension_point` accepts `async def`, calls land in `HookRegistry` |
| `test_register_extension_point_rejects_sync_handler` | Sync `def` raises `TypeError` at registration time with plugin name + hook name in message |
| `test_async_bridge_runs_coro_blocks_until_done` | `AsyncSyncBridge().run_coro(coro)` returns the coro's result |
| `test_async_bridge_propagates_exceptions` | Coro that raises propagates the exception synchronously |
| `test_async_bridge_singleton_returns_same_instance` | Two `AsyncSyncBridge()` calls return same `_loop`/`_thread` |
| `test_async_bridge_reset_for_tests_creates_fresh_instance` | After `reset_for_tests()`, new instance has new loop |
| `test_api_router_register_dispatch_mounts_plugin_routes` | Build minimal `FastAPI()`, register stub plugin's async handler, await `dispatch_extension_point(API_ROUTER_REGISTER, app)`, assert plugin's route is present in `app.routes` |
| `test_celery_task_register_dispatch_via_bridge` | Build minimal `Celery("test")`, register stub plugin's async handler, call dispatch via `AsyncSyncBridge`, assert task is in `celery_app.tasks` |
| `test_dispatch_extension_point_marks_failing_plugin_error_and_continues` | Two plugins; the first raises in its handler. Second still fires. First's `status == PluginStatus.ERROR`, second's stays `ENABLED`. |
| `test_dispatch_extension_point_does_not_affect_call_hook_semantics` | A plugin that raises in `Hook.ON_KB_DOCUMENT_ADDED` (event-style, dispatched via `call_hook`) still has `status == ENABLED` afterwards — confirming the new failure semantics are scoped to extension-point dispatch only. |
| `test_dispatch_starts_plugin_manager_if_not_started` | Plugin manager not yet started; dispatch triggers `startup()` automatically |

Memory-aligned conventions:

- `AsyncMock` for async function mocks (memory: `patch(async_func, return_value=X)` returns MagicMock that breaks awaits).
- Real SQLite / no SQLAlchemy mocks (not applicable here — no DB).
- Bridge tests use `reset_for_tests()` in `pytest` fixtures for clean state across tests.

---

## Migration / Backward Compatibility

- The 5 in-tree plugins (`hello-plugin`, `logger-plugin`, `mcp-wrapper-plugin`, `kb-event-plugin`, `telemetry-prompt-middleware`) use **none** of the new hooks. They continue to load and run identically.
- The new hooks land alongside existing event-style hooks on the same `Hook` enum, same registry. Adding new enum values is non-breaking.
- The new `AsyncSyncBridge` module is purely additive. Nothing imports it today.
- The `register_extension_point` sugar method is additive on `BasePlugin`. Subclasses that don't use it are unaffected.
- `PluginManager.dispatch_extension_point` is a new method; existing event-style hook callers using `HookRegistry.call_hook` are unchanged. Event-style hooks keep their existing "log + ignore" failure semantics — a transient handler exception during normal operation will not flip plugin status.

---

## Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| FastAPI lifespan dispatch happens AFTER core routes — plugin route collides with a core route | FastAPI's last-mount-wins; plugin's route shadows core. Log every plugin-mounted route at INFO so collisions are visible. Filing a follow-up `feat(plugin-sdk): route-collision detection at API_ROUTER_REGISTER time` if this becomes a real problem. |
| Plugin handler hangs forever (infinite loop / deadlock) | Both `await dispatch_extension_point(...)` (FastAPI) and `bridge.run_coro(...)` (Celery) currently have no timeout. Document the contract: handlers are expected to be fast (route registration is sync-fast). If timeouts ever needed, add `timeout=N` to `dispatch_extension_point`. Filed as follow-up if observed. |
| `AsyncSyncBridge` daemon thread leaks resources | Daemon threads are auto-reaped at process exit. Loop is `run_forever` — no resources held except the loop itself. Memory footprint is negligible. |
| `AsyncSyncBridge` singleton state pollutes tests | `reset_for_tests()` classmethod tears down loop + thread. Tests use it as fixture teardown. |
| Plugin manager not yet started at dispatch time | Both dispatch sites guard with `if not plugin_manager.is_started: await plugin_manager.startup()`. Idempotent — `startup()` short-circuits on second call (existing `_started` flag). |
| Plugin's `register_extension_point` called outside `initialize()` (e.g. lazily, during a request) | Doesn't break anything — `HookRegistry.register_hook` is just an append. But the hook fires only at lifespan startup, so late registration means the handler never runs. Document the contract: register in `initialize()`. |
| Celery `worker_init` runs in worker process, not Beat / FastAPI | Correct — that's the intent. Each Celery worker fires its own dispatch. Plugins should make handlers idempotent (register once per worker). FastAPI does the same dispatch independently for HTTP routes. |
| Plugin marked ERROR by an extension-point dispatch fail still appears ENABLED elsewhere | `dispatch_extension_point` updates `plugin.status` immediately. Any code that filters by `status` (e.g., `PluginRegistry.get_enabled_plugins`) will see the plugin as not-enabled after the failure. |

---

## Out of Scope (filed at PR-merge time)

- `feat(plugin-sdk): FRONTEND_ROUTE_REGISTER hook + Vite plugin` — Frontend extension point. Depends on #6972 (frontend module mounting).
- `feat(plugin-sdk): PLUGIN_SETTINGS_VIEW_REGISTER hook` — Frontend settings view registration. Stacked on FRONTEND_ROUTE_REGISTER.
- `feat(plugin-sdk): route-collision detection at API_ROUTER_REGISTER` — Detect when a plugin route collides with a core route or another plugin's route.
- `feat(plugin-sdk): hook timeout support` — `dispatch_extension_point(..., timeout=N)` for handlers that may hang.
- `feat(plugin-sdk): hook discovery endpoint GET /api/plugins/hooks` — Introspection of registered hooks for the host UI.

---

## Acceptance Criteria

- [ ] `Hook.API_ROUTER_REGISTER` and `Hook.CELERY_TASK_REGISTER` added to `autobot_shared/plugin_sdk/hooks.py`
- [ ] `BasePlugin.register_extension_point` added to `autobot_shared/plugin_sdk/base.py`; rejects sync handlers with `TypeError`
- [ ] `AsyncSyncBridge` singleton in `autobot_shared/plugin_sdk/async_bridge.py` with daemon-thread loop + `run_coro` + `reset_for_tests`
- [ ] `PluginManager.dispatch_extension_point(hook, *args, **kwargs)` added; iterates handlers, logs failures, marks failing plugin `status=PluginStatus.ERROR`, continues dispatching remaining plugins. `HookRegistry.call_hook` is **unchanged**.
- [ ] FastAPI dispatch site added to `autobot-backend/initialization/lifespan.py` — `await plugin_manager.dispatch_extension_point(Hook.API_ROUTER_REGISTER, app)` after Phase-1 startup
- [ ] Celery dispatch site added to `autobot-backend/celery_app.py` — `worker_init` signal handler using `AsyncSyncBridge` to invoke `dispatch_extension_point`
- [ ] `get_plugin_manager()` accessor exists in `autobot-backend/plugin_manager.py` (add if missing)
- [ ] All 10 new SDK tests pass
- [ ] Integration test verifies a stub plugin's route lands in `app.routes` after lifespan startup
- [ ] Integration test verifies a stub plugin's task lands in `celery_app.tasks` after `worker_init`
- [ ] All 5 in-tree plugins still load identically (regression check)
- [ ] `black --check`, `isort --check`, `py_compile` clean
- [ ] No new pre-commit failures
