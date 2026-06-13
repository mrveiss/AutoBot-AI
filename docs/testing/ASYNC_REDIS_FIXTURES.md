---
tags:
  - testing
  - backend
  - redis
aliases:
  - Async Redis Fixtures
  - Mocking Redis
---

# Async Redis Test Fixtures (`make_async_redis` / `patch_async_redis`)

> **Source**: `autobot-backend/tests/fixtures/mocks.py` (canonical, #7264 / PR #7267)
>
> **Replaces**: the 11+ ad-hoc `_make_redis*()` helpers and
> `patch(..., new=AsyncMock(return_value=...))` boilerplate that were scattered
> across the backend test tree.

## Overview

Backend production code talks to Redis through the async client returned by
`await get_async_redis_client(...)`. Mocking that boundary by hand is
error-prone in two specific ways:

1. **The awaitable-wrap bug (#7216)** — `patch(target, return_value=mock_redis)`
   is wrong for an async callable. When production code *awaits* the patched
   function, it receives the patch's default `AsyncMock`, **not** your
   configured redis mock. Your `redis.get.return_value` silently never fires,
   and assertions pass or fail against the wrong object. This caused subtle
   test pollution between async-redis mock boundaries: tests appeared green
   while exercising an unconfigured mock, and per-test redis state leaked
   into whichever mock the production code actually saw.
2. **Per-method async setup** — every redis method a test touches must be an
   `AsyncMock` so `await redis.X(...)` works. Ad-hoc helpers each
   re-implemented a different subset, with different defaults.

The canonical fixtures solve both once, in one place.

## Import Path

```python
from tests.fixtures import make_async_redis, patch_async_redis

# Related helpers from the same module:
from tests.fixtures import make_redis_pipeline   # pipeline mock (#7339)
from tests.fixtures.mocks import make_stateful_redis  # stateful store (#7753)
```

All live in `autobot-backend/tests/fixtures/mocks.py`; `make_async_redis`,
`patch_async_redis`, and `make_redis_pipeline` are re-exported from
`tests.fixtures.__init__`.

## When to Use Which

| Situation | Use |
| --- | --- |
| You need a redis-shaped mock object to pass/inject directly (e.g. `svc.redis = mock`) | `make_async_redis(...)` |
| Production code calls `await get_async_redis_client(...)` internally and you must intercept it | `patch_async_redis(target, redis=...)` |
| Production code uses `redis.pipeline()` | `make_redis_pipeline(...)` passed via `make_async_redis(pipeline=...)` |
| Production code uses `redis.scan_iter(...)` (async generator) | `make_async_redis(scan_iter_keys=[...])` |
| Test must assert on *actual values written* (get/set round-trip, publish history) | `make_stateful_redis()` |

`patch_async_redis` uses `make_async_redis()` internally when you don't pass
`redis=`, so the common case is one call.

## Signatures

### `make_async_redis(**kwargs) -> AsyncMock`

Builds an async-redis-shaped `AsyncMock` with every common redis method
pre-configured as an awaitable `AsyncMock`. Defaults pick the
"empty/healthy" shape; override any method's return value via the matching
`X_returns` keyword:

```python
def make_async_redis(
    *,
    get_returns=None, set_returns=True, setex_returns=True,
    delete_returns=1, expire_returns=True, exists_returns=0,
    incr_returns=1, decr_returns=0, keys_returns=None, ttl_returns=-1,
    # Hash ops: hget/hset/hgetall/hkeys/hvals/hdel/hexists ..._returns
    # Set ops: sadd/srem/smembers/sismember ..._returns
    # List ops: lrange/lpush/rpush/llen ..._returns
    # Sorted-set ops: zadd/zcard/zrange/zrangebyscore/zrevrange/zremrangebyrank ..._returns
    publish_returns=0,
    pipeline=None,          # pass make_redis_pipeline(...) (#7339)
    scan_iter_keys=None,    # list of keys yielded by redis.scan_iter() (#7339)
    **extra_methods,        # any other method name -> AsyncMock(return_value=value)
) -> AsyncMock: ...
```

Default shape:

- `get` / `hget` / `hgetall` / `keys` / `smembers` / `lrange` / `zrange` → empty / `None`
- `set` / `setex` / `expire` → `True`
- `sadd` / `srem` / `zadd` / `lpush` / `rpush` / `incr` / `hset` / `delete` → `1`
- `sismember` / `hexists` / `exists` → `0` / `False` (not present)

Methods not in the pre-configured list go through `**extra_methods`:

```python
redis = make_async_redis(get_returns=b"hello", xadd=("stream", "1-0"))
```

### `patch_async_redis(target: str, redis: AsyncMock | None = None)`

A `contextmanager` that patches `get_async_redis_client` at `target` with
the correct `AsyncMock` wrapping (the patched callable is itself awaitable
and returns the inner redis mock when awaited). Yields the **inner redis
mock** so you can configure or assert on it:

```python
with patch_async_redis("api.foo.get_async_redis_client") as redis:
    redis.get = AsyncMock(return_value=b"hit")
    result = await foo()
    redis.get.assert_awaited_once_with("key")
```

Or pass a pre-configured mock:

```python
redis = make_async_redis(get_returns=b"value")
with patch_async_redis("api.foo.get_async_redis_client", redis=redis):
    ...
```

## Migration Example: Ad-Hoc `AsyncMock` → Canonical Fixture

Real migration from `services/workflow_versioning_test.py`
(commit `cf63f00d3`, #7280 round 1 / PR #7340 — removed a local helper and
17 patch call sites):

**Before** (ad-hoc helper + manual patch boilerplate):

```python
from unittest.mock import AsyncMock, patch

def _make_redis() -> AsyncMock:
    """Return an AsyncMock that behaves like a redis-py async client."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.zadd = AsyncMock(return_value=1)
    redis.zrem = AsyncMock(return_value=1)
    redis.zrevrange = AsyncMock(return_value=[])
    return redis

@pytest.mark.asyncio
async def test_returns_version_1_for_new_workflow(self):
    store = WorkflowVersionStore()
    mock_redis = _make_redis()
    mock_redis.zrevrange.return_value = []

    with patch(
        "services.workflow_versioning.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        version = await store.save_version("wf-1", _make_data())

    assert version == 1
```

**After** (canonical fixtures):

```python
from tests.fixtures import make_async_redis, patch_async_redis

@pytest.mark.asyncio
async def test_returns_version_1_for_new_workflow(self):
    store = WorkflowVersionStore()
    mock_redis = make_async_redis()
    mock_redis.zrevrange.return_value = []

    with patch_async_redis(
        "services.workflow_versioning.get_async_redis_client", redis=mock_redis
    ):
        version = await store.save_version("wf-1", _make_data())

    assert version == 1
```

The canonical fixture already pre-configures the defaults the local helper
duplicated (`set=True`, `get=None`, `delete=1`, `zadd=1`, `zrevrange=[]`),
and `patch_async_redis` guarantees the awaitable wrap — the #7216 bug class
cannot reappear at migrated call sites.

## The Consumer-Namespace Patching Rule (PR #7279)

`target` must point at the **module that production code imports the symbol
into** — not at the canonical source. This is the core `unittest.mock`
convention ("patch where it's looked up, not where it's defined"), and PR
#7279 fixed 7 test sites that violated it.

Production code typically imports at module top:

```python
# services/session_service.py
from autobot_shared.redis_client import get_async_redis_client
```

After that import, `services.session_service` holds its **own binding** to
the function. Patching the source only changes the source's binding — the
consumer's local binding still points at the real function, so the patch
never fires at runtime (and the test silently hits real connection logic or
an unrelated mock):

```python
# WRONG — patches the canonical source; consumer binding unaffected
with patch_async_redis("autobot_shared.redis_client.get_async_redis_client"):
    ...

# RIGHT — patches the consumer module's namespace
with patch_async_redis("services.session_service.get_async_redis_client"):
    ...
```

One exception worth knowing: modules using `AsyncRedisClientMixin`
(`self.redis()`) don't import `get_async_redis_client` at all — patching it
there is a no-op. Inject the mock directly instead: `svc.redis = make_async_redis()`.

## Related

- [TEST_UTILITIES_MIGRATION_GUIDE](TEST_UTILITIES_MIGRATION_GUIDE.md) — base-class/`setup_method` standardization (`tests/test_utils`)
- `autobot-backend/tests/fixtures/test_make_async_redis.py` — the fixtures' own test suite (good usage reference)
- History: #7264 (fixture introduction, PR #7267) · #7216 / PR #7234 (awaitable-wrap bug class) · PR #7279 (consumer-namespace rule) · #7339 (pipeline + `scan_iter`) · #7753 (`make_stateful_redis`)
