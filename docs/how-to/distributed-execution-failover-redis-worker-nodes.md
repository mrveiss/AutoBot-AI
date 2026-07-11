# Configure a distributed execution strategy that handles task failover by migrating pending jobs between Redis-backed worker nodes

AutoBot's task execution system uses Redis sorted sets and per-worker task sets to track every in-flight job.  When a worker's heartbeat expires, the `failover_monitor` automatically re-queues that worker's tasks on the remaining active workers — with retry counting and exponential backoff.

## How it works

```
Workers register with NPUWorkerManager
  │
  ├─ Each worker publishes a heartbeat key:
  │       npu:worker:{worker_id}:status  (TTL = heartbeat_interval × 2)
  │
  ├─ On task pickup:
  │       {queue}:pending  (ZSET) → move task_id to {queue}:running (ZSET)
  │       {queue}:worker:{worker_id}:tasks  (SET) ← record assignment
  │
  └─ failover_monitor() runs every 30 s:
          For each worker with expired heartbeat:
              1. Read {queue}:worker:{worker_id}:tasks (SET)
              2. For each task_id:
                    retry_count < max_retries → re-add to {queue}:pending
                    retry_count ≥ max_retries → move to {queue}:failed
              3. Delete worker records and remove from registry
```

## Redis data structures

| Key | Type | Purpose |
|-----|------|---------|
| `{queue}:pending` | ZSET | Waiting tasks (score = priority) |
| `{queue}:running` | ZSET | Executing tasks (score = start timestamp) |
| `{queue}:scheduled` | ZSET | Tasks waiting for retry backoff (score = retry_at timestamp) |
| `{queue}:completed` | ZSET | Finished tasks |
| `{queue}:failed` | ZSET | Permanently failed tasks |
| `{queue}:tasks` | HASH | Task data keyed by task_id |
| `{queue}:worker:{id}:tasks` | SET | Task IDs currently owned by this worker |
| `npu:worker:{id}:status` | STRING | Heartbeat key (TTL-based liveness) |

## Configure the failover monitor

```python
from services.npu_worker_manager import NPUWorkerManager
from autobot_shared.redis_client import get_redis_client
import asyncio

async def setup_distributed_execution():
    redis = await get_redis_client(async_client=True, database="main")
    manager = NPUWorkerManager(redis_client=redis)

    # Register workers
    await manager.register_worker("worker-gpu-01", capabilities=["gpu", "vision"])
    await manager.register_worker("worker-cpu-01", capabilities=["cpu"])
    await manager.register_worker("worker-cpu-02", capabilities=["cpu"])

    # Start the failover monitor (runs in background)
    asyncio.create_task(
        manager.failover_monitor(
            queue_name="autobot_tasks",
            check_interval=30,   # seconds between scans
            max_retries=3,       # max times a task is re-queued before failing
        )
    )

    return manager
```

## Enqueue tasks with priority

```python
from utils.task_queue import TaskQueue, TaskPriority
import asyncio

async def enqueue_tasks():
    queue = TaskQueue(queue_name="autobot_tasks")
    await queue.start()

    # Enqueue with different priorities
    task_id = await queue.enqueue(
        task_type="run_inference",
        payload={"model": "llama3:8b", "prompt": "Hello"},
        priority=TaskPriority.HIGH,
        max_retries=3,
        retry_delay=5,  # seconds base delay (doubled on each retry)
    )
    print(f"Enqueued task: {task_id}")
    return task_id
```

## Task priority levels

| Priority | Value | Use case |
|----------|-------|----------|
| `LOW` | 1 | Background jobs, analytics |
| `NORMAL` | 2 | Standard tasks (default) |
| `HIGH` | 3 | User-facing interactive requests |
| `CRITICAL` | 4 | System operations, deployments |

## Task lifecycle states

```
PENDING → RUNNING → COMPLETED
                 ↘
                   RETRY (exponential backoff)
                     ↓  (max retries exceeded)
                   FAILED

Worker dies while RUNNING:
  RUNNING → PENDING (retry_count < max_retries)
          → FAILED  (retry_count ≥ max_retries)
```

## Retry with exponential backoff

Failed tasks are automatically rescheduled with exponential backoff:

```
retry_delay = base_retry_delay × 2^retry_count

retry_count=1: delay = 5 × 2¹  = 10s
retry_count=2: delay = 5 × 2²  = 20s
retry_count=3: delay = 5 × 2³  = 40s
```

The scheduler loop moves due-tasks from `{queue}:scheduled` back to `{queue}:pending` every 5 seconds.

## Monitor task status programmatically

```python
async def monitor_task(queue: TaskQueue, task_id: str, poll_interval: float = 1.0):
    """Poll a task until it reaches a terminal state."""
    while True:
        result = await queue.get_task_result(task_id)
        status = result.get("status") if result else "unknown"
        print(f"  Task {task_id}: {status}")

        if status in ("completed", "failed", "cancelled"):
            if status == "failed":
                print(f"  Error: {result.get('error')}")
                print(f"  Retries: {result.get('retry_count', 0)}")
            return result

        await asyncio.sleep(poll_interval)
```

## Verify failover works — test script

```python
import asyncio
from services.npu_worker_manager import NPUWorkerManager
from autobot_shared.redis_client import get_redis_client


async def test_failover():
    redis = await get_redis_client(async_client=True, database="main")
    manager = NPUWorkerManager(redis_client=redis)
    queue_name = "autobot_tasks"

    # Simulate a worker dying: expire its heartbeat immediately
    worker_id = "worker-cpu-01"
    await redis.delete(f"npu:worker:{worker_id}:status")

    # Trigger failover check manually
    if await manager._is_worker_heartbeat_expired(worker_id):
        print(f"Worker {worker_id} heartbeat expired — triggering failover...")
        await manager._failover_dead_worker(worker_id, queue_name, max_retries=3)

    # Confirm tasks moved back to pending
    pending_count = await redis.zcard(f"{queue_name}:pending")
    print(f"Tasks in pending queue after failover: {pending_count}")


asyncio.run(test_failover())
```

## Celery task routing (alternative execution strategy)

For Celery-based distributed execution, tasks are routed by type:

```python
# autobot-backend/celery_app.py
task_routes = {
    "tasks.initialize_rbac":         {"queue": "deployments"},
    "tasks.run_system_update":       {"queue": "deployments"},
    "tasks.check_available_updates": {"queue": "deployments"},
}

# Celery uses Redis as both broker and result backend:
# broker:  redis://host:port/db_celery
# backend: redis://host:port/db_results
```

Start workers per queue:

```bash
celery -A celery_app worker -Q deployments -c 2 --loglevel=info
celery -A celery_app worker -Q memory      -c 4 --loglevel=info
```

## Architecture reference

- **Task queue + retry scheduling** — `autobot-backend/utils/task_queue.py`
- **Failover monitor + migration** — `autobot-backend/services/npu_worker_manager.py` (`failover_monitor`, `_failover_dead_worker`, `_migrate_running_task`)
- **Per-worker task tracking** — `autobot-backend/services/npu_worker_manager.py` (`assign_task_to_worker`, `release_worker_task`)
- **Celery configuration** — `autobot-backend/celery_app.py`
- **Worker node** — `autobot-backend/worker_node.py`
