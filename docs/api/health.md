# Health Endpoint — Single Source of Truth

> Issue [#3333](https://github.com/mrveiss/AutoBot-AI/issues/3333). The
> previous sprawl of 45 module-local `/health` endpoints is being collapsed
> behind one canonical aggregator at `/api/system/health`. This document
> describes the registration pattern that replaces the per-module routes.

## TL;DR

There is exactly **one** health endpoint that anything outside the backend
should ever call:

```
GET /api/system/health
```

It is unauthenticated, cached for 30 seconds, and returns the worst-of-components
rollup for every probe registered via `api.system_health.register_health_probe`.

## Response shape

```json
{
  "status": "healthy",
  "timestamp": "2026-05-04T12:34:56.789Z",
  "initialization": {
    "status": "ready",
    "message": "All components initialized"
  },
  "components": {
    "backend": "healthy",
    "config": "healthy",
    "logging": "healthy",
    "redis": "ok",
    "knowledge": "degraded",
    "...": "..."
  },
  "probes": [
    {
      "name": "redis",
      "status": "ok",
      "latency_ms": 1.42
    },
    {
      "name": "knowledge",
      "status": "degraded",
      "detail": "knowledge base not initialized in app state",
      "latency_ms": 0.18
    }
  ]
}
```

- `components` keeps the legacy frontend `Record<string, string>` shape so
  existing callers (`SystemRepository.ts`, monitoring exporters) keep working.
- `probes` is the structured per-component view: each entry is a
  `ComponentHealth` with `latency_ms`, optional `detail`, and optional `data`.
- The top-level `status` is degraded if any probe is degraded, down if any
  probe is down, otherwise healthy.

## Registering a probe

Modules expose health by registering a probe **at import time**:

```python
from typing import Optional
from fastapi import Request
from api.system_health import ComponentHealth, register_health_probe

@register_health_probe("my_module")
async def probe_my_module(request: Optional[Request] = None) -> ComponentHealth:
    """Probe one critical dependency. MUST be lightweight (<2s)."""
    try:
        manager = request.app.state.my_module_manager  # type: ignore[union-attr]
        if manager is None:
            return ComponentHealth(
                name="my_module",
                status="down",
                detail="manager not initialized",
            )
        return ComponentHealth(name="my_module", status="ok")
    except Exception as exc:
        return ComponentHealth(
            name="my_module",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )
```

### Rules

1. **Async, exactly one optional `Request` argument.** Probes that need
   `request.app.state.X` accept the request; probes that only check a
   module-level singleton can ignore it.
2. **Catch your own exceptions.** Return `status="down"` with a short
   `detail`. The registry has a fallback `try/except`, but defensive probes
   produce better diagnostic output.
3. **Lightweight.** The aggregator times each probe out at 2 seconds; a
   probe that exceeds that budget is reported as `status="down"`. Skip
   anything network-heavy or that triggers lazy initialization.
4. **Probe name is the registry key.** `register_health_probe("knowledge")`
   appears under `components["knowledge"]`. Use lowercase snake_case.
5. **Registration happens once per process** at module import time. Re-registering
   the same name overwrites and logs a warning — do NOT call the decorator
   inside a function body.

## Composable helpers (Issue #6904)

Three repeating probe patterns have one-liner registration helpers in
`api/system_health.py`. Use them instead of hand-writing the boilerplate:

| Pattern | One-liner |
|---|---|
| Singleton-resolve (`getter()` non-None) | `register_singleton_probe(name, getter)` — pass `async_getter=True` for async getters |
| Redis ping on a named database | `register_redis_probe(name, database="main")` — always uses `get_async_redis_client` to avoid blocking the event loop |
| `request.app.state.<attr>` initialized | `register_app_state_probe(name, "attr")` |

Example call sites (registered at module import time):

```python
# autobot-backend/api/vision.py
from api.system_health import register_singleton_probe
from utils.screen_analyzer import get_screen_analyzer

register_singleton_probe("vision", get_screen_analyzer)


# autobot-backend/api/redis.py
from api.system_health import register_redis_probe

register_redis_probe("redis", database="main")


# autobot-backend/api/graph_rag.py
from api.system_health import register_app_state_probe

register_app_state_probe("graph_rag", "graph_rag_service")
```

The factory functions `probe_singleton`, `probe_redis_db`, `probe_app_state`
are also exported for callers that want a `ProbeFn` to compose with extra
logic (e.g. pass to `register_health_probe(name)(...)` in a custom block).

### Emitting module-specific data (Issue #6914)

All three helpers accept an optional `data_callback` keyword that lets you
attach module-specific fields to `probes[name].data` without hand-writing the
probe body. The callback receives the resolved value and returns a `dict`; it
is called on both success and failure paths so the frontend always gets a
consistent shape.

| Helper | Callback signature |
|---|---|
| `probe_singleton` / `register_singleton_probe` | `data_callback(instance: Any) -> dict` — `None` on failure |
| `probe_redis_db` / `register_redis_probe` | `data_callback(ok: bool) -> dict` — `False` on client-unavailable or ping failure |
| `probe_app_state` / `register_app_state_probe` | `data_callback(value: Any) -> dict` — `None` when attr missing or explicitly `None` |

```python
# autobot-backend/api/batch_jobs.py
from api.system_health import register_redis_probe

register_redis_probe(
    "batch_jobs",
    database="main",
    data_callback=lambda ok: {"redis_connected": ok, "service": "batch_jobs_manager"},
)
```

The frontend then reads `probes[name=batch_jobs].data.redis_connected` from
`GET /api/system/health` — no separate `/api/batch-jobs/health` call needed.

Probes with richer behaviour — counting items, mapping multi-valued state to
`degraded`/`down`, calling multiple getters — stay hand-written with
`@register_health_probe(name)`.

## Why a single endpoint

- **External monitors** (k8s liveness, Prometheus exporters, oncall dashboards)
  scrape one URL instead of 45.
- **Frontend** continues to use `useFetchEndpoint('/api/system/health')` with
  no payload-shape changes.
- **New modules** can't accidentally fork the pattern — the pre-commit hook
  blocks any `@router.get("/health")` outside `api/system_health.py` and
  `api/system.py`.
- **Failures degrade gracefully.** A slow or crashing probe becomes a single
  `down` component; the rest of the report keeps flowing.

## Pre-commit enforcement

The hook `no-new-health-route` runs at commit time and rejects any new
`@router.{get,post,put,delete}("/health")` definition outside the two
exempt files. Suppression (last resort) is `# noqa: health-route` on the
offending line.

## Sunset of legacy routes

The 38 per-module `/health` routes (after #6903 dropped 6 boilerplate ones)
are kept as a deprecation grace period. They will be removed in a follow-up
PR (tracked at #6902) after the criteria below are all met.

### Sunset signal

Issue #6902 wired `SunsetLegacyHealthMiddleware`
(`autobot-backend/middleware/sunset_legacy_health.py`) into the FastAPI
middleware stack. Every `GET /api/<module>/health` response now carries:

```
Sunset: Wed, 02 Sep 2026 00:00:00 GMT
Deprecation: true
Link: </api/system/health>; rel="successor-version"
```

The canonical aggregator (`/api/system/health` and its alias `/api/health`)
is exempted — those headers do not appear on the migration target.

External scrapers (Prometheus exporters, k8s liveness probes, oncall
dashboards) should treat the `Sunset` header as a signal to migrate to
`/api/system/health` before the date elapses.

### Pre-deletion audit checklist

Before the route-deletion PR can run:

1. **Empirical traffic check** — query the Prometheus counter added by #6919
   over a 14-day window and assert zero hits per path before deletion.
   ```promql
   # Must return 0 for every legacy path before deletion is safe
   sum by (path, user_agent) (increase(autobot_legacy_health_hits_total[14d]))
   ```
   This converts the audit from a "static config grep" to an empirical
   traffic check; any unknown scraper that survived the config search will
   show up here. The counter is registered in
   `autobot-backend/middleware/sunset_legacy_health.py` with labels
   `{path, user_agent}` so operators can identify the caller by user-agent.
2. **Deployment configs** — grep Ansible playbooks, k8s manifests, and
   Prometheus job specs for `/api/<module>/health` paths. Confirm zero
   live scrapers remain.
   ```bash
   grep -rn "/api/[a-z_-]\+/health" autobot-infrastructure/ \
     k8s/ prometheus/ monitoring/ 2>/dev/null
   ```
3. **Server-side access logs** — sample 7 days of nginx/uvicorn logs and
   confirm zero hits on per-module `/health` paths from external IPs.
4. **Frontend callers** — these three callers still consume rich
   per-module response shapes (active_jobs, redis_connected, etc.) that
   the canonical aggregator's `ComponentHealth.data` does not expose.
   Either enrich the relevant probes' `data` payload, or accept that the
   UI may lose some diagnostic fields:
   - `useBatchProcessing.ts:263` → `/api/batch-jobs/health`
   - `useOperationsApi.ts:117` → `/api/long-running/health`
   - `usePrometheusMetrics.ts:368/583` → `/api/monitoring/services/health`
5. **`Sunset:` header live for at least one release** — the middleware
   shipped with PR #6912 (commit landed on `Dev_new_gui` at 2026-05-04).
6. **Pre-commit hook becomes hard-line** — drop the `# noqa: health-route`
   suppression escape hatch from the production code path.

When all six gates clear, the route-deletion PR can:

- Delete the 38 `@router.get("/health")` definitions across `autobot-backend/api/`
- Delete the now-orphaned `*HealthResponse` Pydantic schemas
- Verify `git grep "@router.get.*['\"]/health['\"]" autobot-backend/api/ | wc -l` == 1
- Remove the middleware (no legacy paths left to decorate)

## Parallel surface — `/api/monitoring/services/health` (#6922)

`/api/monitoring/services/health` lives on a different router (`api/monitoring.py`) and returns a `ServicesSummaryResponse` shape — a per-service rollup of npu / browser / ollama / redis pings — that two frontend composables (`usePrometheusMetrics.ts:368,583`) consume directly.

It is **deliberately not** registered as a probe under `/api/system/health` because:

1. **Shape mismatch** — `ServicesSummaryResponse.services[]` is a flat list of `{name, status, last_check, response_time, ...}` records; `ComponentHealth` is a single component with `data: dict[str, Any]`. Forcing the rollup through `ComponentHealth.data` flattens semantically distinct per-service entries into one opaque dict, losing typed access for the frontend.
2. **Different SLA** — `ComponentHealth` is bounded at the registry's ~2s per-probe timeout; `ServicesSummaryResponse` aggregates HTTP pings to remote VMs (npu / browser / ollama) which can legitimately take 5–10s without indicating system-level failure. The two endpoints have different latency envelopes by design.
3. **Auth posture** — both currently require no auth (allowlisted in `service_auth_enforcement.py`), but `services/health` is intended for ops-dashboard scraping (Prometheus/Grafana via `usePrometheusMetrics`) while `system/health` is the user-facing reachability probe. Mixing them blurs the audit trail.

**The two endpoints answer different questions:**

| Endpoint | Question | Caller |
|---|---|---|
| `GET /api/system/health` | "Is the AutoBot backend itself healthy?" | Frontend health monitor before login + post-login banners |
| `GET /api/monitoring/services/health` | "What's the status of the constellation of remote services I depend on?" | Ops dashboard scraping (`usePrometheusMetrics`) |

If the rollup ever needs to fold into the canonical aggregator, the migration path is:

- Add a `monitoring_services` probe whose `data: {services: [...]}` mirrors `ServicesSummaryResponse`
- Migrate the two `usePrometheusMetrics` callers to read `probes[name=monitoring_services].data.services`
- Add `/api/monitoring/services/health` to the deletion list in #6902

Until that migration has explicit ops/frontend buy-in, both endpoints stay as-is. This document records the architectural decision so future contributors don't accidentally fork further.

## Testing a probe

`api.system_health` exposes `_reset_probes_for_testing()` to clear the
registry between tests. Example:

```python
import asyncio
from api.system_health import (
    ComponentHealth,
    _reset_probes_for_testing,
    collect_system_health,
    register_health_probe,
)

def test_my_probe_returns_ok():
    _reset_probes_for_testing()

    @register_health_probe("toy")
    async def probe_toy(_request=None):
        return ComponentHealth(name="toy", status="ok", detail="alive")

    result = asyncio.run(collect_system_health())
    assert result.status == "ok"
    assert result.components[0].name == "toy"
    assert result.components[0].latency_ms is not None
```
