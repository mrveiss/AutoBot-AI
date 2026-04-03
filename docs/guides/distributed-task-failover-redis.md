# Distributed Task Failover with Redis


## Quick Answer

**How do you configure distributed task failover with Redis in AutoBot?**

Use the `TaskQueue` class to enqueue tasks with priority, register workers with
heartbeats, and let the failover monitor automatically migrate tasks from dead
workers. Here is a complete example showing task creation, worker registration,
and explicit failover migration:

```python
#!/usr/bin/env python3
"""Distributed task failover with Redis: enqueue, heartbeat, and migrate."""

import asyncio
import json
import time
import logging

from autobot_shared.redis_client import get_redis_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

HEARTBEAT_TTL = 45  # seconds -- worker considered dead after this


async def enqueue_task(queue_name: str, task_id: str, payload: dict, priority: int = 2):
    """Enqueue a task into a Redis-backed priority queue.

    Args:
        queue_name: Name of the task queue (e.g., "npu_inference").
        task_id: Unique task identifier.
        payload: Task payload dict.
        priority: 1=LOW, 2=NORMAL, 3=HIGH, 4=CRITICAL.
    """
    redis = await get_redis_client(async_client=True, database="main")
    score = priority * 1_000_000 + int(time.time())

    task_data = {
        "id": task_id,
        "type": queue_name,
        "payload": json.dumps(payload),
        "status": "queued",
        "priority": str(priority),
        "created_at": str(time.time()),
        "max_retries": "3",
        "retry_count": "0",
        "worker_id": "",
    }
    await redis.hset(f"{queue_name}:tasks", task_id, json.dumps(task_data))
    await redis.zadd(f"{queue_name}:pending", {task_id: score})
    logger.info("Enqueued task %s with priority %d", task_id, priority)


async def register_worker(worker_id: str, capabilities: list[str]):
    """Register a worker and start its heartbeat loop.

    Args:
        worker_id: Unique worker identifier (e.g., "npu-worker-1").
        capabilities: List of task types this worker can handle.
    """
    redis = await get_redis_client(async_client=True, database="main")
    await redis.sadd("workers:registered", worker_id)
    await redis.hset(f"worker:{worker_id}:config", mapping={
        "capabilities": json.dumps(capabilities),
        "max_concurrent": "3",
    })

    while True:
        heartbeat = {
            "worker_id": worker_id,
            "timestamp": time.time(),
            "load": 0,
            "tasks_active": 0,
            "capabilities": capabilities,
        }
        await redis.set(
            f"worker:{worker_id}:heartbeat",
            json.dumps(heartbeat),
            ex=HEARTBEAT_TTL,
        )
        await asyncio.sleep(15)


async def check_and_migrate_tasks(queue_name: str):
    """Detect dead workers and migrate their tasks back to pending.

    Checks all registered workers for expired heartbeats. Tasks assigned
    to dead workers are moved from running back to pending with incremented
    retry_count.
    """
    redis = await get_redis_client(async_client=True, database="main")
    workers = await redis.smembers("workers:registered")

    for worker_id_bytes in workers:
        worker_id = worker_id_bytes.decode()
        heartbeat = await redis.get(f"worker:{worker_id}:heartbeat")

        if heartbeat is None:
            # Worker is dead -- migrate its tasks
            task_ids = await redis.smembers(f"worker:{worker_id}:tasks")
            for tid_bytes in task_ids:
                task_id = tid_bytes.decode()
                raw = await redis.hget(f"{queue_name}:tasks", task_id)
                if raw is None:
                    continue
                task = json.loads(raw)
                retries = int(task.get("retry_count", 0))

                if retries >= int(task.get("max_retries", 3)):
                    # Move to failed permanently
                    await redis.zadd(f"{queue_name}:failed", {task_id: time.time()})
                    task["status"] = "failed_permanent"
                    logger.warning("Task %s exceeded max retries", task_id)
                else:
                    # Re-enqueue with incremented retry count
                    task["retry_count"] = str(retries + 1)
                    task["status"] = "queued"
                    task["previous_worker"] = worker_id
                    task["worker_id"] = ""
                    score = int(task["priority"]) * 1_000_000 + int(time.time())
                    await redis.zadd(f"{queue_name}:pending", {task_id: score})
                    await redis.zrem(f"{queue_name}:running", task_id)
                    logger.info("Migrated task %s from dead worker %s (retry %d)",
                                task_id, worker_id, retries + 1)

                await redis.hset(f"{queue_name}:tasks", task_id, json.dumps(task))

            # Log the failover event
            event = {"worker": worker_id, "tasks": len(task_ids), "time": time.time()}
            await redis.lpush("failover:log", json.dumps(event))
            await redis.srem("workers:registered", worker_id)


if __name__ == "__main__":
    asyncio.run(enqueue_task("npu_inference", "task-001", {"model": "yolov8"}))
```

For the full task lifecycle, NPU worker distribution, and scheduler integration,
see [Section 3](#3-task-lifecycle) and [Section 5](#5-failover-detection-and-task-migration).

---


> **Scope:** AutoBot's distributed task execution system across the 6-VM fleet,
> using Redis-backed queues for task assignment, heartbeat monitoring, and
> automatic failover when worker nodes become unreachable.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Task Queue Data Structures](#2-task-queue-data-structures)
3. [Task Lifecycle](#3-task-lifecycle)
4. [Worker Registration and Heartbeat](#4-worker-registration-and-heartbeat)
5. [Failover Detection and Task Migration](#5-failover-detection-and-task-migration)
6. [NPU Worker Task Distribution](#6-npu-worker-task-distribution)
7. [Scheduler Integration](#7-scheduler-integration)
8. [Long-Running Operations](#8-long-running-operations)
9. [Complete Failover Configuration Example](#9-complete-failover-configuration-example)
10. [Redis Connection Best Practices](#10-redis-connection-best-practices)
11. [Monitoring and Observability](#11-monitoring-and-observability)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

AutoBot distributes work across a fleet of six virtual machines. A central
Redis Stack instance on the Redis VM acts as the shared coordination layer
for task queues, worker heartbeats, failover state, and result storage.

### Fleet Topology

```
                         +---------------------+
                         |   Redis VM (.23)    |
                         |   Redis Stack       |
                         |   Port 6379         |
                         +----------+----------+
                                    |
           +------------------------+------------------------+
           |                        |                        |
+----------+----------+  +----------+----------+  +----------+----------+
|   Main VM (.20)     |  |   NPU VM (.22)      |  |  AI Stack VM (.24) |
|   Backend API       |  |   OpenVINO Worker   |  |  AI Processing     |
|   Scheduler         |  |   Port 8081         |  |  TTS Worker (8082) |
|   Failover Monitor  |  +---------------------+  +---------------------+
+---------------------+
           |
+----------+----------+  +---------------------+  +---------------------+
|  Frontend VM (.21)  |  |  Browser VM (.25)   |  |  SLM Server (.19)  |
|  nginx / Vue.js     |  |  Playwright         |  |  Fleet Management  |
+---------------------+  +---------------------+  +---------------------+
```

### Redis Database Allocation

AutoBot logically partitions a single Redis Stack instance into named
databases. The canonical mapping lives in
`autobot-backend/utils/redis_management/types.py`:

| Database Name  | DB Number | Purpose                                  |
|----------------|-----------|------------------------------------------|
| `main`         | 0         | Task queues, worker state, general cache |
| `knowledge`    | 1         | Knowledge base vectors and embeddings    |
| `prompts`      | 2         | LLM prompt templates and agent configs   |
| `agents`       | 3         | Agent communication and orchestration    |
| `metrics`      | 4         | Performance metrics and analytics data   |
| `cache`        | 5         | General application cache                |
| `sessions`     | 6         | User sessions and distributed locks      |
| `workflows`    | 7         | Workflow state tracking                  |
| `vectors`      | 8         | Vector embeddings                        |
| `analytics`    | 9         | Codebase analytics and indexing state    |
| `websockets`   | 10        | WebSocket connection state               |
| `config`       | 11        | Cache configuration storage              |
| `audit`        | 12        | Security audit logging (OWASP/NIST)      |

All task queues, worker heartbeats, and failover state described in this
document reside in **DB 0 (`main`)**.

### Connection Architecture

Every Redis connection flows through the canonical client module. The
`RedisConnectionManager` singleton provides:

- **Connection pooling** -- one pool per database, max 20 connections each
- **Circuit breaker** -- opens after 5 consecutive failures, resets after 60 s
- **TCP keepalive** -- prevents idle connection drops across the VM network
- **Exponential backoff** -- retries with `tenacity` (up to 5 attempts)
- **WeakSet tracking** -- connections tracked without interfering with GC
- **Lazy initialization** -- pools created on first use, not at import time

```python
from autobot_shared.redis_client import get_redis_client

# Synchronous client for task management
redis_sync = get_redis_client(async_client=False, database="main")

# Asynchronous client for heartbeat loops and failover monitors
redis_async = await get_redis_client(async_client=True, database="main")
```

> **Rule:** Never instantiate `redis.Redis(host=..., port=...)` directly.
> The pre-commit hook enforces this. See `CLAUDE.md` Rule 2.

---

## 2. Task Queue Data Structures

The failover system relies on the following Redis key patterns, all stored
in DB 0 (`main`):

### Key Schema

AutoBot's `TaskQueue` (in `autobot-backend/utils/task_queue.py`) uses **sorted sets
(ZSET)** with priority scoring rather than simple LIST-based FIFO:

```
{queue_name}:pending                - ZSET   (priority-sorted pending tasks)
{queue_name}:running                - ZSET   (currently executing, scored by start time)
{queue_name}:completed              - ZSET   (finished tasks, scored by completion time)
{queue_name}:failed                 - ZSET   (failed tasks, scored by failure time)
{queue_name}:scheduled              - ZSET   (delayed execution, scored by due time)
{queue_name}:tasks                  - HASH   (task_id -> serialized Task JSON)
{queue_name}:results                - HASH   (task_id -> serialized TaskResult JSON)
worker:{worker_id}:heartbeat        - STRING (JSON heartbeat payload, TTL 45s)
worker:{worker_id}:tasks            - SET    (task IDs assigned to this worker)
worker:{worker_id}:config           - HASH   (worker capabilities and metadata)
workers:registered                  - SET    (all registered worker IDs)
failover:log                        - LIST   (audit trail of migration events)
npu:worker:{worker_id}:status       - STRING (NPUWorkerStatus JSON, TTL 2x health interval)
```

**Priority scoring:** `priority_score = priority.value * 1000000 + int(time.time())`
Tasks are dequeued with `ZREVRANGE` (highest priority first).

**Priority levels** (`TaskPriority` enum):

| Level    | Value | Score Range |
| -------- | ----- | ----------- |
| LOW      | 1     | 1,000,000+  |
| NORMAL   | 2     | 2,000,000+  |
| HIGH     | 3     | 3,000,000+  |
| CRITICAL | 4     | 4,000,000+  |

### Data Formats

**Task Hash** (`task:{task_id}`):

```json
{
    "id":              "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "type":            "npu_inference",
    "payload":         "{\"model\": \"yolov8\", \"image_path\": \"/data/input.jpg\"}",
    "status":          "queued",
    "priority":        "normal",
    "created_at":      "1710000000.0",
    "max_retries":     "3",
    "retry_count":     "0",
    "worker_id":       "",
    "previous_worker": "",
    "requeued_at":     ""
}
```

Valid `status` values: `queued`, `running`, `completed`, `failed`,
`failed_permanent`, `cancelled`.

**Worker Heartbeat** (`worker:{worker_id}:heartbeat`):

```json
{
    "worker_id":    "npu-worker-1",
    "timestamp":    1710000000.0,
    "load":         2,
    "tasks_active": 3,
    "capabilities": ["npu_inference", "vision"],
    "memory_mb":    1024
}
```

The heartbeat key has a TTL of `heartbeat_interval * 3` (default: 45
seconds). When the key expires, the failover monitor treats the worker as
dead.

---

## 3. Task Lifecycle

A task moves through five stages: **enqueue**, **assign**, **execute**,
**complete**, and **clean up**. At each stage, Redis state is updated
atomically to prevent double-processing.

### Stage 1 -- Enqueue

The producer creates a task hash and pushes the task ID onto the
appropriate queue.

```python
import json
import logging
import time
import uuid

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def enqueue_task(
    queue_name: str,
    task_type: str,
    payload: dict,
    priority: str = "normal",
    max_retries: int = 3,
) -> str:
    """Enqueue a task into the distributed Redis queue.

    Creates a task hash in Redis and pushes the task ID onto the
    named queue list. The task starts in ``queued`` status and will
    be picked up by the next available worker.

    Args:
        queue_name: Target queue name (e.g. ``npu_tasks``,
            ``ai_stack_tasks``).
        task_type: Logical task type used for worker routing.
        payload: Arbitrary JSON-serializable task data.
        priority: One of ``low``, ``normal``, ``high``, ``critical``.
        max_retries: Maximum retry attempts before permanent failure.

    Returns:
        The generated UUID task ID.

    Raises:
        RuntimeError: If the Redis client is unavailable.

    Example:
        >>> task_id = enqueue_task(
        ...     queue_name="npu_tasks",
        ...     task_type="npu_inference",
        ...     payload={"model": "yolov8", "image_path": "/data/img.jpg"},
        ...     priority="high",
        ... )
        >>> print(task_id)
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    redis = get_redis_client(async_client=False, database="main")
    if redis is None:
        raise RuntimeError("Redis client unavailable -- check connection")

    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "type": task_type,
        "payload": json.dumps(payload),
        "status": "queued",
        "priority": priority,
        "created_at": str(time.time()),
        "max_retries": str(max_retries),
        "retry_count": "0",
        "worker_id": "",
        "previous_worker": "",
        "requeued_at": "",
    }

    # Atomic: write task hash then push to queue
    pipe = redis.pipeline(transaction=True)
    pipe.hset(f"task:{task_id}", mapping=task)
    pipe.lpush(f"queue:{queue_name}", task_id)
    pipe.execute()

    logger.info(
        "Enqueued task %s on queue:%s (type=%s, priority=%s)",
        task_id,
        queue_name,
        task_type,
        priority,
    )
    return task_id
```

### Stage 2 -- Assign (Atomic Pop)

A worker atomically moves a task ID from the main queue into a processing
list. This prevents two workers from claiming the same task.

```python
def claim_task(
    queue_name: str,
    worker_id: str,
    timeout: int = 30,
) -> str | None:
    """Claim the next task from a queue for a specific worker.

    Uses ``BRPOPLPUSH`` to atomically move a task ID from the
    main queue into a per-queue processing list. The task hash is
    updated to ``running`` status and bound to the claiming worker.

    Args:
        queue_name: Source queue name.
        worker_id: ID of the claiming worker.
        timeout: Seconds to block waiting for a task. Pass ``0``
            for non-blocking.

    Returns:
        The claimed task ID, or ``None`` if no task was available
        within the timeout.

    Example:
        >>> task_id = claim_task("npu_tasks", "npu-worker-1")
        >>> if task_id:
        ...     process(task_id)
    """
    redis = get_redis_client(async_client=False, database="main")
    if redis is None:
        return None

    # Atomic move: queue -> processing list
    raw = redis.brpoplpush(
        f"queue:{queue_name}",
        f"queue:{queue_name}:processing",
        timeout=timeout,
    )
    if raw is None:
        return None

    task_id = raw.decode() if isinstance(raw, bytes) else raw

    # Mark task as running and bind to worker
    pipe = redis.pipeline(transaction=True)
    pipe.hset(
        f"task:{task_id}",
        mapping={
            "status": "running",
            "worker_id": worker_id,
            "started_at": str(time.time()),
        },
    )
    pipe.sadd(f"worker:{worker_id}:tasks", task_id)
    pipe.execute()

    logger.info("Worker %s claimed task %s", worker_id, task_id)
    return task_id
```

### Stage 3 -- Complete

When a worker finishes a task, it stores the result, cleans up the
processing list, and removes the task from its own task set.

```python
def complete_task(
    queue_name: str,
    worker_id: str,
    task_id: str,
    result: dict,
    result_ttl: int = 3600,
) -> None:
    """Mark a task as completed and store its result.

    Updates the task hash status to ``completed``, stores the
    serialized result with a TTL, and removes the task from both
    the processing list and the worker's task set.

    Args:
        queue_name: The queue the task was claimed from.
        worker_id: ID of the worker that processed the task.
        task_id: The task ID being completed.
        result: JSON-serializable result data.
        result_ttl: Seconds to keep the result before expiry.

    Example:
        >>> complete_task(
        ...     "npu_tasks",
        ...     "npu-worker-1",
        ...     task_id,
        ...     {"detections": [{"label": "person", "confidence": 0.97}]},
        ... )
    """
    redis = get_redis_client(async_client=False, database="main")
    if redis is None:
        logger.error("Redis unavailable during task completion")
        return

    pipe = redis.pipeline(transaction=True)
    pipe.hset(
        f"task:{task_id}",
        mapping={
            "status": "completed",
            "completed_at": str(time.time()),
        },
    )
    pipe.setex(
        f"task:{task_id}:result",
        result_ttl,
        json.dumps(result),
    )
    pipe.srem(f"worker:{worker_id}:tasks", task_id)
    pipe.lrem(f"queue:{queue_name}:processing", 1, task_id)
    pipe.execute()

    logger.info("Task %s completed by worker %s", task_id, worker_id)
```

### Stage 4 -- Failure (with Retry)

If a task fails during execution, the worker can re-enqueue it up to
`max_retries` times.

```python
def fail_task(
    queue_name: str,
    worker_id: str,
    task_id: str,
    error_message: str,
) -> bool:
    """Record a task failure and re-enqueue if retries remain.

    Increments the retry counter. If retries remain, the task is
    pushed back onto the queue with status ``queued``. Otherwise
    it is marked ``failed_permanent``.

    Args:
        queue_name: Queue the task belongs to.
        worker_id: ID of the worker that encountered the failure.
        task_id: The failing task ID.
        error_message: Human-readable error description.

    Returns:
        ``True`` if the task was re-queued, ``False`` if it has
        permanently failed.

    Example:
        >>> requeued = fail_task(
        ...     "npu_tasks", "npu-worker-1", task_id, "OOM on model load"
        ... )
    """
    redis = get_redis_client(async_client=False, database="main")
    if redis is None:
        return False

    task_data = redis.hgetall(f"task:{task_id}")
    if not task_data:
        logger.error("Task %s not found during failure handling", task_id)
        return False

    retry_count = int(task_data.get(b"retry_count", 0))
    max_retries = int(task_data.get(b"max_retries", 3))

    pipe = redis.pipeline(transaction=True)
    pipe.srem(f"worker:{worker_id}:tasks", task_id)
    pipe.lrem(f"queue:{queue_name}:processing", 1, task_id)

    if retry_count < max_retries:
        pipe.hset(
            f"task:{task_id}",
            mapping={
                "status": "queued",
                "retry_count": str(retry_count + 1),
                "previous_worker": worker_id,
                "requeued_at": str(time.time()),
                "last_error": error_message,
                "worker_id": "",
            },
        )
        pipe.lpush(f"queue:{queue_name}", task_id)
        pipe.execute()

        logger.warning(
            "Task %s re-queued (retry %d/%d): %s",
            task_id,
            retry_count + 1,
            max_retries,
            error_message,
        )
        return True
    else:
        pipe.hset(
            f"task:{task_id}",
            mapping={
                "status": "failed_permanent",
                "last_error": error_message,
                "failed_at": str(time.time()),
            },
        )
        pipe.execute()

        logger.error(
            "Task %s permanently failed after %d retries: %s",
            task_id,
            max_retries,
            error_message,
        )
        return False
```

### Lifecycle Diagram

```
  Producer                    Redis                      Worker
     |                          |                          |
     |---LPUSH queue:name------>|                          |
     |   HSET task:{id}         |                          |
     |                          |<---BRPOPLPUSH------------|
     |                          |    queue -> processing    |
     |                          |   HSET status=running     |
     |                          |   SADD worker:tasks       |
     |                          |                          |
     |                          |        [processing]       |
     |                          |                          |
     |                          |<---HSET status=completed--|
     |                          |    SETEX result (TTL)     |
     |                          |    SREM worker:tasks      |
     |                          |    LREM processing        |
     |                          |                          |
```

---

## 4. Worker Registration and Heartbeat

Workers must register before claiming tasks. Once registered, they send
periodic heartbeats. If a heartbeat key expires (TTL lapses), the failover
monitor treats the worker as dead.

### Worker Registration

```python
import asyncio
import json
import logging
import time

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def register_worker(
    worker_id: str,
    capabilities: list[str],
    max_concurrent: int = 4,
) -> None:
    """Register a worker node with its capabilities.

    Stores the worker configuration hash and adds the worker ID
    to the global ``workers:registered`` set. Registration must
    complete before the worker can claim tasks or send heartbeats.

    Args:
        worker_id: Unique worker identifier (e.g. ``npu-worker-1``).
        capabilities: List of task types this worker can handle
            (e.g. ``["npu_inference", "vision"]``).
        max_concurrent: Maximum simultaneous tasks.

    Example:
        >>> await register_worker(
        ...     "npu-worker-1",
        ...     capabilities=["npu_inference", "vision"],
        ...     max_concurrent=4,
        ... )
    """
    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        raise RuntimeError("Redis unavailable for worker registration")

    config = {
        "id": worker_id,
        "capabilities": json.dumps(capabilities),
        "max_concurrent": str(max_concurrent),
        "registered_at": str(time.time()),
        "status": "active",
    }

    pipe = redis.pipeline(transaction=True)
    pipe.hset(f"worker:{worker_id}:config", mapping=config)
    pipe.sadd("workers:registered", worker_id)
    await pipe.execute()

    logger.info(
        "Registered worker %s (capabilities=%s, max_concurrent=%d)",
        worker_id,
        capabilities,
        max_concurrent,
    )
```

### Heartbeat Loop

Each worker runs a heartbeat coroutine that periodically writes a
self-expiring key. The TTL is set to three times the heartbeat interval,
giving the worker two missed beats before being declared dead.

```python
async def get_current_load(worker_id: str) -> int:
    """Return the number of tasks currently assigned to this worker.

    Args:
        worker_id: The worker whose load to check.

    Returns:
        Count of active tasks.
    """
    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        return 0
    return await redis.scard(f"worker:{worker_id}:tasks")


async def worker_heartbeat(
    worker_id: str,
    interval: int = 15,
) -> None:
    """Send periodic heartbeats to indicate a worker is alive.

    Writes a JSON payload to ``worker:{worker_id}:heartbeat`` with
    a TTL of ``interval * 3``. If the worker crashes or loses
    network connectivity, the key expires and the failover monitor
    will migrate its tasks.

    This coroutine runs indefinitely and should be launched as a
    background task during worker startup.

    Args:
        worker_id: The worker sending heartbeats.
        interval: Seconds between heartbeats. Default ``15``.

    Example:
        >>> asyncio.create_task(worker_heartbeat("npu-worker-1"))
    """
    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        raise RuntimeError("Redis unavailable for heartbeat")

    ttl = interval * 3  # Tolerate up to 2 missed beats

    while True:
        try:
            load = await get_current_load(worker_id)
            payload = json.dumps({
                "worker_id": worker_id,
                "timestamp": time.time(),
                "load": load,
                "tasks_active": load,
            })
            await redis.setex(
                f"worker:{worker_id}:heartbeat",
                ttl,
                payload,
            )
            logger.debug(
                "Heartbeat sent for %s (load=%d, ttl=%ds)",
                worker_id,
                load,
                ttl,
            )
        except Exception as exc:
            logger.error(
                "Heartbeat failed for %s: %s", worker_id, exc
            )
        await asyncio.sleep(interval)
```

### Graceful Deregistration

When a worker shuts down cleanly, it should deregister to avoid
unnecessary failover processing.

```python
async def deregister_worker(worker_id: str) -> None:
    """Gracefully deregister a worker and release its tasks.

    Removes the worker from the registered set, deletes its
    heartbeat and config keys, and re-queues any tasks that
    were still assigned to it.

    Args:
        worker_id: The worker being deregistered.

    Example:
        >>> await deregister_worker("npu-worker-1")
    """
    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        return

    # Re-queue any remaining tasks
    remaining_tasks = await redis.smembers(f"worker:{worker_id}:tasks")
    for task_id_bytes in remaining_tasks:
        task_id = (
            task_id_bytes.decode()
            if isinstance(task_id_bytes, bytes)
            else task_id_bytes
        )
        task_data = await redis.hgetall(f"task:{task_id}")
        if task_data:
            task_type = task_data.get(b"type", b"default").decode()
            await redis.hset(
                f"task:{task_id}",
                mapping={
                    "status": "queued",
                    "worker_id": "",
                    "requeued_at": str(time.time()),
                },
            )
            await redis.lpush(f"queue:{task_type}", task_id)
            logger.info(
                "Re-queued task %s from deregistering worker %s",
                task_id,
                worker_id,
            )

    # Clean up worker keys
    pipe = redis.pipeline(transaction=True)
    pipe.delete(f"worker:{worker_id}:heartbeat")
    pipe.delete(f"worker:{worker_id}:tasks")
    pipe.delete(f"worker:{worker_id}:config")
    pipe.srem("workers:registered", worker_id)
    await pipe.execute()

    logger.info("Worker %s deregistered", worker_id)
```

---

## 5. Failover Detection and Task Migration

The failover monitor runs on the Main VM (.20) as part of the backend
process. It periodically checks for workers whose heartbeat keys have
expired and migrates their orphaned tasks back to the queue.

### Detection Strategy

1. Read the `workers:registered` set to get all known worker IDs.
2. For each worker, check whether `worker:{worker_id}:heartbeat` exists.
3. If the key is missing (TTL expired), the worker is presumed dead.
4. Read `worker:{worker_id}:tasks` to find orphaned task IDs.
5. For each orphaned task, either re-queue (if retries remain) or mark as
   permanently failed.
6. Clean up the dead worker's keys and remove it from the registered set.

### Failover Monitor Implementation

```python
import asyncio
import json
import logging
import time

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


async def _migrate_orphaned_task(
    redis,
    task_id: str,
    dead_worker_id: str,
) -> None:
    """Migrate a single orphaned task from a dead worker.

    If the task has retries remaining, it is re-queued with an
    incremented retry count. Otherwise it is marked as permanently
    failed.

    Args:
        redis: Async Redis client (DB ``main``).
        task_id: ID of the orphaned task.
        dead_worker_id: ID of the worker that died.
    """
    task_data = await redis.hgetall(f"task:{task_id}")
    if not task_data:
        logger.warning(
            "Orphaned task %s has no hash -- skipping", task_id
        )
        return

    retry_count = int(task_data.get(b"retry_count", 0))
    max_retries = int(task_data.get(b"max_retries", 3))
    task_type = task_data.get(b"type", b"default").decode()

    if retry_count < max_retries:
        await redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "queued",
                "retry_count": str(retry_count + 1),
                "previous_worker": dead_worker_id,
                "requeued_at": str(time.time()),
                "worker_id": "",
            },
        )
        queue_name = f"queue:{task_type}"
        await redis.lpush(queue_name, task_id)

        logger.info(
            "Task %s re-queued (retry %d/%d) from dead worker %s",
            task_id,
            retry_count + 1,
            max_retries,
            dead_worker_id,
        )
    else:
        await redis.hset(
            f"task:{task_id}",
            mapping={
                "status": "failed_permanent",
                "failed_at": str(time.time()),
                "last_error": (
                    f"Worker {dead_worker_id} died; max retries exhausted"
                ),
            },
        )
        logger.error(
            "Task %s permanently failed after %d retries "
            "(worker %s died)",
            task_id,
            max_retries,
            dead_worker_id,
        )


async def _log_failover_event(
    redis,
    dead_worker_id: str,
    orphaned_count: int,
    migrated_count: int,
) -> None:
    """Append a failover event to the audit log in Redis.

    Args:
        redis: Async Redis client.
        dead_worker_id: The worker that was detected as dead.
        orphaned_count: Total orphaned tasks found.
        migrated_count: Tasks successfully re-queued.
    """
    event = json.dumps({
        "event": "worker_failover",
        "worker_id": dead_worker_id,
        "orphaned_tasks": orphaned_count,
        "migrated_tasks": migrated_count,
        "timestamp": time.time(),
    })
    await redis.lpush("failover:log", event)
    # Keep only the last 500 events
    await redis.ltrim("failover:log", 0, 499)


async def detect_and_migrate_failed_tasks(
    check_interval: int = 30,
) -> None:
    """Continuously detect dead workers and migrate their tasks.

    This coroutine runs an infinite loop that:

    1. Reads all registered worker IDs from the ``workers:registered``
       set.
    2. Checks each worker's heartbeat key. If the key has expired
       (i.e., ``GET worker:{id}:heartbeat`` returns ``None``), the
       worker is presumed dead.
    3. Reads the dead worker's ``worker:{id}:tasks`` set to find
       orphaned tasks.
    4. For each orphaned task, either re-queues it (incrementing
       ``retry_count``) or marks it ``failed_permanent`` if retries
       are exhausted.
    5. Cleans up the dead worker's Redis keys and removes it from
       the registered set.
    6. Logs a failover event to ``failover:log``.

    The check runs every ``check_interval`` seconds (default 30).

    Args:
        check_interval: Seconds between failover scans.

    Example:
        Launch as a background task during backend startup::

            asyncio.create_task(
                detect_and_migrate_failed_tasks(check_interval=30)
            )
    """
    redis = await get_redis_client(async_client=True, database="main")
    if redis is None:
        logger.error("Redis unavailable -- failover monitor cannot start")
        return

    logger.info(
        "Failover monitor started (check_interval=%ds)", check_interval
    )

    while True:
        try:
            registered = await redis.smembers("workers:registered")

            for worker_id_bytes in registered:
                worker_id = (
                    worker_id_bytes.decode()
                    if isinstance(worker_id_bytes, bytes)
                    else worker_id_bytes
                )

                # Check heartbeat
                heartbeat = await redis.get(
                    f"worker:{worker_id}:heartbeat"
                )
                if heartbeat is not None:
                    continue  # Worker is alive

                logger.warning(
                    "Worker %s heartbeat expired -- initiating failover",
                    worker_id,
                )

                # Gather orphaned tasks
                orphaned_raw = await redis.smembers(
                    f"worker:{worker_id}:tasks"
                )
                orphaned_tasks = [
                    t.decode() if isinstance(t, bytes) else t
                    for t in orphaned_raw
                ]

                migrated = 0
                for task_id in orphaned_tasks:
                    await _migrate_orphaned_task(
                        redis, task_id, worker_id
                    )
                    migrated += 1

                # Audit log
                await _log_failover_event(
                    redis,
                    worker_id,
                    len(orphaned_tasks),
                    migrated,
                )

                # Clean up dead worker
                pipe = redis.pipeline(transaction=True)
                pipe.delete(f"worker:{worker_id}:tasks")
                pipe.delete(f"worker:{worker_id}:config")
                pipe.srem("workers:registered", worker_id)
                await pipe.execute()

                logger.info(
                    "Failover complete for worker %s: "
                    "%d/%d tasks migrated",
                    worker_id,
                    migrated,
                    len(orphaned_tasks),
                )

        except Exception as exc:
            logger.error("Failover monitor error: %s", exc)

        await asyncio.sleep(check_interval)
```

### Failover Sequence Diagram

```
  Failover Monitor              Redis                     Queue
        |                         |                         |
        |--SMEMBERS registered--->|                         |
        |<--{w1, w2, w3}---------|                         |
        |                         |                         |
        |--GET w2:heartbeat------>|                         |
        |<--None (expired)--------|                         |
        |                         |                         |
        |--SMEMBERS w2:tasks----->|                         |
        |<--{task_A, task_B}------|                         |
        |                         |                         |
        |--HSET task_A queued---->|                         |
        |--LPUSH queue:type------>|--task_A available------>|
        |                         |                         |
        |--HSET task_B failed---->|  (max retries hit)      |
        |                         |                         |
        |--DEL w2:tasks---------->|                         |
        |--SREM registered w2---->|                         |
        |                         |                         |
```

---

## 6. NPU Worker Task Distribution

The NPU worker pool is managed through `api/npu_workers.py` and
`services/npu_worker_manager.py`. Workers are paired (not self-registered)
from the main host and monitored with background health checks that use
exponential backoff.

### API Endpoints

All endpoints require admin authentication and are prefixed with `/api`.

| Method   | Path                              | Description                                |
|----------|-----------------------------------|--------------------------------------------|
| `GET`    | `/npu/workers`                    | List all registered workers                |
| `POST`   | `/npu/workers`                    | Register a new worker (manual)             |
| `POST`   | `/npu/workers/pair`               | Pair with a worker at a given URL          |
| `GET`    | `/npu/workers/{id}`               | Get worker details                         |
| `PUT`    | `/npu/workers/{id}`               | Update worker configuration                |
| `DELETE` | `/npu/workers/{id}`               | Remove a worker                            |
| `POST`   | `/npu/workers/{id}/test`          | Test worker connectivity                   |
| `GET`    | `/npu/workers/{id}/metrics`       | Get worker performance metrics             |
| `POST`   | `/npu/workers/{id}/unpair`        | Unpair worker from master                  |
| `POST`   | `/npu/workers/{id}/repair`        | Re-pair a previously unpaired worker       |
| `GET`    | `/npu/load-balancing`             | Get load balancing configuration           |
| `PUT`    | `/npu/load-balancing`             | Update load balancing configuration        |
| `GET`    | `/npu/status`                     | Get NPU worker pool status                 |
| `POST`   | `/npu/workers/heartbeat`          | Receive heartbeat (paired workers only)    |
| `GET`    | `/npu/pool/stats`                 | Get pool-level statistics                  |
| `GET`    | `/npu/pool/workers`               | Get per-worker health states               |
| `POST`   | `/npu/pool/reload`                | Hot-reload pool configuration              |

### Pairing a Worker

```bash
curl -sk -X POST https://<backend-ip>:8443/api/npu/workers/pair \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "url": "http://<npu-ip>:8081",
        "name": "NPU Worker VM22",
        "platform": "linux",
        "max_concurrent_tasks": 4,
        "priority": 8
    }'
```

### Load Balancing Strategies

Configured through `PUT /api/npu/load-balancing`. The `LoadBalancingConfig`
model (from `models/npu_models.py`) supports:

| Strategy        | Key                    | Behavior                                      |
|-----------------|------------------------|-----------------------------------------------|
| `round-robin`   | `ROUND_ROBIN`          | Distribute tasks evenly across workers         |
| `least-loaded`  | `LEAST_LOADED`         | Route to worker with fewest active tasks       |
| `weighted`      | `WEIGHTED`             | Factor in worker weights (1--100)              |
| `priority`      | `PRIORITY`             | Use worker priority levels (1--10)             |

Default: `least-loaded` with a 30-second health check interval and
10-second timeout.

```python
from models.npu_models import LoadBalancingConfig, LoadBalancingStrategy

config = LoadBalancingConfig(
    strategy=LoadBalancingStrategy.LEAST_LOADED,
    health_check_interval=30,
    timeout_seconds=10,
    retry_failed_workers=True,
    retry_cooldown_seconds=60,
)
```

### Health Check with Exponential Backoff

The `NPUWorkerManager` tracks consecutive health check failures per worker
and applies exponential backoff (1x, 2x, 4x, 8x the base interval):

```python
# From services/npu_worker_manager.py -- backoff logic
_MIN_BACKOFF_MULTIPLIER = 1
_MAX_BACKOFF_MULTIPLIER = 8  # Max 8x interval (4 min at 30s base)

def _get_backoff_multiplier(self, worker_id: str) -> int:
    """Get backoff multiplier based on consecutive failures.

    Returns:
        Multiplier for health check interval (1, 2, 4, or 8).
    """
    failures = self._worker_failure_counts.get(worker_id, 0)
    multiplier = min(2 ** failures, self._MAX_BACKOFF_MULTIPLIER)
    return max(multiplier, self._MIN_BACKOFF_MULTIPLIER)
```

A successful health check resets the failure count to zero.

---

## 7. Scheduler Integration

The workflow scheduler (`workflow_scheduler.py`, API at `api/scheduler.py`)
manages scheduled and queued workflows with priority-based execution. It
integrates with the task queue system for deferred execution.

### Priority Levels

```python
from workflow_scheduler import WorkflowPriority

# Available priorities (ascending order)
WorkflowPriority.LOW       # 1
WorkflowPriority.NORMAL    # 2
WorkflowPriority.HIGH      # 3
WorkflowPriority.URGENT    # 4
WorkflowPriority.CRITICAL  # 5
```

### Workflow Statuses

```python
from workflow_scheduler import WorkflowStatus

WorkflowStatus.SCHEDULED   # Waiting for scheduled_time
WorkflowStatus.QUEUED      # In execution queue
WorkflowStatus.RUNNING     # Currently executing
WorkflowStatus.COMPLETED   # Finished successfully
WorkflowStatus.FAILED      # Execution failed
WorkflowStatus.CANCELLED   # Manually cancelled
WorkflowStatus.PAUSED      # Temporarily paused
```

### Scheduler API Endpoints

All endpoints are under `/api/scheduler` and require admin authentication.

| Method   | Path                                 | Description                              |
|----------|--------------------------------------|------------------------------------------|
| `POST`   | `/schedule`                          | Schedule a new workflow                  |
| `GET`    | `/workflows`                         | List workflows with optional filtering   |
| `GET`    | `/workflows/{id}`                    | Get workflow details                     |
| `PUT`    | `/workflows/{id}/reschedule`         | Reschedule an existing workflow          |
| `DELETE` | `/workflows/{id}`                    | Cancel a workflow                        |
| `GET`    | `/status`                            | Get scheduler status                     |
| `GET`    | `/queue`                             | Get queue status and contents            |
| `POST`   | `/queue/control`                     | Pause, resume, or set max concurrent     |
| `POST`   | `/start`                             | Start the scheduler                      |
| `POST`   | `/stop`                              | Stop the scheduler                       |
| `POST`   | `/batch-schedule`                    | Schedule multiple workflows at once      |
| `GET`    | `/stats`                             | Get detailed scheduler statistics        |
| `GET`    | `/templates/schedule/{template_id}`  | Schedule from a template                 |

### Scheduling a Workflow

```bash
curl -sk -X POST https://<backend-ip>:8443/api/scheduler/schedule \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "user_message": "Run vulnerability scan on codebase",
        "scheduled_time": "2026-03-16T02:00:00Z",
        "priority": "high",
        "complexity": "moderate",
        "max_retries": 3,
        "timeout_minutes": 120,
        "tags": ["security", "scheduled"],
        "dependencies": []
    }'
```

### Queue Control

```bash
# Pause the queue
curl -sk -X POST https://<backend-ip>:8443/api/scheduler/queue/control \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"action": "pause"}'

# Resume the queue
curl -sk -X POST https://<backend-ip>:8443/api/scheduler/queue/control \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"action": "resume"}'

# Set maximum concurrent workflows
curl -sk -X POST https://<backend-ip>:8443/api/scheduler/queue/control \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"action": "set_max_concurrent", "value": 5}'
```

### Dependency Chains

Workflows can declare dependencies on other workflow IDs. A dependent
workflow will not execute until all its dependencies have completed:

```python
from workflow_scheduler import (
    WorkflowPriority,
    WorkflowScheduleRequest,
    workflow_scheduler,
)

# Schedule parent workflow
parent_id = workflow_scheduler.schedule_workflow(
    request=WorkflowScheduleRequest(
        user_message="Index codebase",
        scheduled_time="2026-03-16T01:00:00Z",
        priority=WorkflowPriority.HIGH,
        tags=["indexing"],
    )
)

# Schedule dependent workflow
child_id = workflow_scheduler.schedule_workflow(
    request=WorkflowScheduleRequest(
        user_message="Analyze indexed code for vulnerabilities",
        scheduled_time="2026-03-16T02:00:00Z",
        priority=WorkflowPriority.NORMAL,
        dependencies=[parent_id],
        tags=["security", "post-indexing"],
    )
)
```

---

## 8. Long-Running Operations

The long-running operations framework (`api/long_running_operations.py`)
extends the task system with progress tracking, checkpoint/resume, and
WebSocket-based real-time updates.

### API Endpoints

All endpoints are under `/api/operations`.

| Method      | Path                           | Description                              |
|-------------|--------------------------------|------------------------------------------|
| `POST`      | `/codebase/index`              | Start codebase indexing                  |
| `POST`      | `/testing/comprehensive`       | Start comprehensive test suite           |
| `POST`      | `/knowledge-base/populate`     | Start knowledge base population          |
| `POST`      | `/security/scan`               | Start security scan                      |
| `POST`      | `/migrate/existing`            | Migrate legacy timeout-based operation   |
| `GET`       | `/{operation_id}`              | Get operation status                     |
| `GET`       | `/`                            | List operations with filters             |
| `POST`      | `/{operation_id}/cancel`       | Cancel a running operation               |
| `POST`      | `/{operation_id}/resume`       | Resume from latest checkpoint            |
| `WebSocket` | `/{operation_id}/progress`     | Real-time progress stream                |
| `GET`       | `/health`                      | Health check for operations service      |

### Starting a Long-Running Operation

```bash
curl -sk -X POST https://<backend-ip>:8443/api/operations/codebase/index \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "codebase_path": "/opt/autobot",
        "file_patterns": ["*.py", "*.js", "*.vue", "*.ts"],
        "include_tests": true,
        "include_docs": true,
        "max_file_size": 1048576,
        "priority": "normal"
    }'
```

Response:

```json
{
    "operation_id": "op-a1b2c3d4",
    "status": "created"
}
```

### Progress via WebSocket

```javascript
const ws = new WebSocket(
    `wss://<backend-ip>:8443/api/operations/${operationId}/progress`
);

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "current_progress") {
        console.log(`Progress: ${message.data.progress_percent}%`);
    }
};
```

### Checkpoint and Resume

Operations create checkpoints at safe boundaries. If an operation is
interrupted, it can be resumed from the most recent checkpoint:

```bash
# Resume an interrupted operation
curl -sk -X POST \
    https://<backend-ip>:8443/api/operations/${OPERATION_ID}/resume \
    -H "Authorization: Bearer $TOKEN"
```

Response:

```json
{
    "status": "resumed",
    "new_operation_id": "op-new-id",
    "resumed_from": "checkpoint-xyz",
    "original_operation_id": "op-original-id"
}
```

---

## 9. Complete Failover Configuration Example

This section ties together all components into a production-ready
`DistributedTaskManager` class.

```python
#!/usr/bin/env python3
"""
AutoBot Distributed Task Manager with Failover

Complete implementation of the distributed task system that:
- Registers workers across the 6-VM fleet
- Distributes tasks through priority queues
- Monitors worker health via heartbeats
- Automatically migrates tasks from dead workers
- Provides observability through Redis audit logs

Usage:
    manager = DistributedTaskManager()
    await manager.initialize()
    task_id = await manager.submit_task(
        "npu_inference",
        {"model": "yolov8", "image_path": "/data/img.jpg"},
        priority="high",
    )
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class FailoverConfig:
    """Configuration for the failover subsystem.

    Attributes:
        heartbeat_interval: Seconds between worker heartbeats.
        heartbeat_timeout: Seconds before a missing heartbeat
            triggers failover (should be ``heartbeat_interval * 3``).
        max_retries: Maximum times a task can be re-queued after
            worker failure.
        requeue_delay: Seconds to wait before re-queuing (allows
            transient issues to resolve).
        check_interval: Seconds between failover monitor scans.
        priority_queues: Ordered list of priority levels. Tasks on
            higher-priority queues are checked first during
            migration.
    """

    heartbeat_interval: int = 15
    heartbeat_timeout: int = 45
    max_retries: int = 3
    requeue_delay: int = 5
    check_interval: int = 30
    priority_queues: list = field(
        default_factory=lambda: ["critical", "high", "normal", "low"]
    )


class DistributedTaskManager:
    """Manages distributed task execution with automatic failover.

    This class is the top-level coordinator for the distributed
    task system. It combines worker registration, task submission,
    heartbeat monitoring, and failover detection into a single
    cohesive interface.

    All Redis access goes through the canonical
    ``autobot_shared.redis_client.get_redis_client`` function.
    No direct ``redis.Redis()`` instantiation.

    Attributes:
        config: Failover configuration parameters.
        _redis: Async Redis client for DB ``main``.
        _monitor_task: Background asyncio task for failover
            detection.
        _initialized: Whether ``initialize()`` has been called.
    """

    def __init__(
        self, config: FailoverConfig | None = None
    ) -> None:
        """Initialize the task manager.

        Args:
            config: Optional failover configuration. Uses defaults
                if not provided.
        """
        self.config = config or FailoverConfig()
        self._redis = None
        self._monitor_task: asyncio.Task | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Connect to Redis and start the failover monitor.

        Must be called once during application startup before
        submitting tasks or registering workers.

        Raises:
            RuntimeError: If the Redis client is unavailable.

        Example:
            >>> manager = DistributedTaskManager()
            >>> await manager.initialize()
        """
        self._redis = await get_redis_client(
            async_client=True, database="main"
        )
        if self._redis is None:
            raise RuntimeError(
                "Cannot initialize DistributedTaskManager: "
                "Redis client unavailable"
            )
        self._initialized = True
        logger.info("DistributedTaskManager initialized")

    async def register_worker(
        self,
        worker_id: str,
        capabilities: list[str],
        max_concurrent: int = 4,
    ) -> None:
        """Register a worker node with its capabilities.

        Args:
            worker_id: Unique worker identifier.
            capabilities: Task types this worker handles.
            max_concurrent: Maximum simultaneous tasks.

        Raises:
            RuntimeError: If not initialized.

        Example:
            >>> await manager.register_worker(
            ...     "npu-worker-1",
            ...     ["npu_inference", "vision"],
            ...     max_concurrent=4,
            ... )
        """
        self._check_initialized()

        config_data = {
            "id": worker_id,
            "capabilities": json.dumps(capabilities),
            "max_concurrent": str(max_concurrent),
            "registered_at": str(time.time()),
            "status": "active",
        }

        pipe = self._redis.pipeline(transaction=True)
        pipe.hset(f"worker:{worker_id}:config", mapping=config_data)
        pipe.sadd("workers:registered", worker_id)
        await pipe.execute()

        logger.info(
            "Registered worker %s with capabilities %s",
            worker_id,
            capabilities,
        )

    async def submit_task(
        self,
        task_type: str,
        payload: dict,
        priority: str = "normal",
    ) -> str:
        """Submit a task to the distributed queue.

        The task is placed on a priority-qualified queue
        (``queue:{priority}:{task_type}``) and will be picked up
        by the next available worker with matching capabilities.

        Args:
            task_type: Logical task type for worker routing.
            payload: JSON-serializable task data.
            priority: One of ``low``, ``normal``, ``high``,
                ``critical``.

        Returns:
            The generated task ID (UUID).

        Raises:
            RuntimeError: If not initialized.

        Example:
            >>> task_id = await manager.submit_task(
            ...     "npu_inference",
            ...     {"model": "yolov8", "image_path": "/data/img.jpg"},
            ...     priority="high",
            ... )
        """
        self._check_initialized()

        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "type": task_type,
            "payload": json.dumps(payload),
            "status": "queued",
            "priority": priority,
            "created_at": str(time.time()),
            "max_retries": str(self.config.max_retries),
            "retry_count": "0",
            "worker_id": "",
            "previous_worker": "",
            "requeued_at": "",
        }

        pipe = self._redis.pipeline(transaction=True)
        pipe.hset(f"task:{task_id}", mapping=task)
        queue_name = f"queue:{priority}:{task_type}"
        pipe.lpush(queue_name, task_id)
        await pipe.execute()

        logger.info(
            "Submitted task %s to %s", task_id, queue_name
        )
        return task_id

    async def start_failover_monitor(self) -> None:
        """Start the background failover detection loop.

        Launches an asyncio task that periodically scans for dead
        workers and migrates their orphaned tasks. Should be called
        once during application startup.

        Example:
            >>> await manager.start_failover_monitor()
        """
        self._check_initialized()

        if self._monitor_task is not None:
            logger.warning("Failover monitor already running")
            return

        self._monitor_task = asyncio.create_task(
            self._failover_loop()
        )
        logger.info(
            "Failover monitor started (interval=%ds)",
            self.config.check_interval,
        )

    async def stop_failover_monitor(self) -> None:
        """Stop the background failover detection loop.

        Cancels the monitor task gracefully.

        Example:
            >>> await manager.stop_failover_monitor()
        """
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            logger.info("Failover monitor stopped")

    async def get_task_status(self, task_id: str) -> dict | None:
        """Retrieve the current status of a task.

        Args:
            task_id: The task ID to look up.

        Returns:
            Dictionary of task fields, or ``None`` if not found.

        Example:
            >>> status = await manager.get_task_status(task_id)
            >>> print(status["status"])
            'completed'
        """
        self._check_initialized()

        raw = await self._redis.hgetall(f"task:{task_id}")
        if not raw:
            return None
        return {
            k.decode(): v.decode()
            for k, v in raw.items()
        }

    async def get_task_result(self, task_id: str) -> dict | None:
        """Retrieve the result of a completed task.

        Results are stored with a TTL (default 3600 s) and will
        return ``None`` after expiry.

        Args:
            task_id: The task ID whose result to fetch.

        Returns:
            Deserialized result dictionary, or ``None``.

        Example:
            >>> result = await manager.get_task_result(task_id)
        """
        self._check_initialized()

        raw = await self._redis.get(f"task:{task_id}:result")
        if raw is None:
            return None
        return json.loads(raw)

    async def list_registered_workers(self) -> list[str]:
        """List all currently registered worker IDs.

        Returns:
            List of worker ID strings.

        Example:
            >>> workers = await manager.list_registered_workers()
            >>> print(workers)
            ['npu-worker-1', 'ai-stack-worker-1']
        """
        self._check_initialized()

        raw = await self._redis.smembers("workers:registered")
        return [
            w.decode() if isinstance(w, bytes) else w
            for w in raw
        ]

    async def get_failover_log(
        self, count: int = 50
    ) -> list[dict]:
        """Retrieve recent failover events.

        Args:
            count: Maximum number of events to return.

        Returns:
            List of failover event dictionaries, newest first.

        Example:
            >>> events = await manager.get_failover_log(10)
        """
        self._check_initialized()

        raw_events = await self._redis.lrange(
            "failover:log", 0, count - 1
        )
        return [
            json.loads(e.decode() if isinstance(e, bytes) else e)
            for e in raw_events
        ]

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _check_initialized(self) -> None:
        """Raise if initialize() has not been called."""
        if not self._initialized:
            raise RuntimeError(
                "DistributedTaskManager.initialize() must be "
                "called before use"
            )

    async def _failover_loop(self) -> None:
        """Internal loop that scans for dead workers.

        Runs until cancelled. On each iteration, checks all
        registered workers for expired heartbeats and migrates
        orphaned tasks.
        """
        while True:
            try:
                await self._scan_for_dead_workers()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Failover scan error: %s", exc)

            await asyncio.sleep(self.config.check_interval)

    async def _scan_for_dead_workers(self) -> None:
        """Single pass: find dead workers and migrate tasks."""
        registered = await self._redis.smembers(
            "workers:registered"
        )

        for worker_id_bytes in registered:
            worker_id = (
                worker_id_bytes.decode()
                if isinstance(worker_id_bytes, bytes)
                else worker_id_bytes
            )

            heartbeat = await self._redis.get(
                f"worker:{worker_id}:heartbeat"
            )
            if heartbeat is not None:
                continue

            logger.warning(
                "Worker %s heartbeat expired", worker_id
            )

            orphaned_raw = await self._redis.smembers(
                f"worker:{worker_id}:tasks"
            )
            orphaned = [
                t.decode() if isinstance(t, bytes) else t
                for t in orphaned_raw
            ]

            migrated = 0
            for task_id in orphaned:
                if await self._migrate_task(task_id, worker_id):
                    migrated += 1

            # Log event
            event = json.dumps({
                "event": "worker_failover",
                "worker_id": worker_id,
                "orphaned_tasks": len(orphaned),
                "migrated_tasks": migrated,
                "timestamp": time.time(),
            })
            await self._redis.lpush("failover:log", event)
            await self._redis.ltrim("failover:log", 0, 499)

            # Clean up dead worker
            pipe = self._redis.pipeline(transaction=True)
            pipe.delete(f"worker:{worker_id}:tasks")
            pipe.delete(f"worker:{worker_id}:config")
            pipe.srem("workers:registered", worker_id)
            await pipe.execute()

            logger.info(
                "Failover for %s: %d/%d tasks migrated",
                worker_id,
                migrated,
                len(orphaned),
            )

    async def _migrate_task(
        self, task_id: str, dead_worker_id: str
    ) -> bool:
        """Migrate a single task from a dead worker.

        Returns True if re-queued, False if permanently failed.
        """
        task_data = await self._redis.hgetall(f"task:{task_id}")
        if not task_data:
            return False

        retry_count = int(task_data.get(b"retry_count", 0))
        max_retries = int(task_data.get(b"max_retries", 3))
        task_type = task_data.get(b"type", b"default").decode()
        priority = task_data.get(b"priority", b"normal").decode()

        if retry_count < max_retries:
            pipe = self._redis.pipeline(transaction=True)
            pipe.hset(
                f"task:{task_id}",
                mapping={
                    "status": "queued",
                    "retry_count": str(retry_count + 1),
                    "previous_worker": dead_worker_id,
                    "requeued_at": str(time.time()),
                    "worker_id": "",
                },
            )
            queue_name = f"queue:{priority}:{task_type}"
            pipe.lpush(queue_name, task_id)
            await pipe.execute()

            logger.info(
                "Task %s re-queued (retry %d/%d)",
                task_id,
                retry_count + 1,
                max_retries,
            )
            return True
        else:
            await self._redis.hset(
                f"task:{task_id}",
                mapping={
                    "status": "failed_permanent",
                    "failed_at": str(time.time()),
                    "last_error": (
                        f"Worker {dead_worker_id} died; "
                        f"retries exhausted"
                    ),
                },
            )
            logger.error(
                "Task %s permanently failed (%d retries)",
                task_id,
                max_retries,
            )
            return False
```

### Startup Integration

Wire the `DistributedTaskManager` into the FastAPI application lifespan:

```python
import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Import from the module above
# from distributed_task_manager import (
#     DistributedTaskManager,
#     FailoverConfig,
# )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start and stop the task manager."""
    config = FailoverConfig(
        heartbeat_interval=15,
        heartbeat_timeout=45,
        max_retries=3,
        check_interval=30,
    )
    manager = DistributedTaskManager(config=config)
    await manager.initialize()
    await manager.start_failover_monitor()

    # Register fleet workers
    await manager.register_worker(
        "npu-worker-vm22",
        capabilities=["npu_inference", "vision", "openvino"],
        max_concurrent=4,
    )
    await manager.register_worker(
        "aistack-worker-vm24",
        capabilities=["ai_processing", "tts", "embedding"],
        max_concurrent=8,
    )
    await manager.register_worker(
        "main-worker-vm20",
        capabilities=["general", "scheduling", "analysis"],
        max_concurrent=6,
    )

    app.state.task_manager = manager
    logger.info("Distributed task system ready")

    yield

    await manager.stop_failover_monitor()
    logger.info("Distributed task system shut down")


app = FastAPI(lifespan=lifespan)
```

---

## 10. Redis Connection Best Practices

### Always Use the Canonical Client

```python
# CORRECT -- uses connection pooling, circuit breaker, retries
from autobot_shared.redis_client import get_redis_client

redis = get_redis_client(async_client=False, database="main")
```

```python
# WRONG -- bypasses all protections, violates CLAUDE.md Rule 2
import redis
r = redis.Redis(host="<database-ip>", port=6379, db=0)
```

### Use the Correct Database

Match the database name to the data category. Task queues and worker state
belong in `main` (DB 0).

```python
# Task management
redis_tasks = get_redis_client(database="main")

# Knowledge base data
redis_kb = get_redis_client(database="knowledge")

# Codebase analytics
redis_analytics = get_redis_client(database="analytics")
```

### Use Pipelines for Atomic Operations

When multiple Redis commands must execute together, use a pipeline with
`transaction=True`:

```python
pipe = redis.pipeline(transaction=True)
pipe.hset(f"task:{task_id}", "status", "completed")
pipe.srem(f"worker:{worker_id}:tasks", task_id)
pipe.lrem(f"queue:{queue_name}:processing", 1, task_id)
pipe.execute()
```

### Use the Async Context Manager

For short-lived async operations, use the `redis_context` helper:

```python
from autobot_shared.redis_client import redis_context

async with redis_context("main") as redis:
    await redis.set("key", "value")
    result = await redis.get("key")
```

### Use Convenience Functions for Simple Operations

```python
from autobot_shared.redis_client import redis_get, redis_set, redis_delete

# Simple get/set without managing the client
await redis_set("my_key", "my_value", expire=3600, database="main")
value = await redis_get("my_key", database="main")
await redis_delete("my_key", database="main")
```

### Connection Health Checks

```python
from autobot_shared.redis_client import (
    test_redis_connection,
    get_connection_info,
    get_redis_health,
)

# Simple boolean check
if test_redis_connection("main"):
    print("Redis is reachable")

# Detailed connection info
info = get_connection_info("main")
# Returns: {"database": "main", "connected": True, "health": {...}, ...}

# Full health status across all databases
health = get_redis_health()
```

---

## 11. Monitoring and Observability

### Failover Audit Log

Every failover event is recorded in `failover:log` (a Redis LIST, capped
at 500 entries). Query it directly:

```bash
# Last 10 failover events
redis-cli -h <database-ip> -n 0 LRANGE failover:log 0 9
```

Or programmatically:

```python
events = await manager.get_failover_log(count=10)
for event in events:
    logger.info(
        "Failover: worker=%s, migrated=%d/%d tasks at %s",
        event["worker_id"],
        event["migrated_tasks"],
        event["orphaned_tasks"],
        event["timestamp"],
    )
```

### Worker Health Dashboard Queries

```bash
# List all registered workers
redis-cli -h <database-ip> -n 0 SMEMBERS workers:registered

# Check a specific worker's heartbeat
redis-cli -h <database-ip> -n 0 GET worker:npu-worker-1:heartbeat

# Check heartbeat TTL (seconds remaining)
redis-cli -h <database-ip> -n 0 TTL worker:npu-worker-1:heartbeat

# Count tasks assigned to a worker
redis-cli -h <database-ip> -n 0 SCARD worker:npu-worker-1:tasks

# List tasks assigned to a worker
redis-cli -h <database-ip> -n 0 SMEMBERS worker:npu-worker-1:tasks

# Inspect a specific task
redis-cli -h <database-ip> -n 0 HGETALL task:<task-id>
```

### Queue Depth Monitoring

```bash
# Check queue depth
redis-cli -h <database-ip> -n 0 LLEN queue:npu_tasks

# Check processing list depth (tasks being worked on)
redis-cli -h <database-ip> -n 0 LLEN queue:npu_tasks:processing

# Check priority queue depths
for p in critical high normal low; do
    echo "$p: $(redis-cli -h <database-ip> -n 0 LLEN queue:${p}:npu_inference)"
done
```

### Prometheus Metrics

The `RedisConnectionManager` reports circuit breaker events to Prometheus
via the metrics manager. Key metrics:

- `redis_circuit_breaker_events_total{database, event}` -- circuit open/close events
- `redis_circuit_breaker_state{database}` -- current state (open/closed)
- `redis_connection_failures_total{database}` -- connection failure count

---

## 12. Troubleshooting

### Worker Heartbeat Expired but Worker is Running

**Symptom:** Failover monitor migrates tasks from a worker that is
actually alive.

**Possible causes:**
1. Network partition between worker VM and Redis VM (.23).
2. Worker's heartbeat coroutine crashed silently.
3. Redis is overloaded and not processing `SETEX` commands in time.

**Resolution:**
```bash
# Check network connectivity from worker to Redis
ping -c 3 <database-ip>

# Check Redis latency
redis-cli -h <database-ip> --latency

# Check if worker process is running
ssh autobot@<npu-ip> "ps aux | grep npu_worker"
```

### Tasks Stuck in Processing List

**Symptom:** Tasks remain in `queue:{name}:processing` indefinitely.

**Cause:** Worker crashed after `BRPOPLPUSH` but before completing or
failing the task. The failover monitor handles this for registered
workers, but unregistered workers or edge cases can leave orphans.

**Resolution:**
```bash
# List stuck tasks
redis-cli -h <database-ip> -n 0 LRANGE queue:npu_tasks:processing 0 -1

# Manually re-queue a stuck task
redis-cli -h <database-ip> -n 0 LREM queue:npu_tasks:processing 1 "<task_id>"
redis-cli -h <database-ip> -n 0 HSET task:<task_id> status queued worker_id ""
redis-cli -h <database-ip> -n 0 LPUSH queue:npu_tasks "<task_id>"
```

### Circuit Breaker Open

**Symptom:** `get_redis_client()` returns `None` and logs show
"Circuit breaker is open for database 'main'".

**Cause:** Five or more consecutive connection failures to Redis.

**Resolution:**
```bash
# Check Redis is running
ssh autobot@<database-ip> "systemctl status redis-stack-server"

# Check Redis memory usage
redis-cli -h <database-ip> INFO memory | grep used_memory_human

# The circuit breaker auto-resets after 60 seconds of the last failure.
# If Redis is back up, wait 60 seconds and retry.
```

### Task Permanently Failed After Failover

**Symptom:** Task has status `failed_permanent` with error
"Worker X died; retries exhausted".

**Cause:** The task was migrated multiple times (once per worker death)
and exhausted its `max_retries` counter.

**Resolution:** Investigate why multiple workers died during this task.
If the task payload itself is causing crashes, fix the root cause. To
retry a permanently failed task, reset its state manually:

```bash
redis-cli -h <database-ip> -n 0 HSET task:<task_id> status queued
redis-cli -h <database-ip> -n 0 HSET task:<task_id> retry_count 0
redis-cli -h <database-ip> -n 0 HSET task:<task_id> worker_id ""
redis-cli -h <database-ip> -n 0 LPUSH queue:<task_type> "<task_id>"
```

---

## Related Documentation

- [SSOT Configuration](../../autobot_shared/ssot_config.py) -- VM IPs and port configuration
- [Redis Client Module](../../autobot_shared/redis_client.py) -- canonical Redis access
- [NPU Worker API](../../autobot-backend/api/npu_workers.py) -- NPU endpoint reference
- [Scheduler API](../../autobot-backend/api/scheduler.py) -- workflow scheduling
- [Long-Running Operations](../../autobot-backend/api/long_running_operations.py) -- checkpoint/resume
- [Redis Database Types](../../autobot-backend/utils/redis_management/types.py) -- database mapping
- [Hardcoding Prevention Guide](../developer/HARDCODING_PREVENTION.md) -- SSOT config usage
