# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""General memory is visible to right-to-be-forgotten and export (#13705).

`memory/transparency.py` (#10554) documents itself as spanning ALL memory
stores, but covered five and not the SQLite general store — so a user's general
memories were un-listable, un-exportable and un-forgettable by the engine that
promises otherwise.

That was defensible until #13688: before it, `memory_entries` had no owner
column, so there was no predicate to select a user's rows by. These pin the
sixth store now that there is one.
"""

from datetime import datetime, timezone

import pytest

from memory.enums import MemoryCategory
from memory.models import MemoryEntry
from memory.storage.general_storage import LEGACY_UNSCOPED_OWNER, GeneralStorage

ALICE = "user-alice"
BOB = "user-bob"


@pytest.fixture
async def storage(tmp_path):
    store = GeneralStorage(tmp_path / "memory.db")
    await store.initialize()
    return store


def _entry(user_id, content):
    return MemoryEntry(
        id=None,
        category=MemoryCategory.FACT,
        content=content,
        metadata={"source": "test"},
        timestamp=datetime.now(tz=timezone.utc),
        user_id=user_id,
    )


class TestListByOwner:
    @pytest.mark.asyncio
    async def test_returns_the_owners_entries_across_categories(self, storage):
        await storage.store(_entry(ALICE, "alice fact"))
        alice_state = _entry(ALICE, "alice state")
        alice_state.category = MemoryCategory.STATE
        await storage.store(alice_state)

        entries = await storage.list_by_owner(ALICE)

        assert {e.content for e in entries} == {"alice fact", "alice state"}

    @pytest.mark.asyncio
    async def test_never_returns_another_owners_entries(self, storage):
        await storage.store(_entry(ALICE, "alice fact"))
        await storage.store(_entry(BOB, "bob fact"))

        entries = await storage.list_by_owner(ALICE)

        assert [e.content for e in entries] == ["alice fact"]

    @pytest.mark.asyncio
    async def test_cannot_be_called_without_an_owner(self, storage):
        with pytest.raises(ValueError):
            await storage.list_by_owner("")


class TestScopedDelete:
    @pytest.mark.asyncio
    async def test_deletes_the_owners_own_entry(self, storage):
        entry_id = await storage.store(_entry(ALICE, "alice fact"))

        assert await storage.delete_for_owner(ALICE, entry_id) is True
        assert await storage.list_by_owner(ALICE) == []

    @pytest.mark.asyncio
    async def test_cannot_delete_another_owners_entry_by_id(self, storage):
        """The headline: knowing the row id must not be enough to erase it."""
        bob_entry_id = await storage.store(_entry(BOB, "bob fact"))

        deleted = await storage.delete_for_owner(ALICE, bob_entry_id)

        assert deleted is False
        assert [e.content for e in await storage.list_by_owner(BOB)] == ["bob fact"]

    @pytest.mark.asyncio
    async def test_a_missing_row_and_a_foreign_row_are_indistinguishable(self, storage):
        bob_entry_id = await storage.store(_entry(BOB, "bob fact"))

        assert await storage.delete_for_owner(ALICE, bob_entry_id) is False
        assert await storage.delete_for_owner(ALICE, 999_999) is False


class TestParkedRowsAreNotAttributed:
    @pytest.mark.asyncio
    async def test_legacy_rows_are_not_listed_for_a_real_user(self, storage):
        """Pre-#13688 rows have no recoverable owner.

        They must not surface in anyone's export, and `forget_everywhere`
        deliberately cannot reach them — their disposition is #13719.
        """
        entry = _entry(LEGACY_UNSCOPED_OWNER, "orphaned row")
        # The reserved owner is rejected on writes, so seed it the way the
        # migration does — as an already-parked row.
        import sqlite3

        with sqlite3.connect(storage.db_path) as conn:
            conn.execute(
                "INSERT INTO memory_entries (category, content, timestamp, user_id) VALUES (?, ?, ?, ?)",
                ("fact", entry.content, entry.timestamp, LEGACY_UNSCOPED_OWNER),
            )

        assert await storage.list_by_owner(ALICE) == []
        assert len(await storage.list_by_owner(LEGACY_UNSCOPED_OWNER)) == 1


class TestTransparencyEngineCoversTheStore:
    def test_general_is_registered_in_every_aggregate(self):
        """AC: list, forget dispatch and forget_everywhere all know the store."""
        import inspect

        from memory import transparency

        assert "_list_general_memory" in inspect.getsource(transparency.list_user_memories)
        assert '"general"' in inspect.getsource(transparency.forget_memory)
        assert '"general"' in inspect.getsource(transparency.forget_everywhere)

    def test_export_inherits_the_store_through_list(self):
        """export_user_memory reuses list_user_memories, so coverage follows."""
        import inspect

        from memory import transparency

        assert "list_user_memories" in inspect.getsource(transparency.export_user_memory)

    def test_the_parked_row_policy_is_documented(self):
        """#13719's decision must be stated, not inferred from a missing branch."""
        from memory import transparency

        assert "__unscoped__" in (transparency.__doc__ or "")
        assert "13719" in (transparency.__doc__ or "")
