# System Health API

## Overview

`/api/system/health` aggregates every registered probe into a single
`SystemHealth` response (worst-of-components rollup).  The implementation lives
in `api/system_health.py`.

---

## Probe-name SSOT — design decision (Issue #6917)

### Problem

Before this change, probe name strings were hardcoded independently in two
places:

- **Backend** — `@register_health_probe("batch_jobs")` in e.g. `api/batch_jobs.py`
- **Frontend** — callers that matched on `probes[name="batch_jobs"]` in the
  health response

A one-character typo on either side produced a silent runtime fallback (the
frontend fell back to "unknown" status) rather than an immediate error.

### Options considered

| Option | Description | Verdict |
|--------|-------------|---------|
| A | Generate a TypeScript const file from Python at build time | Too much tooling; overkill for the current scale |
| B | Document the strings in a shared README and rely on code review | Low friction but still allows divergence |
| **C** | Add a `KnownProbes` (`str, enum.Enum`) in the backend; use it at registration time | **Chosen** — zero new tooling, immediate import-time error on typo |

### Chosen approach — Option C

`KnownProbes` is defined in `api/system_health.py` immediately after the
logger setup:

```python
class KnownProbes(str, enum.Enum):
    BATCH_JOBS       = "batch_jobs"
    LONG_RUNNING     = "long_running"
    KNOWLEDGE        = "knowledge"
    ERROR_RESILIENCE = "error_resilience"
    INTELLIGENT_AGENT = "intelligent_agent"
```

Because `KnownProbes` inherits from `str`, every member *is* the string value.
Passing `KnownProbes.BATCH_JOBS` to `register_health_probe(name: str)` works
without a cast, and the registered key in `_PROBES` is the plain string
`"batch_jobs"` — no change to the HTTP response shape.

---

## Adding a new probe

1. Add a member to `KnownProbes` in `api/system_health.py`:

   ```python
   MY_NEW_PROBE = "my_new_probe"
   ```

2. In the probe module, import and use it:

   ```python
   from api.system_health import ComponentHealth, KnownProbes, register_health_probe

   @register_health_probe(KnownProbes.MY_NEW_PROBE)
   async def probe_my_new_probe(request=None) -> ComponentHealth:
       ...
   ```

3. The name automatically appears in the OpenAPI schema under
   `/api/system/health` → `components[].name`.  Frontend callers should derive
   the expected probe names from the OpenAPI schema rather than hardcoding
   strings.

---

## Frontend guidance

Frontend code **must not** hardcode probe name strings.  Instead:

1. Reference the OpenAPI schema exported at `/openapi.json` — the
   `ComponentHealth.name` field documents the possible values.
2. When adding a new frontend caller, verify the probe name against
   `KnownProbes` in `api/system_health.py` (this file) before shipping.

---

## Probe timeout and error handling

Every probe runs under a `_PROBE_TIMEOUT_S = 2.0` second deadline enforced by
`asyncio.wait_for`.  A probe that times out or raises is recorded as
`status="down"` — it cannot crash the aggregator.

Probes **must** be `async def`.  The registry rejects sync probes at
registration time with a `TypeError` (see Issue #6918).

---

## Probe Data Contract (Issue #6916)

Each probe returns a `ComponentHealth` object which includes an optional `data`
dict.  The frontend reads specific keys from `data` to render dashboards and
trigger alerts.

**Critical rule:** the `data` payload of every enriched probe is a
frontend-backend contract.  Keys must not be renamed, removed, or retyped
without a coordinated frontend change.  A contract test must be added
alongside any new `data` payload or change to an existing one (see
[Testing convention](#testing-convention) below).

---

## Probe contracts

### `probe_batch_jobs`

Source: `api/batch_jobs.py`

| Key | Type | Description |
|-----|------|-------------|
| `redis_connected` | `bool` | Whether the Redis ping succeeded |
| `service` | `str` | Always `"batch_jobs_manager"` — canonical identifier used by the frontend |

All three branches of the probe (client `None`, ping fails, ping succeeds)
return both keys.  The frontend may safely access
`probes[name=batch_jobs].data.redis_connected` and
`probes[name=batch_jobs].data.service` without a `null`-guard.

### `probe_long_running`

Source: `api/long_running_operations.py`

| Key | Type | Description |
|-----|------|-------------|
| `active_operations` | `int` | Count of operations with status `RUNNING` |
| `total_operations` | `int` | Total count of all tracked operations |
| `redis_connected` | `bool` | Whether the operation manager has a non-`None` Redis client |
| `background_processor_running` | `bool` | Whether the background processor loop is running |

When the operations framework is not installed (`_OPERATIONS_AVAILABLE =
False`) all values are `0` / `False` — the keys are still present.  The
frontend may safely access all four keys without a `null`-guard.

---

## Testing convention

Every probe that exposes a `data` dict **must** have a corresponding data-shape
test in `tests/test_health_probe_data_contract.py`.

### Checklist for adding a new probe with `data`

1. Add the probe function in the appropriate `api/*.py` module and decorate it
   with `@register_health_probe("<name>")`.
2. Document the `data` keys in the table above (this file).
3. Add at least one `@pytest.mark.asyncio` test in
   `tests/test_health_probe_data_contract.py` that:
   - Monkeypatches all external I/O (Redis clients, manager singletons, etc.)
   - Calls the probe function directly (bypassing the HTTP layer)
   - Asserts `result.data is not None`
   - Asserts each documented key is present in `result.data`

### Checklist for modifying an existing probe's `data` keys

1. Update the table in this file.
2. Update (or add) tests in `tests/test_health_probe_data_contract.py`.
3. Coordinate the frontend change — search for the old key name in the
   frontend codebase before merging.

### Example test skeleton

```python
@pytest.mark.asyncio
async def test_probe_my_service_data_shape(monkeypatch):
    async def fake_client(database):
        class _Stub:
            async def ping(self): return True
        return _Stub()

    monkeypatch.setattr(
        "autobot_shared.redis_client.get_async_redis_client",
        fake_client,
    )

    from api.my_service import probe_my_service
    result = await probe_my_service(None)

    assert result.data is not None
    assert "my_key" in result.data
    assert "other_key" in result.data
```

---

## Related issues

- Issue #6902: enriched probe data introduced for `batch_jobs` and
  `long_running` so the frontend can read structured fields instead of
  parsing the plain-text `detail` field.
- Issue #6916: contract tests added to prevent silent drift between the probe
  `data` payload and the frontend's expected shape.
- Issue #6917: `KnownProbes` enum introduced to eliminate hardcoded probe name
  strings.
- Issue #6918: registry rejects sync probes at registration time.
