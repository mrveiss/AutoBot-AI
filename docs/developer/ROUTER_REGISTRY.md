# AutoBot Router Registry

> Issue #4203 — consolidated and documented as of 2026-05-22

## Overview

The backend mounts all API routers through a two-level system:

```
app_factory._register_routers()
├── load_core_routers()        → initialization/router_registry/core_routers.py
└── load_optional_routers()    → initialization/routers.py
    ├── load_analytics_routers()   → router_registry/analytics_routers.py
    ├── load_terminal_routers()    → router_registry/terminal_routers.py
    ├── load_monitoring_routers()  → router_registry/monitoring_routers.py
    ├── load_integration_routers() → router_registry/integration_routers.py
    ├── load_feature_routers()     → router_registry/feature_routers.py
    └── load_mcp_routers()         → router_registry/mcp_routers.py
```

All core and optional routers are mounted under `/api<prefix>`.
One special-case router (`api.openai_compat`) is mounted at `/v1` directly in
`app_factory.py` for third-party client compatibility (Cursor, LibreChat, etc.).

## Domain Registry Files

| File | Domain | Load method |
|------|---------|-------------|
| `core_routers.py` | Auth, chat, settings, knowledge base, plugin manager, user management | Hard import — must not fail |
| `analytics_routers.py` | Codebase analytics, code analysis | `try/except` graceful |
| `terminal_routers.py` | Terminal, SSH, VNC | `try/except` graceful |
| `monitoring_routers.py` | Metrics, Prometheus, GPU, alertmanager, RUM, diagnostics | `try/except` graceful |
| `integration_routers.py` | External integrations (Slack, Notion, GitHub, etc.) | `try/except` graceful |
| `feature_routers.py` | All remaining product features | `try/except` graceful |
| `mcp_routers.py` | Model Context Protocol extensions | `try/except` graceful |

## Adding a New Router

1. **Choose the right file** based on the domain table above.
2. **Add a 4-tuple** to the `*_ROUTER_CONFIGS` list in that file:
   ```python
   ("api.my_feature", "/my-feature", ["my-feature"], "my_feature"),
   ```
3. **Do NOT** add it to multiple files — check for existing registration first:
   ```bash
   grep -r "my_feature\|my-feature" autobot-backend/initialization/router_registry/
   ```
4. Core features that must always be available → `core_routers.py` (direct import, not tuple list).

## Config Tuple Formats

`feature_routers.py`, `analytics_routers.py`, `integration_routers.py`, `mcp_routers.py`:
```python
(module_path, prefix, tags, display_name)
# e.g. ("api.workflow", "/workflow", ["workflow"], "workflow")
```

`monitoring_routers.py`, `terminal_routers.py`:
```python
(module_path, router_attr, prefix, tags, display_name)
# e.g. ("api.monitoring", "router", "/monitoring", ["monitoring"], "monitoring")
```

## Deduplication Rule

**Each router MUST appear in exactly one registry file.**
`core_routers.py` takes precedence. If a module is imported in `core_routers.py`,
it must not appear in any other registry file.

Known previous duplicates fixed by #4203:
- `api.knowledge_search_aggregator`, `api.knowledge_ai_stack`, `api.knowledge_debug`,
  `api.knowledge_boards`, `api.knowledge_vectorization` — were in both `core_routers.py`
  and `feature_routers.py`; removed from `feature_routers.py`
- `plugin_manager`, `api.user_management` — same issue; removed from `feature_routers.py`
- `api.diagnostics` — was in both `monitoring_routers.py` and `feature_routers.py`;
  removed from `feature_routers.py`

## Health Observability

`feature_routers.py` publishes per-worker load results to Redis under
`autobot:feature_routers:<pid>` (TTL 10 min, issue #6808). The health endpoint
can aggregate across all workers via `get_cross_worker_load_results()`.

The `📊 Loaded N/M optional routers` log line at startup shows how many
router configs successfully imported vs total attempted.
