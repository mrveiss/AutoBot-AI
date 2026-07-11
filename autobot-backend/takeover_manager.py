# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Human-in-the-Loop Takeover Manager for AutoBot Phase 8
Provides interrupt/takeover capabilities for autonomous operations

Issue #11639: State moved to Redis so all uvicorn workers share visibility.
Fallback to in-process dicts when Redis is unavailable (single-worker dev mode).
"""

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from memory import MemoryManager, TaskPriority

logger = get_logger(__name__)

# Performance optimization: O(1) lookup for datetime field keys (Issue #326)
DATETIME_FIELD_KEYS = {"started_at", "ended_at"}

# ---------------------------------------------------------------------------
# TTL constants — env-var-backed, never hard-coded (#11639)
# ---------------------------------------------------------------------------
_DEFAULT_PENDING_TTL_SECONDS = 1800  # 30 min matches default_timeout


def _resolve_pending_ttl() -> int:
    """Return TTL seconds for autobot:takeover:pending:* Redis keys."""
    raw = os.environ.get("AUTOBOT_TAKEOVER_PENDING_TTL_SECONDS")
    if raw is None:
        return _DEFAULT_PENDING_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_TAKEOVER_PENDING_TTL_SECONDS=%r is not an integer; " "falling back to %ds",
            raw,
            _DEFAULT_PENDING_TTL_SECONDS,
        )
        return _DEFAULT_PENDING_TTL_SECONDS
    if value <= 0:
        logger.warning(
            "AUTOBOT_TAKEOVER_PENDING_TTL_SECONDS=%d must be positive; " "falling back to %ds",
            value,
            _DEFAULT_PENDING_TTL_SECONDS,
        )
        return _DEFAULT_PENDING_TTL_SECONDS
    return value


_PENDING_TTL_SECONDS: int = _resolve_pending_ttl()

# Redis key namespace
_NS = "autobot:takeover"
_KEY_PENDING = f"{_NS}:pending"  # STRING prefix; full key = {_KEY_PENDING}:<id>
_KEY_PENDING_INDEX = f"{_NS}:pending_index"  # SET of active request IDs
# M4: sessions stored as individual STRING keys (WATCHable) rather than one HASH.
_KEY_SESSION = f"{_NS}:session"  # STRING prefix; full key = {_KEY_SESSION}:<id>
_KEY_SESSION_INDEX = f"{_NS}:session_index"  # SET of live session IDs
_KEY_PAUSED = f"{_NS}:paused_tasks"  # SET of paused task IDs
_KEY_REQ_TASK = f"{_NS}:request_task"  # HASH: request_id -> memory task_id
# Completed-session history: capped list of compact JSON records (ring buffer).
_KEY_SESSION_HISTORY = f"{_NS}:session_history"
_SESSION_HISTORY_MAX = 200  # keep last 200 completed/cancelled records


class TakeoverTrigger(Enum):
    """Types of takeover triggers"""

    MANUAL_REQUEST = "manual_request"
    CRITICAL_ERROR = "critical_error"
    SECURITY_CONCERN = "security_concern"
    USER_INTERVENTION_REQUIRED = "user_intervention_required"
    SYSTEM_OVERLOAD = "system_overload"
    APPROVAL_REQUIRED = "approval_required"
    TIMEOUT_EXCEEDED = "timeout_exceeded"


class TakeoverState(Enum):
    """Takeover session states"""

    REQUESTED = "requested"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TakeoverRequest:
    """Takeover request data structure"""

    request_id: str
    trigger: TakeoverTrigger
    priority: TaskPriority
    requesting_agent: str | None
    affected_tasks: List[str]
    reason: str
    context_data: Dict[str, Any]
    requested_at: datetime
    expires_at: datetime | None
    auto_approve: bool = False

    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage.

        context_data is arbitrary user-supplied data; use default=str so that
        datetimes/enums/etc. serialize safely instead of blowing up.
        """
        d = asdict(self)
        d["trigger"] = self.trigger.value
        d["priority"] = self.priority.value
        d["requested_at"] = self.requested_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        return json.dumps(d, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "TakeoverRequest":
        """Deserialize from JSON string retrieved from Redis."""
        d = json.loads(raw)
        d["trigger"] = TakeoverTrigger(d["trigger"])
        d["priority"] = TaskPriority(d["priority"])
        d["requested_at"] = datetime.fromisoformat(d["requested_at"])
        if d["expires_at"]:
            d["expires_at"] = datetime.fromisoformat(d["expires_at"])
        return cls(**d)


@dataclass
class TakeoverSession:
    """Active takeover session"""

    session_id: str
    request: TakeoverRequest
    state: TakeoverState
    human_operator: str | None
    started_at: datetime | None
    ended_at: datetime | None
    actions_taken: List[Dict[str, Any]]
    system_snapshot: Dict[str, Any]
    resolution: str | None = None

    def to_json(self) -> str:
        """Serialize to JSON string for Redis storage."""
        d = asdict(self)
        d["state"] = self.state.value
        d["request"]["trigger"] = self.request.trigger.value
        d["request"]["priority"] = self.request.priority.value
        d["request"]["requested_at"] = self.request.requested_at.isoformat()
        if self.request.expires_at:
            d["request"]["expires_at"] = self.request.expires_at.isoformat()
        d["started_at"] = self.started_at.isoformat() if self.started_at else None
        d["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return json.dumps(d, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "TakeoverSession":
        """Deserialize from JSON string retrieved from Redis."""
        d = json.loads(raw)
        d["state"] = TakeoverState(d["state"])
        req = d["request"]
        req["trigger"] = TakeoverTrigger(req["trigger"])
        req["priority"] = TaskPriority(req["priority"])
        req["requested_at"] = datetime.fromisoformat(req["requested_at"])
        if req["expires_at"]:
            req["expires_at"] = datetime.fromisoformat(req["expires_at"])
        d["request"] = TakeoverRequest(**req)
        if d["started_at"]:
            d["started_at"] = datetime.fromisoformat(d["started_at"])
        if d["ended_at"]:
            d["ended_at"] = datetime.fromisoformat(d["ended_at"])
        return cls(**d)


class TakeoverManager:
    """
    Manages human-in-the-loop takeover capabilities for autonomous operations.

    State is stored in Redis (Issue #11639) so all uvicorn workers share
    visibility. Falls back to in-process dicts when Redis is unavailable.

    M4: Each session lives in its own STRING key (autobot:takeover:session:<id>)
    so it can be WATCHed for optimistic concurrency control.
    """

    def __init__(self, memory_manager: MemoryManager | None = None, _redis=None):
        """Initialize takeover manager with memory and session tracking.

        Args:
            memory_manager: Optional MemoryManager override.
            _redis: Optional Redis client override (for tests / fallback mode).
        """
        self.memory_manager = memory_manager or MemoryManager()
        self._redis = _redis  # None = use get_async_redis_client(); set in tests
        # H1: per-process latch — once any Redis op fails, stay in fallback mode.
        # None = not yet probed; True = Redis working; False = latched to fallback.
        self._redis_available: bool | None = None
        self._redis_warning_logged = False

        # In-process fallback state (used when Redis unavailable)
        self._fb_pending: Dict[str, TakeoverRequest] = {}
        self._fb_sessions: Dict[str, TakeoverSession] = {}
        self._fb_paused: Set[str] = set()
        self._fb_req_task: Dict[str, str] = {}

        # Callbacks and handlers (always per-process)
        self.trigger_handlers: Dict[TakeoverTrigger, List[Callable]] = {}
        self.state_change_callbacks: List[Callable] = []

        # Configuration
        self.max_concurrent_sessions = 5
        self.default_timeout = timedelta(minutes=30)
        self.auto_approve_triggers = {TakeoverTrigger.SYSTEM_OVERLOAD}

        logger.info("Takeover Manager initialized")

    # ------------------------------------------------------------------
    # Redis plumbing — H1: latch pattern
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Return a Redis client, or None if unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            from autobot_shared.redis_client import get_async_redis_client

            return await get_async_redis_client()
        except Exception:
            return None

    async def _redis_client(self):
        """Return a usable Redis client, or None when latched to fallback.

        H1: Once any Redis op raises, _redis_available is set False and we
        stay in-process for the lifetime of this worker process.  A single
        warning is logged on the first miss.
        """
        if self._redis_available is False:
            return None
        r = await self._get_redis()
        if r is None:
            if not self._redis_warning_logged:
                logger.warning(
                    "TakeoverManager: Redis unavailable — degrading to in-process state "
                    "(cross-worker visibility disabled; single-worker mode only)"
                )
                self._redis_warning_logged = True
            self._redis_available = False
            return None
        if self._redis_available is None:
            self._redis_available = True
        return r

    def _latch_redis_fallback(self, exc: Exception) -> None:
        """H1: Log once and latch this process to the in-process fallback."""
        if self._redis_available is not False:
            logger.warning(
                "TakeoverManager: Redis op failed (%s) — latching to in-process fallback "
                "for the lifetime of this worker",
                exc,
            )
            self._redis_available = False

    # ------------------------------------------------------------------
    # pending_requests helpers
    # ------------------------------------------------------------------

    async def _pending_set(self, request_id: str, request: TakeoverRequest, timeout_seconds: int | None = None) -> None:
        """Store a pending request in Redis with TTL.

        M3: Single atomic SET with ex= so TTL is set atomically; honours the
        per-request timeout when provided.
        """
        r = await self._redis_client()
        if r is None:
            self._fb_pending[request_id] = request
            return
        ttl = max(_PENDING_TTL_SECONDS, timeout_seconds or 0)
        key = f"{_KEY_PENDING}:{request_id}"
        try:
            # M3: atomic set+expire via ex= parameter
            await r.set(key, request.to_json(), ex=ttl)
            await r.sadd(_KEY_PENDING_INDEX, request_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_pending[request_id] = request

    async def _pending_getdel(self, request_id: str) -> TakeoverRequest | None:
        """Atomically retrieve-and-delete a pending request (prevents double-approve)."""
        r = await self._redis_client()
        if r is None:
            req = self._fb_pending.pop(request_id, None)
            return req
        key = f"{_KEY_PENDING}:{request_id}"
        try:
            raw = await r.getdel(key)
            if raw is None:
                return None
            await r.srem(_KEY_PENDING_INDEX, request_id)
            return TakeoverRequest.from_json(raw)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return self._fb_pending.pop(request_id, None)

    async def _pending_get(self, request_id: str) -> TakeoverRequest | None:
        """Read a pending request without deleting it."""
        r = await self._redis_client()
        if r is None:
            return self._fb_pending.get(request_id)
        key = f"{_KEY_PENDING}:{request_id}"
        try:
            raw = await r.get(key)
            return TakeoverRequest.from_json(raw) if raw else None
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return self._fb_pending.get(request_id)

    async def _pending_delete(self, request_id: str) -> bool:
        """Delete a pending request; return True if it existed."""
        r = await self._redis_client()
        if r is None:
            existed = request_id in self._fb_pending
            self._fb_pending.pop(request_id, None)
            return existed
        key = f"{_KEY_PENDING}:{request_id}"
        try:
            deleted = await r.delete(key)
            await r.srem(_KEY_PENDING_INDEX, request_id)
            return bool(deleted)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            existed = request_id in self._fb_pending
            self._fb_pending.pop(request_id, None)
            return existed

    async def _pending_ids(self) -> Set[str]:
        """Return all current pending request IDs.

        M2: Prune index SET members whose STRING key no longer exists (TTL
        expired without cleanup), removing stale entries and the dangling
        HASH entry from _KEY_REQ_TASK.
        """
        r = await self._redis_client()
        if r is None:
            return set(self._fb_pending.keys())
        try:
            members = await r.smembers(_KEY_PENDING_INDEX)
            ids = {m.decode() if isinstance(m, bytes) else m for m in members}
            if not ids:
                return ids
            # M2: prune stale index entries (STRING expired but SET not cleaned up)
            keys = [f"{_KEY_PENDING}:{rid}" for rid in ids]
            values = await r.mget(*keys)
            live_ids: Set[str] = set()
            stale_ids: list[str] = []
            for rid, val in zip(ids, values):
                if val is None:
                    stale_ids.append(rid)
                else:
                    live_ids.add(rid)
            for rid in stale_ids:
                await r.srem(_KEY_PENDING_INDEX, rid)
                await r.hdel(_KEY_REQ_TASK, rid)
            return live_ids
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return set(self._fb_pending.keys())

    async def _pending_count(self) -> int:
        """Return count of pending requests.

        L4: SCARD after pruning (cheap once index is clean).
        """
        r = await self._redis_client()
        if r is None:
            return len(self._fb_pending)
        # Use _pending_ids which prunes stale entries; SCARD alone could overcount.
        live = await self._pending_ids()
        return len(live)

    # ------------------------------------------------------------------
    # active_sessions helpers (M4: individual STRING keys, WATCHable)
    # ------------------------------------------------------------------

    def _session_key(self, session_id: str) -> str:
        """Return the per-session STRING key."""
        return f"{_KEY_SESSION}:{session_id}"

    async def _sessions_set(self, session_id: str, session: TakeoverSession) -> None:
        """Store a session in Redis (individual STRING key)."""
        r = await self._redis_client()
        if r is None:
            self._fb_sessions[session_id] = session
            return
        try:
            await r.set(self._session_key(session_id), session.to_json())
            await r.sadd(_KEY_SESSION_INDEX, session_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_sessions[session_id] = session

    async def _sessions_get(self, session_id: str) -> TakeoverSession | None:
        """Retrieve a session from Redis."""
        r = await self._redis_client()
        if r is None:
            return self._fb_sessions.get(session_id)
        try:
            raw = await r.get(self._session_key(session_id))
            return TakeoverSession.from_json(raw) if raw else None
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return self._fb_sessions.get(session_id)

    async def _sessions_delete(self, session_id: str) -> None:
        """Remove a live session from Redis (delete STRING key + index entry)."""
        r = await self._redis_client()
        if r is None:
            self._fb_sessions.pop(session_id, None)
            return
        try:
            await r.delete(self._session_key(session_id))
            await r.srem(_KEY_SESSION_INDEX, session_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_sessions.pop(session_id, None)

    async def _sessions_all(self) -> Dict[str, TakeoverSession]:
        """Return all active sessions."""
        r = await self._redis_client()
        if r is None:
            return dict(self._fb_sessions)
        try:
            members = await r.smembers(_KEY_SESSION_INDEX)
            ids = [m.decode() if isinstance(m, bytes) else m for m in members]
            if not ids:
                return {}
            keys = [self._session_key(sid) for sid in ids]
            values = await r.mget(*keys)
            result = {}
            for sid, raw in zip(ids, values):
                if raw is not None:
                    result[sid] = TakeoverSession.from_json(raw)
            return result
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return dict(self._fb_sessions)

    async def _sessions_count(self) -> int:
        """Return number of live sessions.

        L4: Use SCARD of the index (fast), then validate any gaps only when
        needed.  For the liveness guarantee we use _sessions_all which prunes
        implicitly via mget.
        """
        r = await self._redis_client()
        if r is None:
            return len(self._fb_sessions)
        try:
            members = await r.smembers(_KEY_SESSION_INDEX)
            return len(members)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return len(self._fb_sessions)

    async def _sessions_contains(self, session_id: str) -> bool:
        """Check whether a session exists."""
        r = await self._redis_client()
        if r is None:
            return session_id in self._fb_sessions
        try:
            raw = await r.get(self._session_key(session_id))
            return raw is not None
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return session_id in self._fb_sessions

    async def _session_mutate(self, session_id: str, mutate_fn: Callable, attempts: int = 3) -> TakeoverSession | None:
        """Optimistic read-modify-write on a session STRING key.

        M4: WATCH the session key; if another writer commits between our GET
        and EXEC, the pipeline aborts and we retry.  Falls back to a simple
        dict mutation when Redis is unavailable (single-threaded event loop =
        no concurrent mutation in fallback mode).

        Args:
            session_id: Target session.
            mutate_fn: Callable(TakeoverSession) -> TakeoverSession | None.
                       Return None to abort without writing.
            attempts: Maximum CAS retry count.

        Returns:
            The mutated session, or None if not found / mutation aborted.
        """
        r = await self._redis_client()
        if r is None:
            session = self._fb_sessions.get(session_id)
            if session is None:
                return None
            updated = mutate_fn(session)
            if updated is None:
                return None
            self._fb_sessions[session_id] = updated
            return updated

        key = self._session_key(session_id)
        for _ in range(attempts):
            try:
                async with r.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        await pipe.reset()
                        return None
                    session = TakeoverSession.from_json(raw)
                    updated = mutate_fn(session)
                    if updated is None:
                        await pipe.reset()
                        return None
                    pipe.multi()
                    pipe.set(key, updated.to_json())
                    await pipe.execute()
                    return updated
            except Exception as exc:
                # WatchError is a subclass of Exception in redis-py; retry.
                # Re-raise on hard connection errors after latching.
                exc_name = type(exc).__name__
                if exc_name == "WatchError":
                    continue
                if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                    self._latch_redis_fallback(exc)
                    # Fallback: plain dict mutation
                    session = self._fb_sessions.get(session_id)
                    if session is None:
                        return None
                    updated = mutate_fn(session)
                    if updated is None:
                        return None
                    self._fb_sessions[session_id] = updated
                    return updated
                raise
        # All attempts exhausted (concurrent writers kept interfering); give up.
        logger.warning("_session_mutate: %d CAS attempts exhausted for %s", attempts, session_id)
        return None

    # ------------------------------------------------------------------
    # paused_tasks helpers
    # ------------------------------------------------------------------

    async def _paused_add(self, task_id: str) -> None:
        r = await self._redis_client()
        if r is None:
            self._fb_paused.add(task_id)
            return
        try:
            await r.sadd(_KEY_PAUSED, task_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_paused.add(task_id)

    async def _paused_remove(self, task_id: str) -> None:
        r = await self._redis_client()
        if r is None:
            self._fb_paused.discard(task_id)
            return
        try:
            await r.srem(_KEY_PAUSED, task_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_paused.discard(task_id)

    async def _paused_contains(self, task_id: str) -> bool:
        r = await self._redis_client()
        if r is None:
            return task_id in self._fb_paused
        try:
            return bool(await r.sismember(_KEY_PAUSED, task_id))
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return task_id in self._fb_paused

    async def _paused_count(self) -> int:
        r = await self._redis_client()
        if r is None:
            return len(self._fb_paused)
        try:
            members = await r.smembers(_KEY_PAUSED)
            return len(members)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return len(self._fb_paused)

    # ------------------------------------------------------------------
    # _request_task_ids helpers
    # ------------------------------------------------------------------

    async def _req_task_set(self, request_id: str, task_id: str) -> None:
        r = await self._redis_client()
        if r is None:
            self._fb_req_task[request_id] = task_id
            return
        try:
            await r.hset(_KEY_REQ_TASK, request_id, task_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_req_task[request_id] = task_id

    async def _req_task_get(self, request_id: str) -> str | None:
        r = await self._redis_client()
        if r is None:
            return self._fb_req_task.get(request_id)
        try:
            raw = await r.hget(_KEY_REQ_TASK, request_id)
            if raw is None:
                return None
            return raw.decode() if isinstance(raw, bytes) else raw
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return self._fb_req_task.get(request_id)

    async def _req_task_delete(self, request_id: str) -> None:
        r = await self._redis_client()
        if r is None:
            self._fb_req_task.pop(request_id, None)
            return
        try:
            await r.hdel(_KEY_REQ_TASK, request_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            self._fb_req_task.pop(request_id, None)

    # ------------------------------------------------------------------
    # Business logic (unchanged public API)
    # ------------------------------------------------------------------

    def _create_takeover_request(
        self,
        request_id: str,
        trigger: TakeoverTrigger,
        reason: str,
        requesting_agent: str | None,
        affected_tasks: List[str] | None,
        priority: TaskPriority,
        context_data: Dict[str, Any] | None,
        timeout_minutes: int | None,
        auto_approve: bool,
    ) -> TakeoverRequest:
        """
        Create a TakeoverRequest object with computed fields.

        Issue #665: Extracted from request_takeover to reduce function length.
        """
        timeout = timedelta(minutes=timeout_minutes) if timeout_minutes else self.default_timeout
        expires_at = datetime.now(tz=timezone.utc) + timeout

        return TakeoverRequest(
            request_id=request_id,
            trigger=trigger,
            priority=priority,
            requesting_agent=requesting_agent,
            affected_tasks=affected_tasks or [],
            reason=reason,
            context_data=context_data or {},
            requested_at=datetime.now(tz=timezone.utc),
            expires_at=expires_at,
            auto_approve=auto_approve or trigger in self.auto_approve_triggers,
        )

    def _record_takeover_in_memory(
        self,
        trigger: TakeoverTrigger,
        reason: str,
        priority: TaskPriority,
        requesting_agent: str | None,
        affected_tasks: List[str] | None,
    ) -> str:
        """
        Record takeover request in memory system.

        Issue #665: Extracted from request_takeover to reduce function length.
        """
        task_id = self.memory_manager.create_task_record(
            task_name="Takeover Request",
            description=f"Human takeover requested: {reason}",
            priority=priority,
            agent_type="takeover_manager",
            inputs={
                "trigger": trigger.value,
                "reason": reason,
                "affected_tasks": affected_tasks,
                "requesting_agent": requesting_agent,
            },
        )
        self.memory_manager.start_task(task_id)
        return task_id

    def _is_critical_trigger(self, trigger: TakeoverTrigger) -> bool:
        """Check if trigger requires immediate task pause. Issue #620."""
        return trigger in {
            TakeoverTrigger.CRITICAL_ERROR,
            TakeoverTrigger.SECURITY_CONCERN,
        }

    async def _handle_post_request_actions(self, request: TakeoverRequest, request_id: str) -> None:
        """Handle actions after takeover request is created. Issue #620."""
        await self._execute_trigger_handlers(request)

        if self._is_critical_trigger(request.trigger):
            await self._pause_affected_tasks(request.affected_tasks)

        if request.auto_approve:
            await self._auto_approve_request(request_id)

        logger.info(
            "Takeover requested: %s - %s - %s",
            request_id,
            request.trigger.value,
            request.reason,
        )
        await self._notify_state_change("request_created", request_id)

    async def request_takeover(
        self,
        trigger: TakeoverTrigger,
        reason: str,
        requesting_agent: str | None = None,
        affected_tasks: List[str] | None = None,
        priority: TaskPriority = TaskPriority.HIGH,
        context_data: Dict[str, Any] | None = None,
        timeout_minutes: int | None = None,
        auto_approve: bool = False,
    ) -> str:
        """Request human takeover of autonomous operations. Issue #665, #620, #11639."""
        request_id = f"takeover_{int(time.time() * 1000)}"

        request = self._create_takeover_request(
            request_id,
            trigger,
            reason,
            requesting_agent,
            affected_tasks,
            priority,
            context_data,
            timeout_minutes,
            auto_approve,
        )

        memory_task_id = self._record_takeover_in_memory(trigger, reason, priority, requesting_agent, affected_tasks)
        await self._req_task_set(request_id, memory_task_id)
        # M3: pass per-request timeout so TTL matches the request's own expiry.
        timeout_secs = int(timeout_minutes * 60) if timeout_minutes else None
        await self._pending_set(request_id, request, timeout_seconds=timeout_secs)
        await self._handle_post_request_actions(request, request_id)

        return request_id

    async def _validate_takeover_request(self, request_id: str) -> TakeoverRequest:
        """Validate takeover request exists, not expired, and capacity available. Issue #620."""
        request = await self._pending_get(request_id)
        if request is None:
            raise ValueError(f"Takeover request not found: {request_id}")

        if request.expires_at and datetime.now(tz=timezone.utc) > request.expires_at:
            await self._expire_request(request_id)
            raise ValueError(f"Takeover request has expired: {request_id}")

        session_count = await self._sessions_count()
        if session_count >= self.max_concurrent_sessions:
            raise RuntimeError("Maximum concurrent takeover sessions reached")

        return request

    async def _create_takeover_session(
        self, request_id: str, request: TakeoverRequest, human_operator: str
    ) -> TakeoverSession:
        """Create and register a new takeover session. Issue #620, #11639."""
        session_id = f"session_{request_id}_{int(time.time())}"
        system_snapshot = await self._capture_system_snapshot()

        session = TakeoverSession(
            session_id=session_id,
            request=request,
            state=TakeoverState.ACTIVE,
            human_operator=human_operator,
            started_at=datetime.now(tz=timezone.utc),
            ended_at=None,
            actions_taken=[],
            system_snapshot=system_snapshot,
        )

        # Atomic GETDEL: only the first worker to call this succeeds (#11639)
        deleted = await self._pending_getdel(request_id)
        if deleted is None:
            raise ValueError(f"Takeover request already approved or expired: {request_id}")

        await self._sessions_set(session_id, session)
        return session

    async def approve_takeover(
        self,
        request_id: str,
        human_operator: str,
        takeover_scope: Dict[str, Any] | None = None,
    ) -> str:
        """Approve a takeover request and start session"""
        request = await self._validate_takeover_request(request_id)
        session = await self._create_takeover_session(request_id, request, human_operator)

        await self._pause_affected_tasks(request.affected_tasks)

        task_id = await self._req_task_get(request_id)
        if task_id:
            self.memory_manager.complete_task(
                task_id,
                outputs={
                    "session_id": session.session_id,
                    "human_operator": human_operator,
                    "status": "approved_and_active",
                },
            )
        await self._req_task_delete(request_id)

        logger.info("Takeover approved and session started: %s by %s", session.session_id, human_operator)
        await self._notify_state_change("session_started", session.session_id)

        return session.session_id

    async def execute_takeover_action(
        self, session_id: str, action_type: str, action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an action during takeover session.

        M1: pause_task/resume_task have async side-effects applied before the
        CAS write so the result reflects the actual Redis state.
        M4: Uses _session_mutate for read-modify-write safety on the session record.
        """
        session = await self._sessions_get(session_id)
        if session is None:
            raise ValueError(f"Active takeover session not found: {session_id}")
        if session.state != TakeoverState.ACTIVE:
            raise ValueError(f"Session is not active: {session.state.value}")

        # M1: run async side-effects first so result is accurate before persisting
        action_result = await self._execute_action(action_type, action_data, session)

        def _mutate(sess: TakeoverSession) -> TakeoverSession | None:
            if sess.state != TakeoverState.ACTIVE:
                return None
            action_record = {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "action_type": action_type,
                "action_data": action_data,
                "operator": sess.human_operator,
                "result": action_result,
            }
            sess.actions_taken.append(action_record)
            return sess

        await self._session_mutate(session_id, _mutate)

        logger.info("Takeover action executed: %s in session %s", action_type, session_id)
        return action_result

    async def _action_pause_task(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pause_task action (Issue #315).

        M1: Async; adds to paused set and returns status.
        """
        task_id = action_data.get("task_id")
        if task_id:
            await self._paused_add(task_id)
            return {"status": "task_paused", "task_id": task_id}
        return {"status": "error", "reason": "No task_id provided"}

    async def _action_resume_task(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resume_task action (Issue #315).

        M1: Async; validates task is paused before removing, returns error if not.
        """
        task_id = action_data.get("task_id")
        if not task_id:
            return {"status": "error", "reason": "No task_id provided"}
        if not await self._paused_contains(task_id):
            return {"status": "error", "reason": "Task not found or not paused"}
        await self._paused_remove(task_id)
        return {"status": "task_resumed", "task_id": task_id}

    def _action_modify_parameters(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle modify_parameters action (Issue #315)."""
        parameter_changes = action_data.get("changes", {})
        return {"status": "parameters_modified", "changes": parameter_changes}

    def _action_approve_operation(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle approve_operation action (Issue #315)."""
        operation_id = action_data.get("operation_id")
        return {"status": "operation_approved", "operation_id": operation_id}

    def _action_reject_operation(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle reject_operation action (Issue #315)."""
        operation_id = action_data.get("operation_id")
        reason = action_data.get("reason", "Rejected by human operator")
        return {
            "status": "operation_rejected",
            "operation_id": operation_id,
            "reason": reason,
        }

    def _action_system_command(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle system_command action (Issue #315)."""
        command = action_data.get("command")
        if self._is_safe_command(command):
            return {"status": "command_executed", "command": command}
        return {"status": "command_rejected", "reason": "Command not in safe list"}

    def _action_custom_script(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle custom_script action (Issue #315)."""
        script_name = action_data.get("script_name")
        script_params = action_data.get("parameters", {})
        return {
            "status": "script_executed",
            "script": script_name,
            "parameters": script_params,
        }

    async def _execute_action(
        self, action_type: str, action_data: Dict[str, Any], session: TakeoverSession
    ) -> Dict[str, Any]:
        """Execute specific takeover actions (Issue #315 - dispatch table).

        M1: Async handlers for pause_task/resume_task apply their side-effects.
        """
        if action_type == "pause_task":
            return await self._action_pause_task(action_data)
        if action_type == "resume_task":
            return await self._action_resume_task(action_data)
        return _execute_action_sync(action_type, action_data)

    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe for execution during takeover"""
        safe_commands = {
            "ps",
            "top",
            "htop",
            "d",
            "free",
            "uptime",
            "whoami",
            "pwd",
            "ls",
            "cat",
            "less",
            "head",
            "tail",
            "grep",
            "systemctl status",
            "docker ps",
            "docker logs",
        }
        return any(command.startswith(safe_cmd) for safe_cmd in safe_commands)

    async def pause_takeover_session(self, session_id: str) -> bool:
        """Pause an active takeover session.

        M4: Uses _session_mutate for read-modify-write safety.
        """

        def _mutate(session: TakeoverSession) -> TakeoverSession | None:
            if session.state != TakeoverState.ACTIVE:
                return None
            session.state = TakeoverState.PAUSED
            return session

        updated = await self._session_mutate(session_id, _mutate)
        if updated is None:
            return False

        await self._resume_affected_tasks(updated.request.affected_tasks)
        logger.info("Takeover session paused: %s", session_id)
        await self._notify_state_change("session_paused", session_id)
        return True

    async def resume_takeover_session(self, session_id: str) -> bool:
        """Resume a paused takeover session.

        M4: Uses _session_mutate for read-modify-write safety.
        """

        def _mutate(session: TakeoverSession) -> TakeoverSession | None:
            if session.state != TakeoverState.PAUSED:
                return None
            session.state = TakeoverState.ACTIVE
            return session

        updated = await self._session_mutate(session_id, _mutate)
        if updated is None:
            return False

        await self._pause_affected_tasks(updated.request.affected_tasks)
        logger.info("Takeover session resumed: %s", session_id)
        await self._notify_state_change("session_resumed", session_id)
        return True

    async def complete_takeover_session(
        self, session_id: str, resolution: str, handback_notes: str | None = None
    ) -> bool:
        """Complete a takeover session and return control to autonomous system.

        C2: Delete the live session from Redis on completion (prevents DoS via
        max_concurrent_sessions overflow).  A compact history record is pushed
        to a capped list (_KEY_SESSION_HISTORY) so audit data is preserved.

        M4: Uses _session_mutate for the state transition.
        """
        ended_at = datetime.now(tz=timezone.utc)

        def _mutate(session: TakeoverSession) -> TakeoverSession | None:
            session.state = TakeoverState.COMPLETED
            session.ended_at = ended_at
            session.resolution = resolution
            return session

        updated = await self._session_mutate(session_id, _mutate)
        if updated is None:
            return False

        # C2: Delete from live-session store so max_concurrent_sessions gate is not
        # permanently blocked.  Write compact record to capped history list first.
        await self._archive_completed_session(updated, handback_notes)
        await self._sessions_delete(session_id)

        await self._resume_affected_tasks(updated.request.affected_tasks)

        completion_data = {
            "session_id": session_id,
            "duration_minutes": ((updated.ended_at - updated.started_at).total_seconds() / 60),
            "actions_count": len(updated.actions_taken),
            "resolution": resolution,
            "handback_notes": handback_notes,
        }

        completion_task_id = self.memory_manager.create_task_record(
            task_name="Takeover Session Completion",
            description=f"Takeover session completed: {resolution}",
            priority=updated.request.priority,
            agent_type="takeover_manager",
            inputs={"session_id": session_id},
            metadata={"original_request": asdict(updated.request)},
        )
        self.memory_manager.start_task(completion_task_id)
        self.memory_manager.complete_task(completion_task_id, outputs=completion_data)

        logger.info("Takeover session completed: %s - %s", session_id, resolution)
        await self._notify_state_change("session_completed", session_id)
        return True

    async def _archive_completed_session(self, session: TakeoverSession, handback_notes: str | None) -> None:
        """Push a compact history record to the capped Redis list."""
        r = await self._redis_client()
        if r is None:
            return  # no history in fallback mode
        record = json.dumps(
            {
                "session_id": session.session_id,
                "resolution": session.resolution,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "handback_notes": handback_notes,
            },
            ensure_ascii=False,
        )
        try:
            await r.lpush(_KEY_SESSION_HISTORY, record)
            await r.ltrim(_KEY_SESSION_HISTORY, 0, _SESSION_HISTORY_MAX - 1)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)

    async def _pause_affected_tasks(self, task_ids: List[str]):
        """Pause specified autonomous tasks"""
        for task_id in task_ids:
            await self._paused_add(task_id)

        if task_ids:
            logger.info("Paused %s autonomous tasks", len(task_ids))

    async def _resume_affected_tasks(self, task_ids: List[str]):
        """Resume specified autonomous tasks"""
        for task_id in task_ids:
            await self._paused_remove(task_id)

        if task_ids:
            logger.info("Resumed %s autonomous tasks", len(task_ids))

    async def _capture_system_snapshot(self) -> Dict[str, Any]:
        """Capture current system state for takeover context"""
        import psutil

        try:
            paused_count = await self._paused_count()
            sessions_count = await self._sessions_count()
            snapshot = {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "system_info": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage("/").percent,
                    "load_average": (psutil.getloadavg() if hasattr(psutil, "getloadavg") else None),
                },
                "active_processes": len(psutil.pids()),
                "paused_tasks_count": paused_count,
                "active_takeover_sessions": sessions_count,
            }
            return snapshot
        except Exception as e:
            logger.error("Failed to capture system snapshot: %s", e)
            return {
                "error": "Failed to capture system snapshot",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }

    async def _execute_trigger_handlers(self, request: TakeoverRequest):
        """Execute registered handlers for takeover triggers"""
        handlers = self.trigger_handlers.get(request.trigger, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(request)
                else:
                    handler(request)
            except Exception as e:
                logger.error("Trigger handler error: %s", e)

    async def _auto_approve_request(self, request_id: str):
        """Automatically approve a takeover request"""
        try:
            session_id = await self.approve_takeover(request_id, human_operator="system_auto_approval")
            logger.info("Auto-approved takeover request: %s -> %s", request_id, session_id)
        except Exception as e:
            logger.error("Auto-approval failed for %s: %s", request_id, e)

    async def _expire_request(self, request_id: str):
        """Handle expired takeover request.

        L4: Only notifies state change if the request actually existed.
        """
        existed = await self._pending_delete(request_id)

        task_id = await self._req_task_get(request_id)
        if task_id:
            self.memory_manager.fail_task(task_id, "Takeover request expired")
            await self._req_task_delete(request_id)

        if existed:
            logger.info("Takeover request expired: %s", request_id)
            await self._notify_state_change("request_expired", request_id)

    async def _get_task_id_for_request(self, request_id: str) -> str | None:
        """Return the memory task ID recorded when the takeover request was created."""
        task_id = await self._req_task_get(request_id)
        if task_id is None:
            logger.warning(
                "No memory task ID found for takeover request %s. "
                "The task completion/failure call will be skipped. (#2869)",
                request_id,
            )
        return task_id

    async def _notify_state_change(self, event_type: str, identifier: str):
        """Notify registered callbacks of state changes"""
        for callback in self.state_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, identifier)
                else:
                    callback(event_type, identifier)
            except Exception as e:
                logger.error("State change callback error: %s", e)

    def register_trigger_handler(self, trigger: TakeoverTrigger, handler: Callable):
        """Register a handler for specific takeover triggers"""
        if trigger not in self.trigger_handlers:
            self.trigger_handlers[trigger] = []
        self.trigger_handlers[trigger].append(handler)

    def register_state_change_callback(self, callback: Callable):
        """Register a callback for takeover state changes"""
        self.state_change_callbacks.append(callback)

    async def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all pending takeover requests.

        L4: Uses MGET (already called inside _pending_ids pruning) then
        converts existing results without a second per-ID round-trip.
        """
        r = await self._redis_client()
        if r is None:
            result = []
            for request in self._fb_pending.values():
                request_dict = asdict(request)
                request_dict["trigger"] = request.trigger.value
                request_dict["priority"] = request.priority.value
                request_dict["requested_at"] = request.requested_at.isoformat()
                if request.expires_at:
                    request_dict["expires_at"] = request.expires_at.isoformat()
                result.append(request_dict)
            return result

        try:
            members = await r.smembers(_KEY_PENDING_INDEX)
            ids = [m.decode() if isinstance(m, bytes) else m for m in members]
            if not ids:
                return []
            keys = [f"{_KEY_PENDING}:{rid}" for rid in ids]
            # L4: single MGET for all pending requests
            values = await r.mget(*keys)
            result = []
            stale_ids = []
            for rid, raw in zip(ids, values):
                if raw is None:
                    stale_ids.append(rid)
                    continue
                request = TakeoverRequest.from_json(raw)
                request_dict = asdict(request)
                request_dict["trigger"] = request.trigger.value
                request_dict["priority"] = request.priority.value
                request_dict["requested_at"] = request.requested_at.isoformat()
                if request.expires_at:
                    request_dict["expires_at"] = request.expires_at.isoformat()
                result.append(request_dict)
            # M2: prune stale entries found during MGET
            for rid in stale_ids:
                await r.srem(_KEY_PENDING_INDEX, rid)
                await r.hdel(_KEY_REQ_TASK, rid)
            return result
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return await self.get_pending_requests()  # recurse to fallback path

    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active takeover sessions"""
        sessions_map = await self._sessions_all()
        sessions = []
        for session in sessions_map.values():
            session_dict = asdict(session)
            for key in DATETIME_FIELD_KEYS:
                if session_dict[key]:
                    session_dict[key] = session_dict[key].isoformat()
            sessions.append(session_dict)
        return sessions

    async def get_system_status(self) -> Dict[str, Any]:
        """Get current takeover system status"""
        return {
            "pending_requests": await self._pending_count(),
            "active_sessions": await self._sessions_count(),
            "paused_tasks": await self._paused_count(),
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "default_timeout_minutes": int(self.default_timeout.total_seconds() / 60),
            "available_triggers": [trigger.value for trigger in TakeoverTrigger],
            "auto_approve_triggers": [trigger.value for trigger in self.auto_approve_triggers],
        }


# ---------------------------------------------------------------------------
# Module-level sync dispatch table (used by execute_takeover_action and
# _execute_action for non-async handlers to avoid code duplication)
# ---------------------------------------------------------------------------


def _execute_action_sync(action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous action dispatch (result only; side-effects handled separately).

    M1: pause_task / resume_task return their result strings here; the actual
    Redis mutations (_paused_add / _paused_remove) are applied by
    _apply_action_side_effects AFTER the CAS write so they are not blocked by
    the transaction.
    """
    if action_type == "pause_task":
        task_id = action_data.get("task_id")
        if task_id:
            return {"status": "task_paused", "task_id": task_id}
        return {"status": "error", "reason": "No task_id provided"}
    if action_type == "resume_task":
        task_id = action_data.get("task_id")
        if task_id:
            return {"status": "task_resumed", "task_id": task_id}
        return {"status": "error", "reason": "No task_id provided"}
    if action_type == "modify_parameters":
        return {"status": "parameters_modified", "changes": action_data.get("changes", {})}
    if action_type == "approve_operation":
        return {"status": "operation_approved", "operation_id": action_data.get("operation_id")}
    if action_type == "reject_operation":
        return {
            "status": "operation_rejected",
            "operation_id": action_data.get("operation_id"),
            "reason": action_data.get("reason", "Rejected by human operator"),
        }
    if action_type == "system_command":
        command = action_data.get("command", "")
        safe_commands = {
            "ps",
            "top",
            "htop",
            "d",
            "free",
            "uptime",
            "whoami",
            "pwd",
            "ls",
            "cat",
            "less",
            "head",
            "tail",
            "grep",
            "systemctl status",
            "docker ps",
            "docker logs",
        }
        if any(command.startswith(c) for c in safe_commands):
            return {"status": "command_executed", "command": command}
        return {"status": "command_rejected", "reason": "Command not in safe list"}
    if action_type == "custom_script":
        return {
            "status": "script_executed",
            "script": action_data.get("script_name"),
            "parameters": action_data.get("parameters", {}),
        }
    return {"status": "unknown_action", "action_type": action_type}


get_takeover_manager = lazy_singleton(TakeoverManager)
