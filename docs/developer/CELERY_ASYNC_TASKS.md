# Writing async Celery tasks (#20887)

A Celery task is a plain synchronous function; the code it calls is async and reaches
process-wide singletons (the SQLAlchemy async engine and session factory, async Redis
pools, the transcriber's aiosqlite connection). Each of those is bound to the event loop
that first used it.

## The rule

Drive every coroutine from a task through the worker's one persistent loop:

```python
from autobot_shared.worker_loop import run_in_worker_loop

@celery_app.task(name="tasks.example")
def example() -> dict:
    return run_in_worker_loop(_async_body())
```

`run_in_worker_loop` submits the coroutine to a loop that lives for the whole worker
process, blocks for the result, and cancels the pending future if the wait is interrupted
(soft time limit, `timeout=`). It is thread-safe and works with prefork, threads and gevent.

## Never

`asyncio.run(...)`, `new_event_loop()`, `get_event_loop()`, `set_event_loop()`,
`asyncio.Runner`, `anyio.run`, `async_to_sync`, `<loop>.run_until_complete(...)` and
`run_or_schedule(...)` inside a task module. A private loop closes when the call returns;
the next task then reuses a pool whose connections belong to the dead loop and fails with
`RuntimeError('Event loop is closed')`.

The lint rule `py-celery-private-event-loop` (severity block) enforces this over
`autobot-backend/{tasks,workers,llc/scheduler}/` and any file defining a Celery task. Its
`ALLOWLIST` is exactly three modules (`services/pricing_refresh.py`,
`services/provider_key_process_init.py`, `migrations/baseline.py`); migrate the caller
instead of adding a fourth.

## Lifecycle (wired in `autobot-backend/celery_app.py`)

| Signal | Action |
|---|---|
| `worker_process_init` | `reset_async_redis_pools()`, then `user_management.database.reset_after_fork()` (drops the inherited engine and factory without touching the parent's connections), then `start_worker_loop()` |
| `worker_process_shutdown` | `stop_worker_loop()`: disposes the engine, the transcriber connection and the Redis pools on the loop, then stops it |

Engines, session factories and Redis clients are created lazily, on the worker loop, by the
first task that needs them, and reused by every later task. Do not reset or dispose them per
task.

## `run_or_schedule`

`autobot_shared.async_compat.run_or_schedule` is for sync code that may run in either
context; it is not for tasks.

| Caller | Behaviour |
|---|---|
| inside a Celery worker | worker loop |
| no loop running in the thread (CLI, script) | `asyncio.run` |
| a loop is running in the thread, API process | submitted to the main loop registered by the lifespan (`register_main_loop`) with `run_coroutine_threadsafe` |
| called on the main loop's own thread | cannot block on itself; falls back to a thread with its own loop |

## Trade-off

One loop per worker means a runaway coroutine delays later tasks in the same child. The
bounds are Celery's time limits and the future cancellation above.
