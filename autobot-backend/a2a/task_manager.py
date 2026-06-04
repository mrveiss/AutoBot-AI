# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Task Manager

Issue #961: In-memory task lifecycle manager for A2A tasks.
Issue #968: Adds TraceContext per task for distributed tracing + audit log.
Issue #4502: Replace in-process dict with Redis-backed storage to fix 404
             flapping across multiple uvicorn workers.
Issue #4554: Sliding TTL on get_task() so active pollers never hit 404;
             publish_event() for SSE streaming via Redis pub/sub.
Manages task state transitions per the A2A spec §4.2.

State machine:
  SUBMITTED → WORKING → COMPLETED
                      → FAILED
  SUBMITTED → CANCELLED
  WORKING   → INPUT_REQUIRED → WORKING
  WORKING   → CANCELLED

Redis key layout:
  a2a:task:{id}    — JSON-serialised Task (TTL: AUTOBOT_A2A_TASK_TTL_SECONDS)
  a2a:audit:{id}   — Redis list of JSON-serialised TraceEvent entries (same TTL)
  a2a:tasks        — Redis set of all known task IDs
  a2a:events:{id}  — Redis pub/sub channel for SSE streaming (Issue #4554)
"""

import json
import uuid
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
from autobot_shared.time_utils import now_utc

from .tracing import TraceContext, TraceEvent, new_trace_id
from .types import A2ATaskStatus, Task, TaskArtifact, TaskState

logger = get_logger(__name__)

# Terminal states — no further transitions allowed
_TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}

_KEY_TASK = "a2a:task:{}"
_KEY_AUDIT = "a2a:audit:{}"
_KEY_TASKS = "a2a:tasks"
_KEY_EVENTS = "a2a:events:{}"  # pub/sub channel for SSE streaming (#4554)


def _utcnow() -> str:
    return now_utc().isoformat()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _task_to_json(task: Task) -> str:
    """Serialise a Task (without trace_context) to JSON."""
    d: Dict[str, Any] = {
        "id": task.id,
        "status": {
            "state": task.status.state.value,
            "message": task.status.message,
            "timestamp": task.status.timestamp,
        },
        "input": task.input,
        "context": task.context,
        "artifacts": [
            {
                "artifact_type": a.artifact_type,
                "content": a.content,
                "created_at": a.created_at,
            }
            for a in task.artifacts
        ],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        # Trace metadata only (full event log lives in a2a:audit:{id})
        "trace_id": task.trace_context.trace_id if task.trace_context else None,
        "caller_id": task.trace_context.caller_id if task.trace_context else None,
    }
    return json.dumps(d)


def _task_from_json(raw: str) -> Task:
    """Deserialise a Task from JSON.  TraceContext events are NOT reloaded here."""
    d = json.loads(raw)
    status = A2ATaskStatus(
        state=TaskState(d["status"]["state"]),
        message=d["status"].get("message"),
        timestamp=d["status"]["timestamp"],
    )
    artifacts = [
        TaskArtifact(
            artifact_type=a["artifact_type"],
            content=a["content"],
            created_at=a["created_at"],
        )
        for a in d.get("artifacts", [])
    ]
    tc: TraceContext | None = None
    if d.get("trace_id"):
        tc = TraceContext(
            trace_id=d["trace_id"],
            caller_id=d.get("caller_id", "anonymous"),
        )
    task = Task(
        id=d["id"],
        status=status,
        input=d["input"],
        context=d.get("context"),
        artifacts=artifacts,
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        trace_context=tc,
    )
    return task


def _audit_entry_to_json(event: TraceEvent) -> str:
    return json.dumps(event.to_dict())


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


class TaskManager:
    """Redis-backed A2A task store — safe across multiple uvicorn workers.

    Issue #4502: Replaces the per-process in-memory dict with Redis so that
    tasks created on worker A are visible to worker B/C.

    Issue #4554: get_task() slides the TTL on every access (active pollers
    never expire); publish_event() pushes SSE payloads via Redis pub/sub.
    """

    def __init__(self) -> None:
        self._redis = get_redis_client(database="main")

    # ------------------------------------------------------------------
    # Internal Redis helpers
    # ------------------------------------------------------------------

    def _ttl(self) -> int:
        return int(config.timeout.a2a_task_ttl)

    def _save(self, task: Task) -> None:
        """Persist task JSON and register its ID in the task-set."""
        ttl = self._ttl()
        key = _KEY_TASK.format(task.id)
        self._redis.set(key, _task_to_json(task), ex=ttl)
        self._redis.sadd(_KEY_TASKS, task.id)
        self._redis.expire(_KEY_TASKS, ttl)

    def _load(self, task_id: str) -> Task | None:
        raw = self._redis.get(_KEY_TASK.format(task_id))
        if raw is None:
            return None
        return _task_from_json(raw if isinstance(raw, str) else raw.decode("utf-8"))

    def _append_audit(self, task_id: str, event: TraceEvent) -> None:
        key = _KEY_AUDIT.format(task_id)
        self._redis.rpush(key, _audit_entry_to_json(event))
        self._redis.expire(key, self._ttl())

    # ------------------------------------------------------------------
    # Public API (same signatures as the old in-memory implementation)
    # ------------------------------------------------------------------

    def create_task(
        self,
        input_text: str,
        context: Dict | None = None,
        caller_id: str = "anonymous",
        trace_id: str | None = None,
    ) -> Task:
        """Create and register a new task in SUBMITTED state."""
        task_id = str(uuid.uuid4())
        tc = TraceContext(
            trace_id=trace_id or new_trace_id(),
            caller_id=caller_id,
        )
        event = TraceEvent(event="task.submitted", data={"task_id": task_id})
        tc.events.append(event)

        task = Task(
            id=task_id,
            status=A2ATaskStatus(state=TaskState.SUBMITTED),
            input=input_text,
            context=context,
            trace_context=tc,
        )
        self._save(task)
        self._append_audit(task_id, event)
        logger.info(
            "A2A task created: %s trace=%s caller=%s",
            task_id,
            tc.trace_id[:8],
            caller_id,
        )
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Retrieve a task by ID, sliding its TTL on each access.

        Issue #4554: Resetting the TTL on every GET means any client that
        is actively polling will never see a 404 — tasks only expire when
        genuinely abandoned (no polls for a full TTL window).
        Issue #8162: Pipeline the three EXPIRE calls into one round-trip.
        """
        key = _KEY_TASK.format(task_id)
        raw = self._redis.get(key)
        if raw is None:
            return None
        # Slide TTL — reset expiry from now so active pollers stay alive.
        # Slide the audit key too so it doesn't expire before the task does.
        ttl = self._ttl()
        with self._redis.pipeline() as pipe:
            pipe.expire(key, ttl)
            pipe.expire(_KEY_AUDIT.format(task_id), ttl)
            pipe.expire(_KEY_TASKS, ttl)
            pipe.execute()
        return _task_from_json(raw if isinstance(raw, str) else raw.decode("utf-8"))

    def list_tasks(self) -> List[Task]:
        """Return all tasks whose keys are still alive in Redis.

        Issue #8162: Use MGET to batch all task fetches into one round-trip
        instead of issuing one GET per task ID (N+1 pattern).
        """
        ids = self._redis.smembers(_KEY_TASKS)
        if not ids:
            return []

        id_strs = [tid if isinstance(tid, str) else tid.decode("utf-8") for tid in ids]
        keys = [_KEY_TASK.format(tid) for tid in id_strs]
        raws = self._redis.mget(keys)

        tasks: List[Task] = []
        expired_ids = []
        for tid, raw in zip(ids, raws):
            if raw is not None:
                tasks.append(_task_from_json(raw if isinstance(raw, str) else raw.decode("utf-8")))
            else:
                # TTL expired — collect for bulk removal from tracking set
                expired_ids.append(tid)

        if expired_ids:
            with self._redis.pipeline() as pipe:
                for expired in expired_ids:
                    pipe.srem(_KEY_TASKS, expired)
                pipe.execute()

        return tasks

    def update_state(
        self,
        task_id: str,
        state: TaskState,
        message: str | None = None,
    ) -> Task | None:
        """Transition a task to a new state.

        Returns the updated task, or None if task not found or already terminal.
        """
        task = self._load(task_id)
        if not task:
            logger.warning("update_state: task %s not found", task_id)
            return None

        if task.status.state in _TERMINAL_STATES:
            logger.warning(
                "update_state: task %s already in terminal state %s",
                task_id,
                task.status.state.value,
            )
            return task

        task.status = A2ATaskStatus(state=state, message=message)
        task.updated_at = _utcnow()
        event = TraceEvent(
            event="task.state_transition",
            data={"state": state.value, "message": message},
        )
        if task.trace_context:
            task.trace_context.events.append(event)
        self._save(task)
        self._append_audit(task_id, event)
        logger.debug("A2A task %s → %s", task_id, state.value)
        return task

    def add_artifact(self, task_id: str, artifact: TaskArtifact) -> bool:
        """Append an artifact to a task. Returns False if task not found."""
        task = self._load(task_id)
        if not task:
            logger.warning("add_artifact: task %s not found", task_id)
            return False
        task.artifacts.append(artifact)
        task.updated_at = _utcnow()
        self._save(task)
        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task if it is not already in a terminal state.

        Returns True on success, False if not found or already terminal.
        """
        task = self._load(task_id)
        if not task:
            return False
        if task.status.state in _TERMINAL_STATES:
            return False
        task.status = A2ATaskStatus(state=TaskState.CANCELLED)
        task.updated_at = _utcnow()
        event = TraceEvent(event="task.cancelled")
        if task.trace_context:
            task.trace_context.events.append(event)
        self._save(task)
        self._append_audit(task_id, event)
        logger.info("A2A task cancelled: %s", task_id)
        return True

    def get_audit_log(self, task_id: str) -> List[Dict[str, Any]] | None:
        """Return the full trace event log for a task, or None if not found."""
        if not self._load(task_id):
            return None
        raw_entries = self._redis.lrange(_KEY_AUDIT.format(task_id), 0, -1)
        result: List[Dict[str, Any]] = []
        for raw in raw_entries:
            entry = raw if isinstance(raw, str) else raw.decode("utf-8")
            result.append(json.loads(entry))
        return result

    def publish_event(self, task_id: str, payload: Dict[str, Any]) -> None:
        """Publish a task event to the Redis pub/sub channel for SSE streaming.

        Issue #4554: task_executor calls this at every state transition and
        artifact addition.  The SSE endpoint subscribes to this channel and
        forwards messages to connected clients in real time.

        Args:
            task_id: Task identifier.
            payload: JSON-serialisable event dict, e.g.
                     {"event": "state_change", "state": "working"}
                     {"event": "artifact_added", "artifact": {...}}
                     {"event": "state_change", "state": "completed", "terminal": True}
        """
        try:
            channel = _KEY_EVENTS.format(task_id)
            self._redis.publish(channel, json.dumps(payload))
        except Exception as exc:
            # Pub/sub is best-effort — never let it break task execution
            logger.warning("publish_event failed for task %s: %s", task_id, exc)

    def stats(self) -> Dict[str, int]:
        """Return task counts per state."""
        counts: Dict[str, int] = {}
        for task in self.list_tasks():
            key = task.status.state.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# Module-level singleton — Redis-backed, safe across all uvicorn workers
_task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """Return the module-level TaskManager singleton."""
    return _task_manager
