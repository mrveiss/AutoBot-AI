# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ownerless-document visibility backfill (#16693).

It selects, changes and reports as the owner decided on #16693, and it never touches a
fact that has an owner. One test drives the real ``update_fact`` path, so the row, the
Redis projection, ChromaDB and ``kb:system:facts`` are all seen to change together.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from knowledge.facts import FactsMixin
from knowledge.ingestion_visibility import BACKFILL_MARK
from knowledge.ownership import KnowledgeOwnership

_DOC = {"source": "autobot_docs_population", "category": "guides"}
_DIARY = {"category": "AGENT_DIARY", "source": "planner", "source_type": "manual_upload"}
_CANDIDATES = ("owner_id IS NULL", "no visibility")  # stands in for the SQL clauses


class _Backfill(FactsMixin):
    """The backfill with its collaborators stubbed: the copy update_fact reads, and update_fact."""

    def __init__(self, copies):
        self._read_fact_for_write = AsyncMock(side_effect=copies.get)
        self.update_fact = AsyncMock(return_value={"status": "success"})


async def _run(kb, *rows):
    """Run the backfill over *rows* (``(fact_id, metadata)`` pairs); returns ``(report, walk)``."""
    walk = {}

    async def iter_facts(batch_size=500, *, where=()):
        walk["where"] = where
        yield [{"fact_id": fid, "content": "c", "metadata": dict(meta)} for fid, meta in rows]

    with (
        patch("knowledge.fact_store.backfill_candidates", return_value=_CANDIDATES),
        patch("knowledge.fact_store.count_facts", AsyncMock(return_value=len(rows))) as count,
        patch("knowledge.fact_store.iter_facts", iter_facts),
        patch("knowledge.fact_store.clear_backfill_candidates", AsyncMock()) as clear,
    ):
        report = await kb.backfill_document_visibility()
    walk["counted"] = count.await_args.args
    walk["cleared"] = [fid for call in clear.await_args_list for fid in call.args[0]]
    return report, walk


@pytest.mark.asyncio
async def test_an_ownerless_document_is_made_system_through_update_fact():
    kb = _Backfill({"f1": ({}, dict(_DOC))})
    report, walk = await _run(kb, ("f1", _DOC))
    kb.update_fact.assert_awaited_once_with("f1", metadata=BACKFILL_MARK)
    assert (report["found"], report["updated"]) == (1, {"documentation": 1})
    # counted and walked on the same rows, and decided for good
    assert walk == {"where": _CANDIDATES, "counted": _CANDIDATES, "cleared": ["f1"]}


@pytest.mark.asyncio
async def test_every_other_ownerless_fact_stays_private_and_is_counted_by_provenance():
    kb = _Backfill({"f2": ({}, dict(_DIARY))})
    report, walk = await _run(kb, ("f2", _DIARY))
    kb.update_fact.assert_not_awaited()
    assert report["kept_private"] == {"manual_upload/AGENT_DIARY": 1}
    assert walk["cleared"] == ["f2"]  # decided: a later start doesn't walk it again


@pytest.mark.asyncio
async def test_a_fact_whose_live_copy_has_an_owner_is_never_touched():
    """update_fact merges onto the copy it reads; the row alone can't license the change."""
    kb = _Backfill({"f3": ({}, {**_DOC, "owner_id": "u1"})})
    report, walk = await _run(kb, ("f3", _DOC))
    kb.update_fact.assert_not_awaited()
    assert report["skipped"] == {"documentation": 1}
    assert walk["cleared"] == ["f3"]


@pytest.mark.asyncio
async def test_a_failed_update_is_reported_and_kept_for_the_next_start():
    kb = _Backfill({"f4": ({}, dict(_DOC))})
    kb.update_fact.return_value = {"status": "error"}
    report, walk = await _run(kb, ("f4", _DOC))
    assert report["failed"] == {"documentation": 1}
    assert report["updated"] == {}
    assert walk["cleared"] == []  # still flagged, so the next start retries it


def test_candidates_are_flagged_by_the_migration_and_still_unowned_and_unset():
    """No write path sets the flag, so a fact stored after deploy can never be promoted."""
    from knowledge.fact_store import backfill_candidates
    from models.knowledge_fact import KnowledgeFact

    sql = [str(clause.compile(dialect=postgresql.dialect())) for clause in backfill_candidates()]
    assert sql[0] == "knowledge_facts.visibility_backfill_candidate IS true"
    assert sql[1] == "knowledge_facts.owner_id IS NULL"
    assert "->>" in sql[2] and sql[2].endswith(") IS NULL")  # no visibility: absent, or JSON null
    assert "visibility_backfill_candidate" in KnowledgeFact.__table__.columns
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260914_092_kb_visibility_backfill_candidates.py"
    ).read_text(encoding="utf-8")
    # a structural marker, so baseline adoption observes the revision instead of re-running it
    assert 'op.add_column("knowledge_facts", sa.Column("visibility_backfill_candidate"' in migration


class _SetStore:
    """The Redis set commands the ownership indexes use."""

    def __init__(self):
        self.sets: dict[str, set] = defaultdict(set)

    def sadd(self, key, *members):
        self.sets[key].update(members)

    def srem(self, key, *members):
        self.sets[key].difference_update(members)


class _KB(FactsMixin):
    """A FactsMixin host whose update_fact runs for real over an ownerless document."""

    def __init__(self, metadata, index_store):
        self.ensure_initialized = MagicMock()
        self.redis_client = MagicMock()
        self.redis_client.exists.return_value = True
        self.redis_client.hgetall.return_value = {
            b"content": b"doc text",
            b"metadata": json.dumps(metadata).encode("utf-8"),
            b"timestamp": b"2026-01-01T00:00:00+00:00",
        }
        self.vector_store = MagicMock()
        self.ownership_manager = KnowledgeOwnership(index_store)


@pytest.mark.asyncio
async def test_the_backfill_write_reaches_the_row_redis_chromadb_and_the_system_index():
    store = _SetStore()
    kb = _KB(dict(_DOC), store)
    with patch("knowledge.fact_store.update_fact", new=AsyncMock(return_value=True)) as row_write:
        assert (await kb.update_fact("f1", metadata=dict(BACKFILL_MARK)))["status"] == "success"

    assert row_write.await_args.args[2]["visibility"] == "system"  # the durable row
    projected = json.loads(kb.redis_client.hset.call_args.kwargs["mapping"]["metadata"])
    assert projected["visibility_backfill"] == "16693"  # the Redis projection
    assert kb.vector_store._collection.update.call_args.kwargs["metadatas"][0]["visibility"] == "system"
    assert store.sets["kb:system:facts"] == {"f1"}  # every signed-in user reads this index


@pytest.mark.asyncio
async def test_a_new_ownerless_system_fact_is_projected_into_the_system_index():
    """New ingestion writes SYSTEM on what nobody owns; its projection must file it where users read."""
    store = _SetStore()
    kb = _KB({}, store)
    await kb._project_fact_to_redis("f9", "doc text", {**_DOC, "visibility": "system"})
    assert store.sets["kb:system:facts"] == {"f9"}


@pytest.mark.asyncio
async def test_a_new_ownerless_private_fact_is_filed_nowhere():
    store = _SetStore()
    kb = _KB({}, store)
    await kb._project_fact_to_redis("f8", "diary", dict(_DIARY))
    assert not any(store.sets.values())


@pytest.mark.asyncio
async def test_the_backfill_runs_after_legacy_adoption():
    """It walks the durable rows, so Redis-only facts must be adopted first."""
    from knowledge_factory import _adopt_then_backfill

    order = []
    kb = MagicMock()
    kb.adopt_legacy_facts = AsyncMock(side_effect=lambda: order.append("adopt"))
    kb.backfill_document_visibility = AsyncMock(side_effect=lambda: order.append("backfill"))
    await _adopt_then_backfill(kb)
    assert order == ["adopt", "backfill"]
