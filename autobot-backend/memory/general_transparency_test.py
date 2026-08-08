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


class TestScopeGuardOnDelete:
    @pytest.mark.asyncio
    async def test_a_blank_owner_cannot_delete(self, storage):
        """Pins _require_user_id on the delete path.

        Review found this mutation surviving: removing the guard from
        delete_for_owner left the whole suite green, so the scope check — and
        its whitespace normalisation — was unpinned.
        """
        entry_id = await storage.store(_entry(ALICE, "alice fact"))

        for blank in ("", "   ", None):
            with pytest.raises(ValueError):
                await storage.delete_for_owner(blank, entry_id)

        assert len(await storage.list_by_owner(ALICE)) == 1

    @pytest.mark.asyncio
    async def test_surrounding_whitespace_still_resolves_to_the_owner(self, storage):
        entry_id = await storage.store(_entry(ALICE, "alice fact"))

        assert await storage.delete_for_owner(f"  {ALICE}  ", entry_id) is True

    @pytest.mark.asyncio
    async def test_the_reserved_parked_owner_cannot_delete(self, storage):
        """Reads accept it so an operator can still reach parked rows; the
        transparency engine must not be able to erase them."""
        with pytest.raises(ValueError, match="reserved"):
            await storage.delete_for_owner(LEGACY_UNSCOPED_OWNER, 1)


class TestTransparencyEngineBehaviour:
    """Behavioural, not structural.

    The first version of these asserted on `inspect.getsource` and `__doc__`.
    Review showed why that is worse than nothing: the docstring test passed
    while the prose it pinned was false — parked rows *were* reachable — so the
    suite was certifying an incorrect policy.
    """

    @pytest.mark.asyncio
    async def test_list_user_memories_includes_a_general_row(self, tmp_path, monkeypatch):
        """AC 1, end to end through the public surface."""
        from memory import transparency

        entry = _entry(ALICE, "alice general memory")
        entry.id = 7
        monkeypatch.setattr(transparency, "_list_general_memory", _stub_list([_general_row(entry)]), raising=True)
        for name in (
            "_list_verbatim",
            "_list_trajectory",
            "_list_working_memory",
            "_list_graph_entities",
            "_list_rl_patterns",
        ):
            monkeypatch.setattr(transparency, name, _stub_list([]), raising=True)

        items = await transparency.list_user_memories(ALICE)

        assert [i["store"] for i in items] == ["general"]
        assert items[0]["content"] == "alice general memory"

    @pytest.mark.asyncio
    async def test_export_includes_the_general_store(self, monkeypatch):
        """AC 4 — export inherits the store through list_user_memories."""
        from memory import transparency

        entry = _entry(ALICE, "exported memory")
        entry.id = 8
        monkeypatch.setattr(transparency, "_list_general_memory", _stub_list([_general_row(entry)]), raising=True)
        for name in (
            "_list_verbatim",
            "_list_trajectory",
            "_list_working_memory",
            "_list_graph_entities",
            "_list_rl_patterns",
        ):
            monkeypatch.setattr(transparency, name, _stub_list([]), raising=True)

        export = await transparency.export_user_memory(ALICE)

        assert "general" in export["stores"]
        assert export["total_items"] == 1

    @pytest.mark.asyncio
    async def test_parked_rows_are_refused_as_a_user_footprint(self):
        """The policy the old docstring test only claimed.

        `list_by_owner(LEGACY_UNSCOPED_OWNER)` still works at the storage layer —
        that is #13688's design so an operator can reach parked rows. What must
        not happen is surfacing them through the user-facing engine.
        """
        from memory.transparency import _list_general_memory

        assert await _list_general_memory(LEGACY_UNSCOPED_OWNER) == []

    @pytest.mark.asyncio
    async def test_a_foreign_store_id_never_deletes_a_general_row(self):
        """Cross-store collision: forget_everywhere fans one id to all stores.

        A graph entity id or Redis key must not coerce onto a general row id.
        """
        from memory.transparency import _forget_general_memory

        for foreign in ("abc", "autobot:session:x:memory:y", " 2 ", "+3", "0004", "5\n", "1_0", ""):
            assert await _forget_general_memory(ALICE, foreign) is False, foreign


def _general_row(entry):
    from memory.transparency import _general_item

    return _general_item(entry)


def _stub_list(items):
    async def _stub(_user_id):
        return items

    return _stub
