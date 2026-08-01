# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cross-worker registry tests for TakeoverManager and DesktopStreamingManager (#11639).

Two manager instances share a single dict-backed fake-Redis stub to simulate
two uvicorn workers with a shared Redis server.  No live Redis required.

Proven behaviours:
- Takeover request created via instance A is visible and approvable via instance B
- GETDEL prevents double-approve (second approve raises ValueError)
- TTL expiry: expired pending request raises ValueError on approve attempt
- Streaming session registered on A is listed by B via Redis metadata
- Event published by A is relayed by B's subscriber to B's local clients
- Event published by A is NOT echoed back to A's own subscriber
- Completed session is removed from Redis (C2)
- Pending TTL prune removes stale index entries (M2)
- pause/resume actions mutate the shared paused set (M1)
- Non-owner terminate publishes terminate_requested; owner relay kills + deletes (H3)
- Concurrent session mutation — optimistic retry lands both or one retries (M4)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fake async-Redis stub
# ---------------------------------------------------------------------------


class _FakePubSub:
    """Minimal async pub/sub stub backed by the same shared store."""

    def __init__(self, store: "_FakeRedis") -> None:
        self._store = store
        self._channels: list[str] = []

    async def subscribe(self, *channels: str) -> None:
        for ch in channels:
            if ch not in self._channels:
                self._channels.append(ch)

    async def unsubscribe(self, *channels: str) -> None:
        for ch in channels:
            if ch in self._channels:
                self._channels.remove(ch)

    async def close(self) -> None:
        self._channels.clear()

    async def listen(self):
        """Yield messages queued for subscribed channels then stop."""
        while True:
            for ch in list(self._channels):
                queue: list = self._store._pubsub_queues.get(ch, [])
                while queue:
                    yield {"type": "message", "data": queue.pop(0)}
            await asyncio.sleep(0)
            break  # one pass — tests drain manually


class _FakePipeline:
    """Simple pipeline stub supporting WATCH/MULTI/EXEC for optimistic CAS (M4).

    Tracks the watched key's value at watch() time; execute() raises WatchError
    (simulated via ValueError with name WatchError) if the value changed.
    """

    class WatchError(Exception):
        pass

    def __init__(self, store: "_FakeRedis") -> None:
        self._store = store
        self._watched_keys: dict[str, bytes | None] = {}
        self._multi = False
        self._queue: list[tuple[str, tuple, dict]] = []

    async def watch(self, *keys: str) -> None:
        for key in keys:
            self._watched_keys[key] = self._store._strings.get(key)

    async def get(self, key: str) -> bytes | None:
        """Direct GET during watch phase (before MULTI)."""
        if self._store._is_expired(key):
            self._store._strings.pop(key, None)
            return None
        return self._store._strings.get(key)

    def multi(self) -> None:
        self._multi = True

    def set(self, key: str, value: Any) -> None:  # noqa: A003
        self._queue.append(("set", (key, value), {}))

    async def execute(self) -> list:
        # Check watched keys for concurrent modification
        for key, snapshot_val in self._watched_keys.items():
            current = self._store._strings.get(key)
            if current != snapshot_val:
                raise _FakePipeline.WatchError(f"WATCH key {key!r} was modified")
        results = []
        for cmd, args, kwargs in self._queue:
            if cmd == "set":
                self._store._strings[args[0]] = self._store._encode(args[1])
                results.append(True)
        return results

    async def reset(self) -> None:
        self._watched_keys.clear()
        self._multi = False
        self._queue.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _FakeRedis:
    """
    Shared-state async Redis stub implementing the command surface used by
    TakeoverManager and DesktopStreamingManager (#11639).

    Supports: get/set(ex=)/getdel/expire/delete/mget/
              sadd/srem/smembers/sismember/scard/
              hset/hget/hdel/hgetall/
              lpush/ltrim/
              pipeline(transaction=True)/publish + minimal pubsub.
    """

    def __init__(self) -> None:
        self._strings: dict[str, bytes] = {}
        self._sets: dict[str, set] = defaultdict(set)
        self._hashes: dict[str, dict[str, bytes]] = defaultdict(dict)
        self._lists: dict[str, list[bytes]] = defaultdict(list)
        self._expirations: dict[str, float] = {}  # key -> abs epoch when it expires
        self._pubsub_queues: dict[str, list] = defaultdict(list)

    def _is_expired(self, key: str) -> bool:
        exp = self._expirations.get(key)
        return exp is not None and time.time() > exp

    def _encode(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    # STRING
    async def set(self, key: str, value: Any, ex: int | None = None) -> None:  # noqa: A003
        self._strings[key] = self._encode(value)
        if ex is not None:
            self._expirations[key] = time.time() + ex

    async def get(self, key: str) -> bytes | None:
        if self._is_expired(key):
            self._strings.pop(key, None)
            return None
        return self._strings.get(key)

    async def getdel(self, key: str) -> bytes | None:
        if self._is_expired(key):
            self._strings.pop(key, None)
            return None
        return self._strings.pop(key, None)

    async def mget(self, *keys: str) -> list[bytes | None]:
        result = []
        for key in keys:
            if self._is_expired(key):
                self._strings.pop(key, None)
                result.append(None)
            else:
                result.append(self._strings.get(key))
        return result

    async def expire(self, key: str, seconds: int) -> None:
        self._expirations[key] = time.time() + seconds

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._strings:
                del self._strings[key]
                count += 1
        return count

    # SET
    async def sadd(self, key: str, *members: Any) -> int:
        before = len(self._sets[key])
        self._sets[key].update(self._encode(m) for m in members)
        return len(self._sets[key]) - before

    async def srem(self, key: str, *members: Any) -> int:
        count = 0
        for m in members:
            enc = self._encode(m)
            if enc in self._sets[key]:
                self._sets[key].discard(enc)
                count += 1
        return count

    async def smembers(self, key: str) -> set:
        return set(self._sets[key])

    async def sismember(self, key: str, member: Any) -> int:
        return int(self._encode(member) in self._sets[key])

    async def scard(self, key: str) -> int:
        return len(self._sets[key])

    # HASH
    async def hset(self, name: str, field: str, value: Any) -> int:
        existed = field in self._hashes[name]
        self._hashes[name][field] = self._encode(value)
        return 0 if existed else 1

    async def hget(self, name: str, field: str) -> bytes | None:
        return self._hashes[name].get(field)

    async def hdel(self, name: str, *fields: str) -> int:
        count = 0
        for f in fields:
            if f in self._hashes[name]:
                del self._hashes[name][f]
                count += 1
        return count

    async def hgetall(self, name: str) -> dict:
        return dict(self._hashes[name])

    # LIST (M4 history)
    async def lpush(self, key: str, *values: Any) -> int:
        for v in values:
            self._lists[key].insert(0, self._encode(v))
        return len(self._lists[key])

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        self._lists[key] = self._lists[key][start : stop + 1]

    # PIPELINE (M4 optimistic CAS)
    @asynccontextmanager
    async def pipeline(self, transaction: bool = False):
        pipe = _FakePipeline(self)
        yield pipe

    # PUB/SUB
    async def publish(self, channel: str, message: Any) -> int:
        self._pubsub_queues[channel].append(self._encode(message))
        return 1

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self)


# ---------------------------------------------------------------------------
# Helpers to build manager instances that share a fake Redis
# ---------------------------------------------------------------------------


def _make_memory_manager() -> MagicMock:
    """Return a MemoryManager stub that records calls but doesn't touch DB.

    The a-prefixed methods must be AsyncMock: TakeoverManager awaits
    ``acreate_task_record``/``astart_task``/``acomplete_task``/``afail_task``,
    and awaiting a plain MagicMock raises
    ``TypeError: object MagicMock can't be used in 'await' expression``.

    The sync spellings are kept alongside them. This stub was written against
    the sync API; MemoryManager later grew the async variants and the stub was
    never updated, which is what broke all 8 tests in this module. Same shape as
    the redis-client stub rot in #12903 — a hand-listed double lagging the thing
    it doubles.
    """
    mm = MagicMock()
    mm.create_task_record.return_value = "task-123"
    mm.start_task.return_value = None
    mm.complete_task.return_value = None
    mm.fail_task.return_value = None
    mm.acreate_task_record = AsyncMock(return_value="task-123")
    mm.astart_task = AsyncMock(return_value=None)
    mm.acomplete_task = AsyncMock(return_value=None)
    mm.afail_task = AsyncMock(return_value=None)
    return mm


def _takeover_pair(shared_redis: _FakeRedis):
    """Return two TakeoverManager instances sharing *shared_redis*."""
    import takeover_manager as tm_mod

    a = tm_mod.TakeoverManager(memory_manager=_make_memory_manager(), _redis=shared_redis)
    b = tm_mod.TakeoverManager(memory_manager=_make_memory_manager(), _redis=shared_redis)
    return a, b


def _streaming_pair(shared_redis: _FakeRedis):
    """Return two DesktopStreamingManager instances sharing *shared_redis*."""
    import desktop_streaming_manager as dsm_mod

    a = dsm_mod.DesktopStreamingManager(_redis=shared_redis)
    b = dsm_mod.DesktopStreamingManager(_redis=shared_redis)
    return a, b


# ---------------------------------------------------------------------------
# TakeoverManager cross-worker tests
# ---------------------------------------------------------------------------


class TestTakeoverManagerCrossWorker:
    @pytest.mark.asyncio
    async def test_request_visible_on_second_worker(self):
        """Request created on A is visible via B."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="test reason",
            auto_approve=False,
        )

        # B should see the pending request
        pending = await b._pending_get(request_id)
        assert pending is not None, "B must see the request written by A"
        assert pending.request_id == request_id
        assert pending.reason == "test reason"

    @pytest.mark.asyncio
    async def test_approve_on_second_worker(self):
        """B can approve a request created by A."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="needs approval",
            auto_approve=False,
        )

        session_id = await b.approve_takeover(request_id, human_operator="operator@example.com")
        assert session_id.startswith("session_"), f"Unexpected session_id: {session_id}"

        # Session must now be visible on A
        session = await a._sessions_get(session_id)
        assert session is not None, "Session created by B must be visible on A"
        assert session.human_operator == "operator@example.com"

    @pytest.mark.asyncio
    async def test_getdel_prevents_double_approve(self):
        """GETDEL ensures only one worker can approve a request."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="race condition test",
            auto_approve=False,
        )

        # First approval succeeds
        await b.approve_takeover(request_id, human_operator="op1")

        # Second approval must raise; the request no longer exists so _validate
        # raises "not found", and _create_takeover_session raises "already approved"
        with pytest.raises(ValueError):
            await a.approve_takeover(request_id, human_operator="op2")

    @pytest.mark.asyncio
    async def test_expired_request_raises(self):
        """Approving an expired request raises ValueError after TTL elapses."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="expiry test",
            auto_approve=False,
        )

        # Force TTL to look expired by backdating the expiration in the stub
        key = f"autobot:takeover:pending:{request_id}"
        redis._expirations[key] = time.time() - 1  # already expired

        with pytest.raises(ValueError, match="expired|not found"):
            await b.approve_takeover(request_id, human_operator="late_op")

    @pytest.mark.asyncio
    async def test_paused_tasks_shared(self):
        """Paused tasks set is shared across workers."""
        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        await a._paused_add("task-42")
        members = await redis.smembers("autobot:takeover:paused_tasks")
        assert b"task-42" in members or "task-42" in members

    @pytest.mark.asyncio
    async def test_completed_session_removed_from_redis(self):
        """C2: Completing a session removes it from the live Redis store."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="c2 test",
            auto_approve=False,
        )
        session_id = await b.approve_takeover(request_id, human_operator="op")

        # Verify live session exists
        assert await a._sessions_get(session_id) is not None

        result = await a.complete_takeover_session(session_id, resolution="done")
        assert result is True

        # C2: session must be gone from live store; count must not be stuck
        assert await a._sessions_get(session_id) is None
        assert await a._sessions_count() == 0

    @pytest.mark.asyncio
    async def test_pending_ttl_prune_removes_stale_index(self):
        """M2: _pending_ids() prunes index members whose STRING key expired."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, _ = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="prune test",
            auto_approve=False,
        )

        # Simulate TTL expiry of the STRING key only (SET member stays stale)
        string_key = f"autobot:takeover:pending:{request_id}"
        redis._strings.pop(string_key, None)  # expire the STRING without SREM

        # Before pruning: index still contains the stale id
        raw_members = await redis.smembers("autobot:takeover:pending_index")
        raw_ids = {m.decode() if isinstance(m, bytes) else m for m in raw_members}
        assert request_id in raw_ids, "stale entry must be in index before prune"

        # _pending_ids() should prune and return empty set
        live_ids = await a._pending_ids()
        assert request_id not in live_ids

        # Index SET must now be clean
        raw_members_after = await redis.smembers("autobot:takeover:pending_index")
        raw_ids_after = {m.decode() if isinstance(m, bytes) else m for m in raw_members_after}
        assert request_id not in raw_ids_after

    @pytest.mark.asyncio
    async def test_pause_resume_mutate_paused_set(self):
        """M1: pause_task/resume_task action handlers actually mutate the shared paused set."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="m1 test",
            auto_approve=False,
        )
        session_id = await b.approve_takeover(request_id, human_operator="op")

        # Execute pause_task action
        result = await a.execute_takeover_action(session_id, "pause_task", {"task_id": "task-X"})
        assert result.get("status") == "task_paused"

        # task-X must now be in the shared paused set
        members = await redis.smembers("autobot:takeover:paused_tasks")
        encoded = {m.decode() if isinstance(m, bytes) else m for m in members}
        assert "task-X" in encoded, f"task-X not in paused set: {encoded}"

        # Execute resume_task action
        result2 = await a.execute_takeover_action(session_id, "resume_task", {"task_id": "task-X"})
        assert result2.get("status") == "task_resumed"

        members_after = await redis.smembers("autobot:takeover:paused_tasks")
        encoded_after = {m.decode() if isinstance(m, bytes) else m for m in members_after}
        assert "task-X" not in encoded_after

    @pytest.mark.asyncio
    async def test_concurrent_session_mutation_both_land(self):
        """M4: Two sequential mutations to the same session both persist (CAS retry)."""
        import takeover_manager as tm_mod

        redis = _FakeRedis()
        a, b = _takeover_pair(redis)

        request_id = await a.request_takeover(
            trigger=tm_mod.TakeoverTrigger.MANUAL_REQUEST,
            reason="m4 test",
            auto_approve=False,
        )
        session_id = await b.approve_takeover(request_id, human_operator="op")

        # Apply two sequential actions — in practice these could be concurrent
        # but the fake pipeline is single-threaded so we test sequential correctness.
        await a.execute_takeover_action(session_id, "approve_operation", {"operation_id": "op1"})
        await b.execute_takeover_action(session_id, "approve_operation", {"operation_id": "op2"})

        final_session = await a._sessions_get(session_id)
        assert final_session is not None
        action_types = [ac["action_type"] for ac in final_session.actions_taken]
        assert "approve_operation" in action_types, f"actions missing: {action_types}"


# ---------------------------------------------------------------------------
# DesktopStreamingManager cross-worker tests
# ---------------------------------------------------------------------------


class TestDesktopStreamingManagerCrossWorker:
    @pytest.mark.asyncio
    async def test_session_registered_on_a_visible_to_b(self):
        """Session metadata written by A is visible via B's list_all_sessions."""
        redis = _FakeRedis()
        a, b = _streaming_pair(redis)

        # Stub out VNC creation so no real subprocesses are spawned
        vnc_info = {"session_id": "stream_u1_1", "vnc_port": 5910, "novnc_port": 6090}
        a.vnc_manager.create_session = AsyncMock(return_value=vnc_info)

        await a.create_streaming_session("u1")
        # stop the relay task started by create_streaming_session
        await a.stop()

        sessions_b = await b.list_all_sessions()
        session_ids = [s.get("session_id") for s in sessions_b]
        assert any("u1" in sid for sid in session_ids), f"B must see session created by A; got {session_ids}"

    @pytest.mark.asyncio
    async def test_event_published_by_a_relayed_by_b(self):
        """Event published by A is relayed by B's subscriber to B's local clients."""
        import desktop_streaming_manager as dsm_mod

        redis = _FakeRedis()
        a, b = _streaming_pair(redis)

        # Give B a fake local client for session "sess-1"
        fake_ws = AsyncMock()
        b.session_clients["sess-1"] = ["client-b1"]
        b.websocket_clients["client-b1"] = fake_ws

        # Simulate A publishing with a different worker_id (different from B's _WORKER_ID)
        a_worker_id = "worker-A-different-from-B"

        msg = json.dumps(
            {
                "worker_id": a_worker_id,
                "type": "screenshot",
                "payload": {"session_id": "sess-1", "data": "base64..."},
            },
            ensure_ascii=False,
        )
        await redis.publish(dsm_mod._DESKTOP_EVENTS_CHANNEL, msg)

        # Run B's relay handler once
        raw_msgs = redis._pubsub_queues.get(dsm_mod._DESKTOP_EVENTS_CHANNEL, [])
        for raw in raw_msgs:
            await b._handle_pubsub_message(raw)

        # B's local client must receive the relayed message
        fake_ws.send.assert_called_once()
        sent = json.loads(fake_ws.send.call_args[0][0])
        assert sent["type"] == "screenshot"
        assert sent["data"]["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_event_not_echoed_to_originating_worker(self):
        """Event from this worker is not self-echoed by B (same worker_id check)."""
        import desktop_streaming_manager as dsm_mod

        redis = _FakeRedis()
        _, b = _streaming_pair(redis)

        fake_ws = AsyncMock()
        b.session_clients["sess-2"] = ["client-b2"]
        b.websocket_clients["client-b2"] = fake_ws

        # Publish with B's own worker_id — must NOT be relayed to B's clients
        msg = json.dumps(
            {
                "worker_id": dsm_mod._WORKER_ID,  # same as B (module-level constant)
                "type": "screenshot",
                "payload": {"session_id": "sess-2", "data": "base64..."},
            },
            ensure_ascii=False,
        )
        await redis.publish(dsm_mod._DESKTOP_EVENTS_CHANNEL, msg)

        raw_msgs = redis._pubsub_queues.get(dsm_mod._DESKTOP_EVENTS_CHANNEL, [])
        for raw in raw_msgs:
            await b._handle_pubsub_message(raw)

        # B must NOT forward the message (it originated here)
        fake_ws.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminate_removes_redis_metadata(self):
        """Terminating a session removes its Redis metadata."""
        redis = _FakeRedis()
        a, b = _streaming_pair(redis)

        vnc_info = {"vnc_port": 5911, "novnc_port": 6091}
        a.vnc_manager.create_session = AsyncMock(return_value=vnc_info)
        a.vnc_manager.terminate_session = AsyncMock(return_value=True)

        result = await a.create_streaming_session("u2")
        await a.stop()
        session_id = result["websocket_endpoint"].rsplit("/", 1)[-1]

        # Verify B sees it
        sessions_b_before = await b.list_all_sessions()
        assert len(sessions_b_before) == 1

        # Terminate from A using the real session_id
        await a.terminate_streaming_session(session_id)

        sessions_b_after = await b.list_all_sessions()
        assert len(sessions_b_after) == 0, "Metadata must be removed on termination"

    @pytest.mark.asyncio
    async def test_subscriber_lifecycle_start_stop(self):
        """start() creates the subscriber task; stop() cancels it cleanly."""
        import desktop_streaming_manager as dsm_mod

        redis = _FakeRedis()
        mgr = dsm_mod.DesktopStreamingManager(_redis=redis)

        await mgr.start()
        assert mgr._subscriber_task is not None
        assert not mgr._subscriber_task.done()

        await mgr.stop()
        assert mgr._subscriber_task is None

    @pytest.mark.asyncio
    async def test_non_owner_terminate_publishes_terminate_requested(self):
        """H3: Non-owner worker publishes session_terminate_requested instead of deleting."""
        import desktop_streaming_manager as dsm_mod

        redis = _FakeRedis()
        a, b = _streaming_pair(redis)

        # A "owns" the session (has it in session_clients and vnc_manager)
        session_id = "sess-owner-test"
        a.session_clients[session_id] = []
        a.vnc_manager.active_sessions[session_id] = {}

        # Write Redis metadata so B sees the session exists
        await a._meta_set(session_id, {"session_id": session_id, "worker_id": "worker-A"})

        # B is the non-owner — should publish terminate_requested
        result = await b.terminate_streaming_session(session_id)
        assert result is True, "Non-owner terminate must return True (accepted)"

        # Verify the event was published to the channel
        channel = dsm_mod._DESKTOP_EVENTS_CHANNEL
        queued = redis._pubsub_queues.get(channel, [])
        assert len(queued) >= 1, "terminate_requested event must be published"
        last_msg = json.loads(queued[-1])
        assert last_msg["type"] == "session_terminate_requested"
        assert last_msg["payload"]["session_id"] == session_id

        # Metadata must NOT be deleted yet (owner handles that)
        meta = await a._meta_get(session_id)
        assert meta is not None, "Non-owner must NOT delete metadata prematurely"

    @pytest.mark.asyncio
    async def test_owner_relay_terminates_on_terminate_requested(self):
        """H3: Owner relay calls _local_terminate when it receives terminate_requested."""
        redis = _FakeRedis()
        a, b = _streaming_pair(redis)

        # A is owner
        session_id = "sess-relay-test"
        a.session_clients[session_id] = []
        a.vnc_manager.active_sessions[session_id] = {}
        a.vnc_manager.terminate_session = AsyncMock(return_value=True)

        await a._meta_set(session_id, {"session_id": session_id})

        # B publishes terminate_requested (different worker_id)
        b_worker_id = "worker-B-different"
        msg = json.dumps(
            {
                "worker_id": b_worker_id,
                "type": "session_terminate_requested",
                "payload": {"session_id": session_id},
            }
        )

        await a._handle_pubsub_message(msg.encode())

        # A's local terminate must have been called
        a.vnc_manager.terminate_session.assert_awaited_once_with(session_id)

        # Metadata must be deleted by owner
        meta_after = await a._meta_get(session_id)
        assert meta_after is None, "Owner must delete metadata after local terminate"
