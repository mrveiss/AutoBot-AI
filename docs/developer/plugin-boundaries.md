# Plugin / Extension / Skill Import Boundary Enforcement

**Issue:** [#7372](https://github.com/mrveiss/AutoBot-AI/issues/7372)
**Status:** Enforced (pre-commit + CI semgrep scan)

---

## Why Boundaries Matter

AutoBot has three distinct plugin layers:

| Layer | Path | Loader | Purpose |
|---|---|---|---|
| **Extensions** | `autobot-backend/middleware/builtin/` | `middleware.manager` | Lifecycle middleware hooks (`BEFORE_MESSAGE_PROCESS`, etc.) |
| **Skills** | `autobot-backend/skills/builtin/` | `skills.manager` | User-facing capabilities (calendar, code-review, web-fetch…) |
| **Core-plugins** | `plugins/core-plugins/` | `autobot_shared.plugin_sdk.loader` | Standalone manifest-driven packages |

When any of these layers imports directly from `autobot-backend` core modules
(e.g. `from chat_workflow import graph`) it creates **implicit coupling** that
breaks silently when core is refactored. This is the same root cause as
[#6525](https://github.com/mrveiss/AutoBot-AI/issues/6525)
(marketplace brittle remote-entry).

---

## Rules

### Rule 1 — No core-backend imports (`extension-no-core-internals`)

Files under `middleware/builtin/`, `skills/builtin/`, and `plugins/core-plugins/`
**must not** import from autobot-backend core packages:

```python
# ❌ VIOLATION — reaches into core
from chat_workflow.graph import build_graph
from knowledge.base import KnowledgeBase
from api.schemas_agent import AgentPayload

# ✅ ALLOWED — public SDK surface
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from autobot_shared.plugin_sdk.base import PluginBase
```

### Rule 2 — No sibling extension imports (`extension-no-sibling-import`)

Extensions must not import other extensions except through `__init__.py`
(the package's own re-export file).

```python
# ❌ VIOLATION — coupling two extensions together
from middleware.builtin.permission_enforcement import PermissionEnforcementExtension

# ✅ ALLOWED in __init__.py only (package re-export)
from middleware.builtin.logging_extension import LoggingExtension
```

### Rule 3 — No sibling skill imports (`skill-no-sibling-import`)

Same rule for skills: skills must not import each other directly.
Share logic via `autobot_shared/` or a dedicated helper module.

---

## Enforcement

### Pre-commit (local development)

The hook `extension-import-boundaries` runs automatically on staged `.py`
files in the covered paths.

To run manually on specific files:
```bash
python tools/lint/check_extension_import_boundaries.py \
  autobot-backend/middleware/builtin/my_extension.py
```

Exit code 0 = clean, exit code 1 = violations.

### CI (pull requests)

`.github/workflows/code-quality.yml` includes a semgrep step that runs the
rules in `security/semgrep/extension-import-boundaries.yaml` on every PR
touching covered paths.

---

## Waivers

If a violation is **genuinely intentional** (rare), add an inline waiver with
a mandatory reason comment:

```python
from middleware.builtin.permission_enforcement import check  # nosemgrep: extension-no-sibling-import — shared audit helper, not yet moved to autobot_shared
```

**Waivers without a reason comment are not accepted.**  File an issue to
track the cleanup: `discovery(arch): waiver for <rule> in <file>`.

---

## Adding New Extensions / Skills / Plugins

When writing a new extension, skill, or plugin:

1. Import **only** from `autobot_shared.*` for shared utilities.
2. Implement your logic self-contained within the file/package.
3. If you find yourself needing to import from core, that code belongs in
   `autobot_shared/` — file an issue to move it there.

---

## Related

- [#7426](https://github.com/mrveiss/AutoBot-AI/issues/7426) — canonical terminology (plugin vs extension vs skill)
- [#6525](https://github.com/mrveiss/AutoBot-AI/issues/6525) — marketplace brittle remote-entry (same root cause)
- [#5225](https://github.com/mrveiss/AutoBot-AI/issues/5225) — KB redis accessor migration (same enforcement pattern)
- `security/semgrep/extension-import-boundaries.yaml` — machine-readable rules
- `tools/lint/check_extension_import_boundaries.py` — pre-commit checker
