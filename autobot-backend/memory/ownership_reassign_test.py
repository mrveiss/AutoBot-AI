# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for memory ownership reassignment (Issue #11065).

Coverage plan
-------------
1. ChromaDB verbatim — matching ``user_id`` records are reassigned; non-matching untouched.
2. ChromaDB trajectory — same, but via ``user_id`` field in trajectory metadata.
3. ChromaDB ``owner_id`` — records keyed by ``owner_id`` are also reassigned.
4. Redis working-memory — only matching ``user_id`` keys inside allowed key shape are rewritten;
   non-matching payloads and non-working-memory keys are never touched.
5. Graph entities — ``user_id`` and ``owner_id`` inside metadata.* are both rewritten.
6. A store raising does NOT crash ``reassign_user_memory``; other stores still run.
7. No-op when ids are blank or equal.
8. ``delete_user(..., reassign_to=X)`` calls ``reassign_user_memory`` with correct args
   before deleting the DB row.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_chroma_collection(ids=None, metas=None):
    """Return a minimal ChromaDB collection AsyncMock."""
    ids = ids or []
    metas = metas or [{} for _ in ids]
    col = AsyncMock()
    col.get = AsyncMock(return_value={"ids": ids, "metadatas": metas})
    col.update = AsyncMock()
    return col


def _make_store(collection):
    """Return a store AsyncMock whose ``_get_collection`` returns *collection*."""
    store = AsyncMock()
    store._get_collection = AsyncMock(return_value=collection)
    return store


# ---------------------------------------------------------------------------
# 1–3. ChromaDB stores
# ---------------------------------------------------------------------------


class TestReassignVerbatim:
    """verbatim ChromaDB store: metadata ``user_id`` reassignment."""

    @pytest.mark.asyncio
    async def test_matching_records_are_reassigned(self):
        import memory.ownership_reassign as mr

        col = _make_chroma_collection(
            ids=["v1", "v2"],
            metas=[{"user_id": "user-A", "session_id": "s1"}, {"user_id": "user-A", "session_id": "s2"}],
        )
        store = _make_store(col)
        orig = mr.get_verbatim_store
        mr.get_verbatim_store = AsyncMock(return_value=store)
        try:
            count = await mr._reassign_verbatim("user-A", "user-B")
        finally:
            mr.get_verbatim_store = orig

        assert count == 2
        col.update.assert_called_once()
        _, kwargs = col.update.call_args
        assert kwargs["ids"] == ["v1", "v2"]
        # Every updated metadata must have user_id == new owner
        for meta in kwargs["metadatas"]:
            assert meta["user_id"] == "user-B"
        # Other fields must be preserved
        assert kwargs["metadatas"][0]["session_id"] == "s1"

    @pytest.mark.asyncio
    async def test_no_matching_records_returns_zero(self):
        import memory.ownership_reassign as mr

        col = _make_chroma_collection(ids=[], metas=[])
        store = _make_store(col)
        orig = mr.get_verbatim_store
        mr.get_verbatim_store = AsyncMock(return_value=store)
        try:
            count = await mr._reassign_verbatim("user-A", "user-B")
        finally:
            mr.get_verbatim_store = orig

        assert count == 0
        col.update.assert_not_called()


class TestReassignTrajectory:
    """trajectory ChromaDB store: metadata ``user_id`` reassignment."""

    @pytest.mark.asyncio
    async def test_trajectory_user_id_reassigned(self):
        import memory.ownership_reassign as mr

        col = _make_chroma_collection(
            ids=["t1"],
            metas=[{"user_id": "user-A", "agent_id": "agent-1", "outcome": "success"}],
        )
        store = _make_store(col)
        orig = mr.get_trajectory_store
        mr.get_trajectory_store = AsyncMock(return_value=store)
        try:
            count = await mr._reassign_trajectory("user-A", "user-B")
        finally:
            mr.get_trajectory_store = orig

        assert count == 1
        col.update.assert_called_once()
        _, kwargs = col.update.call_args
        assert kwargs["metadatas"][0]["user_id"] == "user-B"
        # agent_id and outcome must not be touched
        assert kwargs["metadatas"][0]["agent_id"] == "agent-1"
        assert kwargs["metadatas"][0]["outcome"] == "success"


# ---------------------------------------------------------------------------
# 4. Redis working-memory
# ---------------------------------------------------------------------------


class TestReassignWorkingMemory:
    """Redis working-memory: only matching + allowed keys are rewritten."""

    @staticmethod
    def _make_redis_stub(keys, payloads):
        """Return a Redis AsyncMock that serves *payloads* keyed by *keys* on scan+get."""
        redis = AsyncMock()

        # Simulate a single-pass scan returning all keys (cursor 0 → done).
        redis.scan = AsyncMock(return_value=(0, [k.encode() for k in keys]))

        async def _get(key):
            key_str = key if isinstance(key, str) else key.decode()
            val = payloads.get(key_str)
            return json.dumps(val).encode() if val is not None else None

        redis.get = AsyncMock(side_effect=_get)
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_matching_key_is_rewritten(self):
        import memory.ownership_reassign as mr

        key = "autobot:session:s1:memory:k1"
        payload = {"user_id": "user-A", "content": "hello"}
        redis = self._make_redis_stub([key], {key: payload})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_working_memory("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 1
        redis.set.assert_called_once()
        saved_key, saved_val = redis.set.call_args[0]
        assert saved_key == key
        saved = json.loads(saved_val)
        assert saved["user_id"] == "user-B"
        assert saved["content"] == "hello"

    @pytest.mark.asyncio
    async def test_non_matching_user_id_not_touched(self):
        import memory.ownership_reassign as mr

        key = "autobot:session:s1:memory:k1"
        payload = {"user_id": "user-C", "content": "other"}
        redis = self._make_redis_stub([key], {key: payload})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_working_memory("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 0
        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_working_memory_key_never_touched(self):
        """A key that fails ``is_working_memory_key`` is always skipped."""
        import memory.ownership_reassign as mr

        # Even though the payload has user_id==user-A, the non-WM key must be ignored.
        bad_key = "some:other:namespace:key"
        payload = {"user_id": "user-A"}
        redis = self._make_redis_stub([bad_key], {bad_key: payload})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_working_memory("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 0
        redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_keys_only_matching_rewritten(self):
        """Two keys in scan; only the one with user_id==old is rewritten."""
        import memory.ownership_reassign as mr

        key_a = "autobot:session:s1:memory:k1"
        key_b = "autobot:session:s2:memory:k2"
        payloads = {
            key_a: {"user_id": "user-A", "content": "mine"},
            key_b: {"user_id": "user-C", "content": "theirs"},
        }
        redis = AsyncMock()
        # Two-key scan
        redis.scan = AsyncMock(return_value=(0, [k.encode() for k in [key_a, key_b]]))

        async def _get(k):
            key_str = k if isinstance(k, str) else k.decode()
            val = payloads.get(key_str)
            return json.dumps(val).encode() if val is not None else None

        redis.get = AsyncMock(side_effect=_get)
        redis.set = AsyncMock()

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_working_memory("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 1
        assert redis.set.call_count == 1
        saved_key, _ = redis.set.call_args[0]
        assert saved_key == key_a


# ---------------------------------------------------------------------------
# 5. Graph entities
# ---------------------------------------------------------------------------


class TestReassignGraphEntities:
    """Redis graph entities: metadata.user_id / metadata.owner_id reassigned."""

    @staticmethod
    def _make_graph_redis(keys, entities):
        redis = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, [k.encode() for k in keys]))

        json_client = AsyncMock()

        async def _json_get(key):
            return entities.get(key if isinstance(key, str) else key.decode())

        json_client.get = AsyncMock(side_effect=_json_get)
        json_client.set = AsyncMock()
        redis.json = MagicMock(return_value=json_client)
        return redis, json_client

    @pytest.mark.asyncio
    async def test_user_id_in_metadata_reassigned(self):
        import memory.ownership_reassign as mr

        key = "memory:entity:e1"
        entity = {"id": "e1", "name": "Alice", "metadata": {"user_id": "user-A"}}
        redis, json_client = self._make_graph_redis([key], {key: entity})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_graph_entities("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 1
        json_client.set.assert_called_once()
        call_args = json_client.set.call_args[0]
        assert call_args[0] == key
        assert call_args[1] == "$.metadata"
        assert call_args[2]["user_id"] == "user-B"

    @pytest.mark.asyncio
    async def test_owner_id_in_metadata_reassigned(self):
        import memory.ownership_reassign as mr

        key = "memory:entity:e2"
        entity = {"id": "e2", "metadata": {"owner_id": "user-A"}}
        redis, json_client = self._make_graph_redis([key], {key: entity})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_graph_entities("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 1
        assert json_client.set.call_args[0][2]["owner_id"] == "user-B"

    @pytest.mark.asyncio
    async def test_both_user_id_and_owner_id_reassigned(self):
        import memory.ownership_reassign as mr

        key = "memory:entity:e3"
        entity = {"id": "e3", "metadata": {"user_id": "user-A", "owner_id": "user-A"}}
        redis, json_client = self._make_graph_redis([key], {key: entity})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_graph_entities("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 1
        saved_meta = json_client.set.call_args[0][2]
        assert saved_meta["user_id"] == "user-B"
        assert saved_meta["owner_id"] == "user-B"

    @pytest.mark.asyncio
    async def test_unrelated_entity_not_touched(self):
        import memory.ownership_reassign as mr

        key = "memory:entity:e4"
        entity = {"id": "e4", "metadata": {"user_id": "user-C"}}
        redis, json_client = self._make_graph_redis([key], {key: entity})

        orig = mr.get_redis_client
        mr.get_redis_client = AsyncMock(return_value=redis)
        try:
            count = await mr._reassign_graph_entities("user-A", "user-B")
        finally:
            mr.get_redis_client = orig

        assert count == 0
        json_client.set.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Store-level failure isolation
# ---------------------------------------------------------------------------


class TestReassignUserMemoryFaultTolerance:
    """A failing store must not crash reassign_user_memory; others still run."""

    @pytest.mark.asyncio
    async def test_failing_store_records_zero_and_continues(self):
        from memory.ownership_reassign import reassign_user_memory

        async def _raise(*_args, **_kwargs):
            raise RuntimeError("chroma down")

        async def _ok(*_args, **_kwargs):
            return 5

        with (
            patch("memory.ownership_reassign._reassign_verbatim", side_effect=_raise),
            patch("memory.ownership_reassign._reassign_trajectory", side_effect=_ok),
            patch("memory.ownership_reassign._reassign_working_memory", side_effect=_ok),
            patch("memory.ownership_reassign._reassign_graph_entities", side_effect=_ok),
        ):
            counts = await reassign_user_memory("user-A", "user-B")

        # verbatim errored → 0; others returned 5
        assert counts["verbatim"] == 0
        assert counts["trajectory"] == 5
        assert counts["working_memory"] == 5
        assert counts["graph"] == 5

    @pytest.mark.asyncio
    async def test_all_stores_fail_returns_zeros(self):
        from memory.ownership_reassign import reassign_user_memory

        async def _raise(*_args, **_kwargs):
            raise RuntimeError("everything down")

        with (
            patch("memory.ownership_reassign._reassign_verbatim", side_effect=_raise),
            patch("memory.ownership_reassign._reassign_trajectory", side_effect=_raise),
            patch("memory.ownership_reassign._reassign_working_memory", side_effect=_raise),
            patch("memory.ownership_reassign._reassign_graph_entities", side_effect=_raise),
        ):
            counts = await reassign_user_memory("user-A", "user-B")

        assert counts == {"verbatim": 0, "trajectory": 0, "working_memory": 0, "graph": 0}


# ---------------------------------------------------------------------------
# 7. No-op guard conditions
# ---------------------------------------------------------------------------


class TestNoOpGuards:
    """Blank or equal ids must produce an immediate no-op."""

    @pytest.mark.asyncio
    async def test_blank_old_user_id(self):
        from memory.ownership_reassign import reassign_user_memory

        with patch("memory.ownership_reassign._bootstrap") as mock_boot:
            counts = await reassign_user_memory("", "user-B")

        mock_boot.assert_not_called()
        assert all(v == 0 for v in counts.values())

    @pytest.mark.asyncio
    async def test_blank_new_owner_id(self):
        from memory.ownership_reassign import reassign_user_memory

        with patch("memory.ownership_reassign._bootstrap") as mock_boot:
            counts = await reassign_user_memory("user-A", "")

        mock_boot.assert_not_called()
        assert all(v == 0 for v in counts.values())

    @pytest.mark.asyncio
    async def test_equal_ids(self):
        from memory.ownership_reassign import reassign_user_memory

        with patch("memory.ownership_reassign._bootstrap") as mock_boot:
            counts = await reassign_user_memory("user-A", "user-A")

        mock_boot.assert_not_called()
        assert all(v == 0 for v in counts.values())


# ---------------------------------------------------------------------------
# 8. delete_user wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.org_id = uuid.uuid4()
    context.user_id = uuid.uuid4()
    return context


@pytest.fixture
def user_service(mock_session, mock_context):
    from user_management.services.user_service import UserService

    return UserService(session=mock_session, context=mock_context)


@pytest.fixture
def sample_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    return user


class TestDeleteUserReassignWiring:
    """delete_user calls reassign_user_memory before deleting the DB row."""

    @pytest.mark.asyncio
    async def test_reassign_to_calls_reassign_before_delete(
        self, user_service, sample_user, mock_session
    ):  # noqa: ARG002
        import sys

        new_owner = uuid.uuid4()
        fake_counts = {"verbatim": 3, "trajectory": 0, "working_memory": 1, "graph": 2}
        mock_reassign = AsyncMock(return_value=fake_counts)

        # The lazy import inside delete_user does:
        #   from memory.ownership_reassign import reassign_user_memory
        # Intercept via sys.modules so the imported name resolves to our mock.
        fake_module = MagicMock()
        fake_module.reassign_user_memory = mock_reassign

        with patch.dict(sys.modules, {"memory.ownership_reassign": fake_module}):
            with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
                with patch.object(user_service, "_audit_log", AsyncMock()):
                    result = await user_service.delete_user(
                        sample_user.id,
                        hard_delete=False,
                        reassign_to=new_owner,
                    )

        assert result is True
        mock_reassign.assert_called_once_with(str(sample_user.id), str(new_owner))

    @pytest.mark.asyncio
    async def test_no_reassign_to_skips_reassign(self, user_service, sample_user):
        """When reassign_to is None, reassign_user_memory is never called."""
        import sys

        mock_reassign = AsyncMock()
        fake_module = MagicMock()
        fake_module.reassign_user_memory = mock_reassign
        with patch.dict(sys.modules, {"memory.ownership_reassign": fake_module}):
            with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
                with patch.object(user_service, "_audit_log", AsyncMock()):
                    result = await user_service.delete_user(sample_user.id, hard_delete=False)

        assert result is True
        mock_reassign.assert_not_called()

    @pytest.mark.asyncio
    async def test_hard_delete_propagates_reassign_error(self, user_service, sample_user):
        """For hard_delete, if reassign raises the delete is aborted."""
        new_owner = uuid.uuid4()

        with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
            with patch.object(user_service, "_audit_log", AsyncMock()):
                broken_module = MagicMock()
                broken_module.reassign_user_memory = AsyncMock(side_effect=RuntimeError("store catastrophe"))
                with patch.dict("sys.modules", {"memory.ownership_reassign": broken_module}):
                    with pytest.raises(RuntimeError, match="store catastrophe"):
                        await user_service.delete_user(
                            sample_user.id,
                            hard_delete=True,
                            reassign_to=new_owner,
                        )

    @pytest.mark.asyncio
    async def test_soft_delete_continues_despite_reassign_error(self, user_service, sample_user):
        """For soft delete, a failing reassign logs a warning and proceeds."""
        new_owner = uuid.uuid4()

        with patch.object(user_service, "get_user", AsyncMock(return_value=sample_user)):
            with patch.object(user_service, "_audit_log", AsyncMock()):
                broken_module = MagicMock()
                broken_module.reassign_user_memory = AsyncMock(side_effect=RuntimeError("oops"))
                with patch.dict("sys.modules", {"memory.ownership_reassign": broken_module}):
                    result = await user_service.delete_user(
                        sample_user.id,
                        hard_delete=False,
                        reassign_to=new_owner,
                    )

        # Soft delete succeeded despite reassign error
        assert result is True
