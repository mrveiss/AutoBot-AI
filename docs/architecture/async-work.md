# Async Work — Unified Architecture

> Tracks the consolidation effort under umbrella issue [#6495](https://github.com/mrveiss/AutoBot-AI/issues/6495). This document is updated as each phase lands.
>
> - **Phase 1 — Task queues** ([#6505](https://github.com/mrveiss/AutoBot-AI/issues/6505)): _pending_
> - **Phase 2 — Progress trackers** ([#6506](https://github.com/mrveiss/AutoBot-AI/issues/6506)): **landed (this document)**
> - **Phase 3 — Periodic schedulers** ([#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507)): _pending_

The async-work stack covers three sub-domains: **queue work → execute → report progress → schedule next**. Historically each had two or three parallel implementations; #6495 consolidates them onto one canonical primitive per sub-domain.

## Progress tracking (Phase 2 — landed)

`task_execution_tracker.TaskExecutionTracker` is the canonical store and
broadcaster for in-flight task progress. Pre-#6506 there were three parallel
trackers; the in-memory `_progress_cache` and ad-hoc Redis pub/sub formats are
gone. There is now exactly one Redis key shape, one wire format, and one
publisher.

### Decision tree

| Caller need | Use |
|---|---|
| Track a task's lifecycle (start → complete/fail) | `TaskExecutionTracker.track_task` (context manager) |
| Emit fine-grained in-flight progress for any task | `TaskExecutionTracker.update_progress(task_id, percent, current_step, ...)` |
| Read the latest progress snapshot for a task | `TaskExecutionTracker.get_progress(task_id)` |
| Subscribe an in-process callback for the long-running-operations framework | `OperationProgressTracker.subscribe_to_progress(operation_id, callback)` |
| Receive progress over WebSocket | Subscribe to Redis channel `operations:progress` (global) or `operation:{task_id}:progress` (per-task) |

### Why the two layers

- **`TaskExecutionTracker`** is the canonical primitive — every progress write
  flows through it, every WebSocket subscriber reads what it publishes.
- **`OperationProgressTracker`** is a thin façade on top, retained because the
  long-running-operations framework depends on **in-process** subscriber
  callbacks (synchronous notification within the same Python process) that
  Redis pub/sub doesn't reproduce. The façade owns only the in-process
  callback dictionary; storage and broadcast delegate to the canonical tracker.

### Wire format

Both Redis storage and pub/sub use the same JSON envelope:

```json
{
  "type": "operation_progress",
  "operation_id": "task-abc-123",
  "operation_type": "codebase_indexing",
  "name": "Index repo X",
  "status": "running",
  "progress": {
    "current_step": "Scanning files",
    "progress_percent": 42.5,
    "items_processed": 850,
    "total_items": 2000,
    "estimated_remaining": 35.0,
    "last_update": "2026-04-29T12:34:56.789012+00:00",
    "details": {}
  }
}
```

Storage key: `operation:{task_id}:progress` (latest snapshot, `SET`).
Per-task channel: `operation:{task_id}:progress` (PUBLISH).
Global channel: `operations:progress` (PUBLISH).

`operation_type`, `name`, and `status` are top-level so existing WebSocket
consumers can route events without parsing the inner `progress` block. They
default to empty strings / `"running"` when the caller doesn't supply them
(typical for plain `TaskExecutionTracker.update_progress` callers outside the
long-running-operations framework).

### Removed surface

- `OperationProgressTracker._progress_cache` — gone. The previous in-memory
  `Dict[str, OperationProgress]` is replaced by the Redis snapshot at
  `operation:{task_id}:progress`.
- `OperationProgressTracker._broadcast_progress_update` — gone. The façade
  no longer talks to Redis directly; it calls
  `TaskExecutionTracker.update_progress`.
- `OperationProgressTracker.get_cached_progress` — retained for signature
  stability but always returns `None`. Use `get_progress()` (async, reads
  from Redis) instead.

## Task queues (Phase 1 — pending)

See [#6505](https://github.com/mrveiss/AutoBot-AI/issues/6505). Until that
phase lands, three task-queue implementations coexist:

- `celery_app.py` — canonical going forward
- `utils/task_queue.py` — Redis Streams + Sorted Sets, may stay as a #6468
  carve-out for atomic claim semantics
- `utils/background_task_manager.py` — to be deleted in Phase 1

## Periodic schedulers (Phase 3 — pending)

See [#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507). Decision tree
once that phase lands:

| Caller need | Use |
|---|---|
| Cron-like periodic execution (`*/5 * * * *`, `@hourly`) | Celery Beat |
| Event-driven wakeup (per-agent heartbeat) | `services/heartbeat_scheduler.py` |

`services/scheduling/cron_scheduler.py` and `knowledge/connectors/scheduler.py`
are scheduled for deletion in Phase 3.

## Cross-cutting

- All Redis access goes through `autobot_shared.redis_client.get_async_redis_client`
  — never the error-prone `get_redis_client(async_client=True)` (see
  [redis_client.py](../../autobot_shared/redis_client.py) for the rationale).
- All progress writes are best-effort: Redis errors log a warning and return,
  matching the legacy behavior.
