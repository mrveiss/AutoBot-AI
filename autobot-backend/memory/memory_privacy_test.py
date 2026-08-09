# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for memory transparency engine (Issue #10554).

Test plan
---------
1. list_user_memories — returns only the caller's items (not other users').
2. forget_memory / forget_everywhere — item deleted from every store; cross-user
   delete is rejected (tenant isolation).
3. Cross-user list access denied — a separate user_id yields empty results.
4. export_user_memory — wrapper around list; correct schema.
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_chroma_stub(ids=None, docs=None, metas=None):
    """Return a ChromaDB collection stub with a .get() that returns ``ids``."""
    docs = docs or ["chunk text"] * len(ids or [])
    metas = metas or [{}] * len(ids or [])
    collection = AsyncMock()
    collection.get.return_value = {
        "ids": ids or [],
        "documents": docs,
        "metadatas": metas,
    }
    collection.delete = AsyncMock()
    collection.add = AsyncMock()
    return collection


class TestListUserMemories(unittest.IsolatedAsyncioTestCase):
    """list_user_memories returns only the target user's items."""

    async def asyncSetUp(self):
        # Patch all store accessors so tests don't need live Redis/ChromaDB.
        self._patches = []

        # VerbatimStore stub
        verbatim_collection = _make_chroma_stub(
            ids=["v1"],
            docs=["hello world"],
            metas=[{"user_id": "user-A", "timestamp": "2026-01-01T00:00:00+00:00", "session_id": "s1"}],
        )
        verbatim_store = AsyncMock()
        verbatim_store._get_collection = AsyncMock(return_value=verbatim_collection)
        p1 = patch("memory.transparency.get_verbatim_store_import", create=True)  # patched inline below
        self._verbatim_collection = verbatim_collection
        self._verbatim_store = verbatim_store

        # TrajectoryStore stub (no items for user-A so trajectory list is empty)
        traj_collection = _make_chroma_stub(ids=[])
        traj_store = AsyncMock()
        traj_store._get_collection = AsyncMock(return_value=traj_collection)
        self._traj_collection = traj_collection
        self._traj_store = traj_store

    async def test_verbatim_returns_only_owner_chunks(self):
        """_list_verbatim filters by user_id metadata."""
        import memory.transparency as mt
        from memory.transparency import _list_verbatim

        original = mt.get_verbatim_store
        mt.get_verbatim_store = AsyncMock(return_value=self._verbatim_store)
        try:
            items = await _list_verbatim("user-A")
        finally:
            mt.get_verbatim_store = original

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["memory_id"], "v1")
        self.assertEqual(items[0]["store"], "verbatim")

    async def test_verbatim_excludes_other_user(self):
        """_list_verbatim for user-B returns empty when ChromaDB returns no matches."""
        import memory.transparency as mt
        from memory.transparency import _list_verbatim

        empty_col = _make_chroma_stub(ids=[])
        store = AsyncMock()
        store._get_collection = AsyncMock(return_value=empty_col)

        original = mt.get_verbatim_store
        mt.get_verbatim_store = AsyncMock(return_value=store)
        try:
            items = await _list_verbatim("user-B")
        finally:
            mt.get_verbatim_store = original

        self.assertEqual(items, [])

    async def test_list_user_memories_aggregates_stores(self):
        """list_user_memories gathers from all 5 stores; partial failures are tolerated."""
        from memory.transparency import list_user_memories

        with (
            patch(
                "memory.transparency._list_verbatim",
                AsyncMock(
                    return_value=[
                        {"memory_id": "v1", "store": "verbatim", "content": "x", "provenance": {}, "timestamp": ""}
                    ]
                ),
            ),
            patch("memory.transparency._list_trajectory", AsyncMock(return_value=[])),
            patch("memory.transparency._list_working_memory", AsyncMock(return_value=[])),
            patch("memory.transparency._list_graph_entities", AsyncMock(return_value=[])),
            patch("memory.transparency._list_rl_patterns", AsyncMock(return_value=[])),
        ):
            items = await list_user_memories("user-A")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["memory_id"], "v1")

    async def test_list_user_memories_store_failure_is_tolerated(self):
        """A failing store does not prevent other stores from being returned."""
        from memory.transparency import list_user_memories

        async def _fail(*_):
            raise RuntimeError("store down")

        with (
            patch("memory.transparency._list_verbatim", _fail),
            patch(
                "memory.transparency._list_trajectory",
                AsyncMock(
                    return_value=[
                        {"memory_id": "t1", "store": "trajectory", "content": "y", "provenance": {}, "timestamp": ""}
                    ]
                ),
            ),
            patch("memory.transparency._list_working_memory", AsyncMock(return_value=[])),
            patch("memory.transparency._list_graph_entities", AsyncMock(return_value=[])),
            patch("memory.transparency._list_rl_patterns", AsyncMock(return_value=[])),
        ):
            items = await list_user_memories("user-A")

        # verbatim failed but trajectory succeeded
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["memory_id"], "t1")


class TestForgetTenantIsolation(unittest.IsolatedAsyncioTestCase):
    """Cross-user delete must be rejected by each store's forget helper."""

    async def test_forget_verbatim_rejects_wrong_user(self):
        """_forget_verbatim must NOT delete a chunk owned by another user (IDOR fix)."""
        import memory.transparency as mt
        from memory.transparency import _forget_verbatim

        collection = _make_chroma_stub(ids=["v1"], metas=[{"user_id": "user-B"}])
        store = AsyncMock()
        store._get_collection = AsyncMock(return_value=collection)

        original = mt.get_verbatim_store
        mt.get_verbatim_store = AsyncMock(return_value=store)
        try:
            result = await _forget_verbatim("user-A", "v1")  # caller A, chunk owned by B
        finally:
            mt.get_verbatim_store = original

        collection.delete.assert_not_called()
        self.assertFalse(result)

    async def test_forget_verbatim_deletes_own_chunk(self):
        """_forget_verbatim deletes a chunk the caller owns."""
        import memory.transparency as mt
        from memory.transparency import _forget_verbatim

        collection = _make_chroma_stub(ids=["v1"], metas=[{"user_id": "user-A"}])
        store = AsyncMock()
        store._get_collection = AsyncMock(return_value=collection)
        original = mt.get_verbatim_store
        mt.get_verbatim_store = AsyncMock(return_value=store)
        try:
            result = await _forget_verbatim("user-A", "v1")
        finally:
            mt.get_verbatim_store = original
        collection.delete.assert_called_once_with(ids=["v1"])
        self.assertTrue(result)

    async def test_forget_working_memory_rejects_wrong_user(self):
        """_forget_working_memory returns False when stored user_id != caller."""
        import memory.transparency as mt
        from memory.transparency import _forget_working_memory

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"user_id": "user-B", "content": "secret"}).encode())

        original = mt.get_async_redis_client
        mt.get_async_redis_client = AsyncMock(return_value=redis_mock)
        try:
            result = await _forget_working_memory("user-A", "autobot:session:s1:memory:k1")
        finally:
            mt.get_async_redis_client = original

        self.assertFalse(result)
        redis_mock.delete.assert_not_called()

    async def test_forget_rl_pattern_rejects_wrong_user(self):
        """_forget_rl_pattern returns False when key belongs to another user."""
        from memory.transparency import _forget_rl_pattern

        # Key belongs to user-B, caller is user-A
        result = await _forget_rl_pattern("user-A", "rag:retrieval_patterns:user-B:abc123")

        self.assertFalse(result)

    async def test_forget_graph_entity_rejects_wrong_user(self):
        """_forget_graph_entity returns False when entity owner != caller."""
        import memory.transparency as mt
        from memory.transparency import _forget_graph_entity

        redis_mock = AsyncMock()
        json_mock = AsyncMock()
        json_mock.get = AsyncMock(return_value={"id": "eid1", "metadata": {"user_id": "user-B"}})
        redis_mock.json = MagicMock(return_value=json_mock)

        original = mt.get_async_redis_client
        mt.get_async_redis_client = AsyncMock(return_value=redis_mock)
        try:
            result = await _forget_graph_entity("user-A", "eid1")
        finally:
            mt.get_async_redis_client = original

        self.assertFalse(result)
        redis_mock.delete.assert_not_called()


class TestForgetEverywhere(unittest.IsolatedAsyncioTestCase):
    """forget_everywhere resolves the owning store instead of guessing (#13739).

    It used to issue the delete against all six stores with the same id. That
    was safe only while every store's id space was structurally distinct;
    #13705 added ``general``, whose ids are dense SQLite rowids, so a numeric
    id from another store landed on an unrelated general row of the same user.
    """

    @staticmethod
    def _listing(*pairs):
        """Patch list_user_memories with the given (memory_id, store) pairs."""

        async def _stub(_user_id):
            return [{"memory_id": mid, "store": store, "content": "", "timestamp": ""} for mid, store in pairs]

        return patch("memory.transparency.list_user_memories", side_effect=_stub)

    async def test_deletes_only_from_the_store_that_holds_the_id(self):
        from memory.transparency import forget_everywhere

        with (
            self._listing(("mem-id-1", "verbatim")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=True)) as mock_forget,
        ):
            results = await forget_everywhere("user-A", "mem-id-1")

        self.assertEqual(mock_forget.call_count, 1)
        self.assertEqual(mock_forget.call_args.args[2], "verbatim")
        self.assertTrue(results["verbatim"])

    async def test_a_numeric_foreign_id_never_reaches_the_general_store(self):
        """The reproduction from #13739: graph entity "6" vs general row 6.

        The general row is unrelated and belongs to the same user, so the owner
        predicate does not protect it — only refusing to guess does.
        """
        from memory.transparency import forget_everywhere

        # Only the graph entity carries this id; general row 6 is a different item.
        with (
            self._listing(("6", "graph"), ("42", "general")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=True)) as mock_forget,
        ):
            results = await forget_everywhere("alice", "6")

        self.assertEqual([c.args[2] for c in mock_forget.call_args_list], ["graph"])
        self.assertFalse(results["general"])
        self.assertTrue(results["graph"])

    async def test_an_id_held_by_two_stores_is_refused_not_guessed(self):
        """Deleting from both is the original bug; picking one is a coin flip."""
        from memory.transparency import AmbiguousMemoryId, forget_everywhere

        with (
            self._listing(("6", "graph"), ("6", "general")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=True)) as mock_forget,
        ):
            with self.assertRaises(AmbiguousMemoryId) as caught:
                await forget_everywhere("alice", "6")

        mock_forget.assert_not_called()
        self.assertEqual(caught.exception.stores, ["general", "graph"])

    async def test_an_unknown_id_deletes_nothing(self):
        from memory.transparency import forget_everywhere

        with (
            self._listing(("other", "verbatim")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=True)) as mock_forget,
        ):
            results = await forget_everywhere("user-A", "mem-id-1")

        mock_forget.assert_not_called()
        self.assertFalse(any(results.values()))

    async def test_every_store_is_still_reported(self):
        """The response shape is unchanged — all six keys, absent ones False."""
        from memory.transparency import MEMORY_STORES, forget_everywhere

        with (
            self._listing(("mem-id-1", "verbatim")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=True)),
        ):
            results = await forget_everywhere("user-A", "mem-id-1")

        self.assertEqual(set(results), set(MEMORY_STORES))
        self.assertEqual(len(MEMORY_STORES), 6)

    async def test_a_failed_delete_is_reported_not_swallowed(self):
        from memory.transparency import forget_everywhere

        with (
            self._listing(("mem-id-1", "graph")),
            patch("memory.transparency.forget_memory", AsyncMock(return_value=False)),
        ):
            results = await forget_everywhere("user-A", "mem-id-1")

        self.assertFalse(results["graph"])


class TestExportUserMemory(unittest.IsolatedAsyncioTestCase):
    """export_user_memory returns a correctly structured payload."""

    async def test_export_schema(self):
        """export_user_memory wraps list_user_memories with export metadata."""
        from memory.transparency import export_user_memory

        fake_items = [
            {"memory_id": "v1", "store": "verbatim", "content": "hello", "provenance": {}, "timestamp": ""},
            {"memory_id": "t1", "store": "trajectory", "content": "world", "provenance": {}, "timestamp": ""},
        ]
        with patch("memory.transparency.list_user_memories", AsyncMock(return_value=fake_items)):
            payload = await export_user_memory("user-A")

        self.assertEqual(payload["export_version"], "1.0")
        self.assertEqual(payload["user_id"], "user-A")
        self.assertEqual(payload["total_items"], 2)
        self.assertIn("exported_at", payload)
        self.assertIn("memories", payload)
        self.assertEqual(len(payload["memories"]), 2)
        self.assertIn("verbatim", payload["stores"])
        self.assertIn("trajectory", payload["stores"])


class TestApiEndpointTenantIsolation(unittest.IsolatedAsyncioTestCase):
    """API endpoint _resolve_target_user enforces tenant isolation."""

    def _make_request(self, role="user"):
        request = MagicMock()
        request.headers = {}
        return request

    async def test_non_admin_cannot_use_target_user_id(self):
        """Non-admin supplying a different target_user_id gets 403."""
        from fastapi import HTTPException

        from api.memory_privacy import _resolve_target_user

        current_user = {"user_id": "user-A", "role": "user"}

        with patch("api.memory_privacy.check_admin_permission", side_effect=HTTPException(status_code=403)):
            with self.assertRaises(HTTPException) as ctx:
                _resolve_target_user(current_user, "user-B", self._make_request())

        self.assertEqual(ctx.exception.status_code, 403)

    async def test_same_user_id_is_always_allowed(self):
        """Passing own user_id as target does not require admin."""
        from api.memory_privacy import _resolve_target_user

        current_user = {"user_id": "user-A", "role": "user"}
        result = _resolve_target_user(current_user, "user-A", self._make_request())
        self.assertEqual(result, "user-A")

    async def test_no_target_user_id_returns_caller(self):
        """Omitting target_user_id returns the caller's own id."""
        from api.memory_privacy import _resolve_target_user

        current_user = {"user_id": "user-A", "role": "user"}
        result = _resolve_target_user(current_user, None, self._make_request())
        self.assertEqual(result, "user-A")

    async def test_admin_can_use_target_user_id(self):
        """An admin may specify another user's id."""
        from api.memory_privacy import _resolve_target_user

        current_user = {"user_id": "admin-1", "role": "admin"}

        with patch("api.memory_privacy.check_admin_permission", return_value=True):
            result = _resolve_target_user(current_user, "user-B", self._make_request())

        self.assertEqual(result, "user-B")


if __name__ == "__main__":
    unittest.main()
