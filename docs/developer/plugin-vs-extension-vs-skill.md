# Plugin vs Extension vs Skill — Terminology and Architecture

**Issue:** [#7426](https://github.com/mrveiss/AutoBot-AI/issues/7426)
**Status:** Resolved (renames + terminology canonical)

---

## Executive Summary

AutoBot has three plugin-like subsystems, each with a distinct purpose and API:

| Layer | Package | Purpose | API |
|---|---|---|---|
| **Middleware** | `autobot-backend/middleware/` | Lifecycle hooks at 24 pipeline points | Extends `Extension` base class |
| **Skills** | `autobot-backend/skills/` | User-facing capabilities (calendar, code-review, web-fetch…) | Service classes with methods |
| **Plugins** | `plugins/core-plugins/` | Standalone packages with manifests | Load via `autobot_shared/plugin_sdk/` |

These terms were historically conflated. **Middleware** was called "extensions" because the base class was `Extension`. New code should use "middleware" exclusively.

---

## Terms Defined

### Middleware (renamed from "extensions")

**Location:** `autobot-backend/middleware/builtin/`

**Purpose:** Implement before/after hooks at defined lifecycle points in message processing.

**API:** Subclass `Extension` and override hook handlers:
```python
from middleware import Extension, HookPoint, HookContext

class LoggingMiddleware(Extension):
    name = "logging_middleware"
    
    async def on_before_message_process(self, ctx: HookContext):
        # Log before processing
        pass
```

**Lifecycle points (HookPoint enum):** 24 points including:
- `BEFORE_MESSAGE_PROCESS` / `AFTER_MESSAGE_PROCESS`
- `BEFORE_TOOL_EXECUTE` / `AFTER_TOOL_EXECUTE`
- `APPROVAL_REQUIRED`
- And 20 others

**Invocation:** Central `ExtensionManager` (misnomer — will be renamed to `MiddlewareManager` in v2).

---

### Skill

**Location:** `autobot-backend/skills/builtin/`

**Purpose:** User-facing capabilities (available to agents as commands).

**API:** Standalone Python class or async function with a schema:
```python
class WebFetchSkill:
    """Fetch content from a URL."""
    
    async def execute(self, url: str, timeout: int = 30) -> str:
        # Implement skill logic
        pass
```

**Invocation:** Agent requests skill by name; `SkillManager` routes and executes.

**Examples:** `calendar_integration`, `code_review`, `web_fetch`, `github_search`

---

### Plugin (core-plugins)

**Location:** `plugins/core-plugins/`

**Purpose:** Standalone packages that extend AutoBot via manifest-driven loading.

**API:** Package with `plugin.json` manifest + Python/JavaScript code:
```json
{
  "id": "hello-plugin",
  "name": "Hello World Plugin",
  "version": "1.0.0",
  "entryPoint": "main.py",
  "hooks": ["BEFORE_MESSAGE_PROCESS"]
}
```

**Invocation:** `autobot_shared/plugin_sdk/loader.py` loads at startup.

**Examples:** `hello-plugin`, `logger-plugin`, `telemetry-prompt-middleware`

---

## Migration (Issue #7426)

### Renames Executed

1. **Backend:** `autobot-backend/extensions/` → `autobot-backend/middleware/`
   - All `from extensions.` imports → `from middleware.`
   - Base class still `Extension` (v2: rename to `Middleware`)
   - Re-export shim in `extensions/__init__.py` for one release cycle

2. **Frontend:** `autobot-frontend/src/plugins/` (unchanged for now)
   - These are Vue plugin utilities, not part of the plugin system
   - Future: rename to `vue-plugins/` or inline into `main.ts` (filed separately)

### Call-Site Updates

External callers updated:
- `autobot-backend/chat_workflow/session_handler.py`
- `autobot-backend/chat_workflow/llm_handler.py`
- `autobot-backend/initialization/lifespan.py`

Test files work via backwards-compat re-export shim.

### Deprecation Timeline

**v1 (now):**
- Middleware code in `autobot-backend/middleware/`
- Extensions package is a re-export shim pointing to middleware
- Importing from `extensions` still works (triggers deprecation warning in v2)

**v2 (next release):**
- Remove `extensions/__init__.py` shim
- Rename `Extension` class → `Middleware`
- Rename `ExtensionManager` → `MiddlewareManager`

---

## Acceptance Criteria

- [x] Terminology decision document created (this file)
- [x] Directory renamed: `extensions/` → `middleware/`
- [x] Re-export shim in `extensions/__init__.py` for backwards compat
- [x] External call sites updated
- [x] CLAUDE.md references updated (if any)

---

## Related

- [#7372](https://github.com/mrveiss/AutoBot-AI/issues/7372) — import boundary enforcement
- [#658](https://github.com/mrveiss/AutoBot-AI/issues/658) — extension manager origin
- [#730](https://github.com/mrveiss/AutoBot-AI/issues/730) — plugin SDK origin
- [#3185](https://github.com/mrveiss/AutoBot-AI/issues/3185) — LLM consolidation
