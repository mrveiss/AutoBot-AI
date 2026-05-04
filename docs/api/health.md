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

The 44 per-module `/health` routes are kept for one release as a deprecation
grace period. They will be removed in a follow-up PR after:

1. A grep of deployment configs (Ansible, k8s, monitoring) confirms no
   external scraper still hits them.
2. The frontend has migrated `useBatchProcessing.ts:263`,
   `useOperationsApi.ts:117`, and `usePrometheusMetrics.ts:368/583` off
   their per-module health calls.
3. A `Sunset:` HTTP response header has been live on the legacy routes for
   one release.

The sunset PR is not in scope for #3333.

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
