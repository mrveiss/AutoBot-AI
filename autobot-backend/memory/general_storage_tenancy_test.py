# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenant scoping on the general memory data plane (#13688).

Before this, ``store_memory``/``retrieve_memories``/``search_memories`` took no
owner argument at all, and ``search_memories(query)`` returned whatever the
storage layer matched — every owner's rows. Tenancy was enforced only in the
layers above (``memory/transparency.py``, the working-memory key allowlist), so
isolation depended on every call site remembering to filter.

These tests hold the shape: the filter lives in the storage layer, the scope is
a required argument, and no query can be constructed without one.
"""

import sqlite3
from datetime import datetime, timezone

import pytest

from memory.enums import MemoryCategory
from memory.manager import MemoryManager
from memory.models import MemoryEntry
from memory.storage.general_storage import LEGACY_UNSCOPED_OWNER, GeneralStorage

ALICE = "user-alice"
BOB = "user-bob"


@pytest.fixture
async def storage(tmp_path):
    store = GeneralStorage(tmp_path / "memory.db")
    await store.initialize()
    return store


@pytest.fixture
async def manager(tmp_path):
    mgr = MemoryManager(db_path=str(tmp_path / "unified.db"), enable_cache=False)
    await mgr._ensure_initialized()
    return mgr


def _entry(user_id, content="a private note", category=MemoryCategory.FACT):
    return MemoryEntry(
        id=None,
        category=category,
        content=content,
        metadata={"secret": content},
        timestamp=datetime.now(tz=timezone.utc),
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# The filter lives in the storage layer
# ---------------------------------------------------------------------------


class TestStorageLayerIsolation:
    @pytest.mark.asyncio
    async def test_search_cannot_return_another_owners_entry(self, storage):
        """The #13688 headline: search was unfiltered and returned everyone's rows."""
        await storage.store(_entry(ALICE, "alice deployment key"))
        await storage.store(_entry(BOB, "bob deployment key"))

        results = await storage.search(ALICE, "deployment key")

        assert len(results) == 1
        assert results[0].user_id == ALICE
        assert "bob" not in results[0].content

    @pytest.mark.asyncio
    async def test_search_matching_metadata_still_cannot_cross_owners(self, storage):
        """The owner predicate brackets the content-OR-metadata match."""
        await storage.store(_entry(BOB, "bob secret"))

        assert await storage.search(ALICE, "bob secret") == []

    @pytest.mark.asyncio
    async def test_retrieve_cannot_return_another_owners_entry(self, storage):
        await storage.store(_entry(ALICE, "alice fact"))
        await storage.store(_entry(BOB, "bob fact"))

        results = await storage.retrieve(ALICE, MemoryCategory.FACT, {"limit": 100})

        assert [r.user_id for r in results] == [ALICE]

    @pytest.mark.asyncio
    async def test_query_without_a_scope_cannot_be_constructed(self, storage):
        """A blank or missing scope is a ValueError/TypeError, never a full-tenant query."""
        for blank in ("", "   ", None):
            with pytest.raises(ValueError):
                await storage.search(blank, "anything")
            with pytest.raises(ValueError):
                await storage.retrieve(blank, MemoryCategory.FACT, {"limit": 10})

        with pytest.raises(TypeError):
            await storage.search("only-a-query")  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_write_without_a_scope_is_rejected(self, storage):
        with pytest.raises(ValueError):
            await storage.store(_entry(None))
        with pytest.raises(ValueError):
            await storage.store(_entry("  "))


# ---------------------------------------------------------------------------
# The scope is a first-class column, not metadata
# ---------------------------------------------------------------------------


class TestScopeIsFirstClass:
    @pytest.mark.asyncio
    async def test_user_id_is_a_column_not_a_metadata_key(self, storage, tmp_path):
        await storage.store(_entry(ALICE, "alice fact"))

        with sqlite3.connect(tmp_path / "memory.db") as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_entries)")}
            stored_user, stored_meta = conn.execute("SELECT user_id, metadata_json FROM memory_entries").fetchone()

        assert "user_id" in columns
        assert stored_user == ALICE
        assert "user-alice" not in (stored_meta or "")

    @pytest.mark.asyncio
    async def test_round_trip_preserves_the_owner(self, storage):
        await storage.store(_entry(ALICE, "alice fact"))
        [entry] = await storage.retrieve(ALICE, MemoryCategory.FACT, {"limit": 10})
        assert entry.user_id == ALICE


# ---------------------------------------------------------------------------
# Pre-#13688 databases keep their rows
# ---------------------------------------------------------------------------


class TestLegacyDatabaseMigration:
    @pytest.mark.asyncio
    async def test_existing_rows_survive_and_are_parked_not_leaked(self, tmp_path):
        """No data loss: legacy rows are preserved under a reserved owner.

        They must not surface for a real user, and must not be deleted.
        """
        db = tmp_path / "legacy.db"
        with sqlite3.connect(db) as conn:
            conn.execute("""
                CREATE TABLE memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    reference_path TEXT,
                    embedding BLOB
                )
            """)
            conn.execute(
                "INSERT INTO memory_entries (category, content, timestamp) VALUES (?, ?, ?)",
                ("fact", "pre-existing row", datetime.now(tz=timezone.utc)),
            )

        storage = GeneralStorage(db)
        await storage.initialize()

        assert await storage.search(ALICE, "pre-existing") == []
        parked = await storage.search(LEGACY_UNSCOPED_OWNER, "pre-existing")
        assert len(parked) == 1
        assert parked[0].content == "pre-existing row"

    @pytest.mark.asyncio
    async def test_migration_is_idempotent(self, tmp_path):
        storage = GeneralStorage(tmp_path / "twice.db")
        await storage.initialize()
        await storage.store(_entry(ALICE, "alice fact"))
        await storage.initialize()

        assert len(await storage.search(ALICE, "alice fact")) == 1


# ---------------------------------------------------------------------------
# The manager API requires the scope
# ---------------------------------------------------------------------------


class TestManagerApiRequiresScope:
    @pytest.mark.asyncio
    async def test_search_memories_is_owner_scoped(self, manager):
        await manager.store_memory(MemoryCategory.FACT, "alice note", user_id=ALICE)
        await manager.store_memory(MemoryCategory.FACT, "bob note", user_id=BOB)

        assert [e.user_id for e in await manager.search_memories("note", user_id=ALICE)] == [ALICE]

    @pytest.mark.asyncio
    async def test_retrieve_memories_is_owner_scoped(self, manager):
        await manager.store_memory(MemoryCategory.FACT, "alice note", user_id=ALICE)
        await manager.store_memory(MemoryCategory.FACT, "bob note", user_id=BOB)

        results = await manager.retrieve_memories(MemoryCategory.FACT, user_id=BOB, limit=100)

        assert [e.user_id for e in results] == [BOB]

    @pytest.mark.asyncio
    async def test_omitting_the_scope_is_a_type_error(self, manager):
        """AC: omitting the scope is a TypeError, not a silent full-tenant query."""
        with pytest.raises(TypeError):
            await manager.store_memory(MemoryCategory.FACT, "unowned")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            await manager.retrieve_memories(MemoryCategory.FACT)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            await manager.search_memories("anything")  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_blank_scope_is_a_value_error(self, manager):
        with pytest.raises(ValueError):
            await manager.store_memory(MemoryCategory.FACT, "unowned", user_id="")
        with pytest.raises(ValueError):
            await manager.search_memories("anything", user_id="   ")

    @pytest.mark.asyncio
    async def test_correctly_scoped_caller_sees_no_behaviour_change(self, manager):
        """AC: no behaviour change for a correctly-scoped caller."""
        entry_id = await manager.store_memory(
            MemoryCategory.FACT,
            "AutoBot supports multi-modal AI",
            user_id=ALICE,
            metadata={"source": "documentation"},
        )
        assert isinstance(entry_id, int)

        [entry] = await manager.retrieve_memories(MemoryCategory.FACT, user_id=ALICE, limit=10)
        assert entry.content == "AutoBot supports multi-modal AI"
        assert entry.metadata == {"source": "documentation"}


# ---------------------------------------------------------------------------
# Review findings on PR #13698
# ---------------------------------------------------------------------------


class TestReservedOwnerCannotBeWritten:
    @pytest.mark.asyncio
    async def test_legacy_owner_is_rejected_as_a_write_scope(self, storage):
        """Writing under the reserved id would re-create the unscoped bucket."""
        with pytest.raises(ValueError, match="reserved"):
            await storage.store(_entry(LEGACY_UNSCOPED_OWNER))

    @pytest.mark.asyncio
    async def test_legacy_owner_is_still_readable(self, storage):
        """Reads must keep accepting it or parked rows become unreachable."""
        assert await storage.search(LEGACY_UNSCOPED_OWNER, "anything") == []


class TestScopeNormalisation:
    @pytest.mark.asyncio
    async def test_surrounding_whitespace_does_not_split_a_tenant(self, storage):
        await storage.store(_entry(f"  {ALICE}  ", "alice note"))

        assert len(await storage.search(ALICE, "alice note")) == 1
        [entry] = await storage.retrieve(ALICE, MemoryCategory.FACT, {"limit": 10})
        assert entry.user_id == ALICE


class TestConcurrentMigration:
    @pytest.mark.asyncio
    async def test_two_initializers_racing_on_a_legacy_db_both_succeed(self, tmp_path):
        """A second worker must not die on 'duplicate column name' at startup.

        PRAGMA and ALTER are not one transaction and the asyncio lock guards
        only one process, so the loser has to treat the column already existing
        as success.
        """
        import asyncio

        db = tmp_path / "legacy_race.db"
        with sqlite3.connect(db) as conn:
            conn.execute("""
                CREATE TABLE memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    reference_path TEXT,
                    embedding BLOB
                )
            """)
            conn.execute(
                "INSERT INTO memory_entries (category, content, timestamp) VALUES (?, ?, ?)",
                ("fact", "pre-existing row", datetime.now(tz=timezone.utc)),
            )

        results = await asyncio.gather(
            *[GeneralStorage(db).initialize() for _ in range(6)],
            return_exceptions=True,
        )

        failures = [r for r in results if isinstance(r, Exception)]
        assert not failures, f"concurrent initialize must not raise: {failures}"

        parked = await GeneralStorage(db).search(LEGACY_UNSCOPED_OWNER, "pre-existing")
        assert len(parked) == 1


class TestRetentionDoesNotEatParkedRows:
    @pytest.mark.asyncio
    async def test_cleanup_old_exempts_pre_migration_rows(self, tmp_path):
        """The migration preserves legacy rows; the first sweep must not undo that."""
        db = tmp_path / "legacy_retention.db"
        with sqlite3.connect(db) as conn:
            conn.execute("""
                CREATE TABLE memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp TIMESTAMP NOT NULL,
                    reference_path TEXT,
                    embedding BLOB
                )
            """)
            conn.execute(
                "INSERT INTO memory_entries (category, content, timestamp) VALUES (?, ?, ?)",
                ("fact", "pre-existing row", datetime(2020, 1, 1, tzinfo=timezone.utc)),
            )

        storage = GeneralStorage(db)
        await storage.initialize()
        await storage.store(_entry(ALICE, "recent alice row"))

        deleted = await storage.cleanup_old(0)

        assert deleted == 1, "the owned row expires; the parked one must not"
        parked = await storage.search(LEGACY_UNSCOPED_OWNER, "pre-existing")
        assert len(parked) == 1
