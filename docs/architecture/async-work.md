# Async Work — Unified Architecture

> Tracks the consolidation effort under umbrella issue [#6495](https://github.com/mrveiss/AutoBot-AI/issues/6495). This document is updated as each phase lands.
>
> - **Phase 1 — Task queues** ([#6505](https://github.com/mrveiss/AutoBot-AI/issues/6505)): ✅ **COMPLETE** — all 7 `BackgroundTaskManager` callers migrated to Celery; `background_task_manager.py` deleted; `task_queue.py` retained as [#6468](https://github.com/mrveiss/AutoBot-AI/issues/6468) carve-out
> - **Phase 2 — Progress trackers** ([#6506](https://github.com/mrveiss/AutoBot-AI/issues/6506)): **landed**
> - **Phase 3 — Periodic schedulers** ([#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507)): **landed**
>   - Beat deployment ([#6555](https://github.com/mrveiss/AutoBot-AI/issues/6555)): landed
>   - ConnectorScheduler multi-worker fix ([#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556)): landed
>   - cron_scheduler.py dead stub: deleted
> - **Wakeup coalescing** ([#6472](https://github.com/mrveiss/AutoBot-AI/issues/6472)): **landed** — dedup by (agent_id, task_id), merged_count observability column

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

## Unified facade — `async_work/` ([#6495](https://github.com/mrveiss/AutoBot-AI/issues/6495))

`autobot-backend/async_work/__init__.py` is the single public entry point for
all async-work operations.  New code should use this facade instead of the
legacy implementations directly.

```python
from async_work import get_task_queue, get_progress_tracker, get_periodic_scheduler

# Enqueue a Celery task
handle = await get_task_queue().enqueue("knowledge_tasks.rebuild_index", priority=5)

# Report progress inside a task
await get_progress_tracker().report(task_id, percent=50, current_step="Embedding")

# Schedule a periodic job
get_periodic_scheduler().schedule("nightly_cleanup", "0 2 * * *", cleanup_callback)
```

### Decision tree

```
Need async work?
├── One-off background task     → get_task_queue().enqueue()
├── Track progress of a task    → get_progress_tracker().report()
├── Run on a schedule (cron)    → get_periodic_scheduler().schedule()
│   └── Static schedule?        → prefer celery_app.conf.beat_schedule entry
├── Atomic-claim across workers → utils/task_queue.py  [carve-out, doc why]
└── Event-driven wakeup         → services/heartbeat_scheduler.py
```

## Task queues (Phase 1 — COMPLETE as of GH#6505)

See [#6505](https://github.com/mrveiss/AutoBot-AI/issues/6505). The
three-implementation era is over. **Celery is the sole task queue.**

### Canonical pattern

```python
from tasks.analytics_tasks import run_import_tree_analysis
from utils.celery_task_status import celery_result_to_status, store_latest_task_id
from celery.result import AsyncResult

# Enqueue
result = run_import_tree_analysis.delay()
await store_latest_task_id("import_task:", result.id)

# Poll status (returns BackgroundTaskManager-compatible dict)
status = celery_result_to_status(AsyncResult(result.id))
```

Progress is reported via `self.update_state(state="PROGRESS", meta={...})` in
`tasks/analytics_tasks.py`. The `celery_result_to_status()` helper in
`utils/celery_task_status.py` converts Celery state → the legacy response shape
the frontend already understands (`status`, `progress`, `current_step`, etc.).

### Carve-out: `utils/task_queue.py`

`utils/task_queue.py` (Redis Streams + SETNX) is **explicitly retained** as a
`#6468` carve-out. The NPU worker manager (`initialization/lifespan.py`)
requires atomic-claim semantics that Celery does not expose. Do **not** migrate
or delete this file until GH#6468 is resolved.

### Deleted

- `utils/background_task_manager.py` — deleted in GH#6505. All 7 callers
  migrated to `tasks/analytics_tasks.py` Celery tasks.

## Periodic schedulers

See [#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507). The current
landscape has **three patterns**, not two:

| Pattern | When to use | Implementation | Status |
|---|---|---|---|
| **Static cron** | Fixed schedules known at deploy time (knowledge cleanup, sync queue prune) | Celery Beat — `celery_app.conf.beat_schedule` | Deployed via `autobot-celery-beat.service` ([#6555](https://github.com/mrveiss/AutoBot-AI/issues/6555)) |
| **Dynamic per-entity recurring** | Schedules created/edited/deleted at runtime via API (per-connector sync intervals) | `knowledge/connectors/scheduler.py` (`ConnectorScheduler`) — Redis-backed + leader election (Option A, [#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556)) | Stable: schedules survive worker restart, status consistent across workers |
| **Event-driven wakeup** | "Wake me when X happens" not "wake me every N minutes" (per-agent heartbeat with explicit wakeup events) | `services/heartbeat_scheduler.py` | Stable as-is, do not migrate |

### Why three, not two

The original [#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507) plan
folded `ConnectorScheduler` into Beat. That assumes connectors are static
config — they aren't. Connectors are CRUD'd at runtime via `POST/DELETE
/knowledge_base/connectors/...`, each with its own interval. Beat reads
schedules from a static dict at startup; supporting dynamic schedules
requires either `celery-redbeat` (extra dependency) or coordinating Beat
restarts on every connector edit (terrible UX). The chosen approach ([#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556)) is
Option A: Redis-backed schedule persistence + leader election so any worker
can answer status queries and the elected leader runs the asyncio tasks.


### ConnectorScheduler — multi-worker design ([#6556](https://github.com/mrveiss/AutoBot-AI/issues/6556))

**Problem:** with 4 uvicorn workers, each `POST /knowledge_base/connectors` call
could land on a different worker. That worker's in-process singleton held the
schedule; the other three workers did not. After a worker restart the schedule
was silently lost.

**Solution (Option A):** Redis-backed schedules + leader election.

| Concern | Mechanism |
|---|---|
| Persist schedules | `connector:schedule:{id}` key in the `knowledge` Redis DB. `start()` writes; `stop()` deletes. |
| Consistent `scheduled` status | `is_running()` reads Redis — not the local asyncio task dict. Any worker answers correctly. |
| Single-flight execution | Leader key `connector:scheduler:leader` with 30 s TTL. One worker wins via `SET NX`; refreshes every 10 s via `GET`+`PEXPIRE`. |
| Restart recovery | When a leader dies its key expires. Within 15 s a non-leader wins election, calls `_reconcile_schedules()`, and rehydrates all `connector:schedule:*` keys into local asyncio tasks. |

All four workers call `begin_leader_election()` at startup
(wired in `initialization/lifespan.py:_start_connector_scheduler`).

### Celery Beat ([#6555](https://github.com/mrveiss/AutoBot-AI/issues/6555))

- Single-instance — `autobot-celery-beat.service` deployed on exactly one host.
- Reads schedules from `celery_app.conf.beat_schedule`.
- Persists next-run state to `/var/lib/autobot/celerybeat-schedule` (file lock
  prevents accidental multi-Beat startup on the same host).
- Restarts cascade: `restart celery beat` handler triggered on template change.
- Currently deployed schedules: `knowledge-cleanup-orphan-documents`,
  `knowledge-cleanup-generated-files`, `knowledge-sync-queue-prune`. Add new
  entries to `beat_schedule` and bump the deploy.

### Dead surface deleted

- `services/scheduling/cron_scheduler.py` — 44 LOC stub with no execution loop,
  zero callers. Deleted in [#6507](https://github.com/mrveiss/AutoBot-AI/issues/6507).

## Wakeup coalescing ([#6472](https://github.com/mrveiss/AutoBot-AI/issues/6472))

### Problem

Without deduplication, N simultaneous wakeup signals for the same
`(agent_id, task_id)` — e.g., `@-mention + assignment + cron` firing within
the same second — insert N rows and trigger N redundant agent runs, burning N×
tokens for the same effective work.

### Solution

`HeartbeatScheduler.wakeup()` checks for an existing un-consumed row with the
same `(agent_id, task_id)` before inserting. When found:

1. Context is merged (incoming keys win on conflict).
2. Priority is updated to `max(existing, incoming)`.
3. `merged_count` is incremented (observability column; default 0 on clean rows).
4. The existing row id is returned — no new row is inserted.

Coalescing is skipped when `context` is absent or does not contain `task_id`,
so non-task wakeups (interval ticks, manual triggers) are unaffected.

The `FOR UPDATE` lock on the existing row prevents a TOCTOU race where two
concurrent calls both see "no existing row" and both insert.

### Schema

`agent_wakeup_requests.merged_count INTEGER NOT NULL DEFAULT 0` — migration
`20260522_021`. Read this column in Grafana or the `/heartbeat/{agent_id}/wakeup`
API response to tune coalescing thresholds.

## Cross-cutting

- All Redis access goes through `autobot_shared.redis_client.get_async_redis_client`
  — never the error-prone `get_redis_client(async_client=True)` (see
  [redis_client.py](../../autobot_shared/redis_client.py) for the rationale).
- All progress writes are best-effort: Redis errors log a warning and return,
  matching the legacy behavior.
