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
