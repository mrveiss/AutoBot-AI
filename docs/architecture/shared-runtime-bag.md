# SharedRuntimeBag — Redis-backed cross-worker constraint envelope

Issue [#6630](https://github.com/mrveiss/AutoBot-AI/issues/6630)

## Problem

AutoBot runs 4 uvicorn workers in production. Many subsystems store state in
module-level singletons that are silently per-worker:

- `ConnectorScheduler` — schedule mutations only land on one worker
- `LiveEventManager` — WebSocket subscribers see events only from their worker
- `AgentBudgetTracker` — budget counters not shared; hard-stop can't be enforced globally
- `AgentAbortFlags` — cancel on worker A doesn't reach in-flight task on worker B

This is a **recurring class of bug**. `SharedRuntimeBag` fixes the *pattern*, not each instance.

## Design

`SharedRuntimeBag[T]` is a generic Redis-backed dictionary. Any subsystem that
needs cross-worker state uses it instead of a module-level dict or singleton.

```
autobot_shared/coordination/shared_runtime_bag.py
```

### Redis key layout

| Key | Purpose |
|-----|---------|
| `runtime_bag:{namespace}:{key}` | JSON-serialised value, with TTL |
| `runtime_bag:{namespace}:changes` | pub/sub channel for change events |

### API

```python
from autobot_shared.coordination import SharedRuntimeBag

# Create a typed bag
bag: SharedRuntimeBag[int] = SharedRuntimeBag(
    namespace="agent_budget",
    value_type=int,
    default_ttl_s=3600,
)

# Basic operations
await bag.set("agent-123", 1000)
value = await bag.get("agent-123")     # 1000
keys  = await bag.keys()               # ["agent-123"]
await bag.delete("agent-123")

# Atomic read-modify-write (CAS via WATCH/MULTI/EXEC)
new_val = await bag.update("agent-123", lambda v: v - 1)

# Subscribe to change events from any worker
async for event in bag.subscribe_changes():
    print(event.key, event.operation, event.value)
    # event.operation: "set" | "delete"
```

### Pydantic models as values

```python
from pydantic import BaseModel

class BudgetState(BaseModel):
    limit: int
    used: int

bag: SharedRuntimeBag[BudgetState] = SharedRuntimeBag(
    "agent_budget", BudgetState
)
await bag.set("agent-123", BudgetState(limit=1000, used=0))
state = await bag.get("agent-123")   # BudgetState instance
```

## Guarantees

| Property | Mechanism |
|----------|-----------|
| Cross-worker visibility | Redis as single source of truth |
| TTL / expiry | `EX` flag on every `SET` |
| Atomic mutation | `WATCH / MULTI / EXEC` with configurable retry |
| Change notifications | Redis pub/sub per namespace |
| Serialisation | Pydantic `TypeAdapter` — handles plain types and models |
| Pub/sub best-effort | Publish failures are logged, never propagated |

## Migration cookbook

To migrate a module-level singleton to `SharedRuntimeBag`:

### Before

```python
# agent_abort_flags.py
_abort_flags: dict[str, bool] = {}

def is_aborted(agent_id: str) -> bool:
    return _abort_flags.get(agent_id, False)

def set_abort(agent_id: str) -> None:
    _abort_flags[agent_id] = True
```

### After

```python
# agent_abort_flags.py
from autobot_shared.coordination import SharedRuntimeBag

_abort_bag: SharedRuntimeBag[bool] = SharedRuntimeBag(
    "agent_abort_flags", bool, default_ttl_s=86400
)

async def is_aborted(agent_id: str) -> bool:
    return (await _abort_bag.get(agent_id)) or False

async def set_abort(agent_id: str) -> None:
    await _abort_bag.set(agent_id, True)
```

Key changes: functions become `async`, callers must `await` them.

## Known consumers

| Consumer | Issue | Priority |
|----------|-------|----------|
| `AgentBudgetTracker` | [#6470](https://github.com/mrveiss/AutoBot-AI/issues/6470) | 1 — required for budget hard-stop |
| `AgentAbortFlags` | — | 2 — cross-worker cancel |
| `AgentParentGoalState` | [#6469](https://github.com/mrveiss/AutoBot-AI/issues/6469) | 3 — goal ancestry |
| `ConnectorScheduler` | [#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556) | 4 |
| `LiveEventManager` subscriber registry | — | 5 |

## Why not a simple Redis hash?

A raw Redis hash has no TTL per-entry, no CAS, and no change notification.
`SharedRuntimeBag` is a thin wrapper that adds all three while keeping the
API ergonomic and the serialisation transparent.

## Related

- Pattern source: [#4502](https://github.com/mrveiss/AutoBot-AI/issues/4502) (A2A Redis-backed task store — `autobot-backend/a2a/task_manager.py`)
- Direct consumer: [#6470](https://github.com/mrveiss/AutoBot-AI/issues/6470)
- Recurring class: [#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556), [#6479](https://github.com/mrveiss/AutoBot-AI/issues/6479)
