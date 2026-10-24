# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-importing the system-knowledge templates never inserts a second copy of a fact (#18577).

The librarian's document bodies embed a timestamp, so the KB's content-hash dedup cannot match a
re-import. The managers therefore store every template item under a stable id, and a repeat import
updates the existing fact. This runs the REAL template tree through the REAL manager and librarian
against an in-memory KB.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from agents.kb_librarian.librarian import KBLibrarian
from agents.kb_librarian.stable_ids import IMPORT_HASH_FIELD, SystemFactIds, system_fact_id, text_digest
from agents.system_knowledge_manager import SystemKnowledgeManager
from autobot_shared.paths import project_root
from autobot_shared.system_knowledge_paths import system_knowledge_templates_dir


class _FakeKB:
    def __init__(self) -> None:
        self.facts: dict[str, str] = {}
        self.meta: dict[str, dict] = {}
        self.stored = 0
        self.updated = 0
        self.fail = False  # every write reports an error
        self.dup_type = None  # type of the fact a duplicate answer points at (default: the item's own)
        self.dup_link = None  # system_fact_id the duplicate target already carries
        self.duplicate = False  # store_fact answers "duplicate" of a pre-existing fact (semantic match)
        self.dup_meta: dict = {}  # extra metadata (owner, visibility) the duplicate target carries (#19296)

    @property
    def writes(self) -> int:
        return self.stored + self.updated

    def get_fact(self, fact_id):
        return {"id": fact_id, "metadata": self.meta.get(fact_id, {})} if fact_id in self.facts else None

    async def store_fact(self, content, metadata=None, fact_id=None):
        if self.fail:
            return {"status": "error", "message": "Knowledge operation failed"}
        if self.duplicate:
            dup_id = f"dup-{len(self.facts)}"
            self.facts[dup_id] = content + " (near copy)"
            self.meta[dup_id] = {"source": "web_research", "type": self.dup_type or metadata["type"], **self.dup_meta}
            if self.dup_link:
                self.meta[dup_id]["system_fact_id"] = self.dup_link
            return {"status": "duplicate", "fact_id": dup_id, "message": "Near-duplicate fact already exists"}
        self.stored += 1
        # Mirrors the real store: no stable id means a fresh random one every call.
        fid = fact_id or f"random-{self.stored}"
        self.facts[fid] = content
        self.meta[fid] = dict(metadata or {})
        return {"status": "success"}

    async def update_fact(self, fact_id, content=None, metadata=None):
        if self.fail or fact_id not in self.meta:
            return {"status": "error", "message": "Fact not found"}
        self.updated += 1
        if content is not None:
            self.facts[fact_id] = content
        self.meta[fact_id] = {**self.meta.get(fact_id, {}), **(metadata or {})}  # the real update merges
        return {"status": "success"}


def _batches_of(kb: _FakeKB):
    """The durable-store view of the fake KB: what ``fact_store.iter_facts`` would yield."""

    async def _gen():
        yield [
            {"fact_id": fid, "content": c, "metadata": kb.meta[fid]} for fid, c in kb.facts.items() if fid in kb.meta
        ]

    return _gen


def _manager(kb: _FakeKB, tmp_path) -> SystemKnowledgeManager:
    manager = object.__new__(SystemKnowledgeManager)
    manager.knowledge_base = kb
    manager.librarian = KBLibrarian.__new__(KBLibrarian)
    manager.librarian.knowledge_base = kb
    manager.system_knowledge_dir = system_knowledge_templates_dir()
    manager.fact_ids = SystemFactIds(_batches_of(kb))
    manager.runtime_knowledge_dir = tmp_path / "runtime"
    manager.backup_dir = tmp_path / "backup"
    manager._import_failures = []
    manager._import_unresolved = []
    return manager


@pytest.mark.asyncio
async def test_second_import_of_the_real_templates_adds_no_fact(tmp_path) -> None:
    kb = _FakeKB()
    manager = _manager(kb, tmp_path)
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        assert await manager._import_system_knowledge() == 0
        first = dict.fromkeys(kb.facts)
        assert first, "the template tree imported nothing"
        writes = kb.writes
        assert await manager._import_system_knowledge() == 0
    assert set(kb.facts) == set(first), "a re-import created new facts"
    assert kb.writes == writes, "an unchanged second run wrote (store/update) again"


def test_the_template_tree_is_the_tracked_resources_dir() -> None:
    assert system_knowledge_templates_dir() == project_root() / "autobot-backend" / "resources" / "knowledge"
    assert (system_knowledge_templates_dir() / "tools").is_dir()


def test_every_template_loads_as_a_mapping() -> None:
    """A comment-only stub (loads as ``None``) would crash or pollute the importers (#18577)."""
    for path in system_knowledge_templates_dir().rglob("*.yaml"):
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict), path


def test_system_fact_id_is_stable_and_kind_scoped() -> None:
    assert system_fact_id("tool", "nmap") == system_fact_id("tool", "nmap")
    assert system_fact_id("tool", "nmap") != system_fact_id("workflow", "nmap")


async def _import(kb: _FakeKB, tmp_path) -> int:
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        return await _manager(kb, tmp_path)._import_system_knowledge()


@pytest.mark.asyncio
async def test_a_fresh_install_tags_every_fact_system_knowledge(tmp_path) -> None:
    kb = _FakeKB()
    await _import(kb, tmp_path)
    assert kb.meta
    assert {m["source"] for m in kb.meta.values()} == {"system_knowledge"}
    assert all(fid == m["system_fact_id"] for fid, m in kb.meta.items())


async def _seeded(tmp_path, legacy_meta: dict) -> tuple[_FakeKB, str, int]:
    """A node holding one random-id fact for a real template tool, with ``legacy_meta`` merged in."""
    clean = _FakeKB()
    await _import(clean, tmp_path)
    tool = next(m["tool_name"] for m in clean.meta.values() if m["type"] == "tool_documentation")
    node = _FakeKB()
    node.facts = {"legacy-tool": "RESEARCHED TEXT"}
    node.meta = {
        "legacy-tool": {"type": "tool_documentation", "tool_name": tool, "source": "web_research", **legacy_meta}
    }
    await _import(node, tmp_path)
    return node, tool, len(clean.facts)


@pytest.mark.asyncio
async def test_an_adopted_legacy_fact_keeps_its_text_and_gains_the_link(tmp_path) -> None:
    node, tool, clean_count = await _seeded(tmp_path, {})
    holders = [f for f, m in node.meta.items() if m.get("tool_name") == tool]
    assert holders == ["legacy-tool"], "the tool was stored a second time"
    assert node.facts["legacy-tool"] == "RESEARCHED TEXT", "researched text was overwritten"
    assert node.meta["legacy-tool"]["source"] == "web_research", "the legacy source was rewritten"
    assert node.meta["legacy-tool"]["system_fact_id"] == system_fact_id("tool", tool)
    assert len(node.facts) == clean_count, "an existing-node import changed the fact count"
    await _import(node, tmp_path)  # and it stays one, unchanged, on the next run
    assert len(node.facts) == clean_count
    assert node.facts["legacy-tool"] == "RESEARCHED TEXT"


async def _owned_seed(tmp_path, recorded_for: str) -> tuple[_FakeKB, str]:
    """An owned fact (``source=system_knowledge``) holding "RESEARCHED TEXT", whose recorded import hash is that of ``recorded_for``."""
    node, tool, _ = await _seeded(
        tmp_path,
        {"source": "system_knowledge", IMPORT_HASH_FIELD: text_digest(recorded_for), "system_template_hash": "old"},
    )
    return node, tool


@pytest.mark.asyncio
async def test_an_owned_unedited_fact_is_refreshed_through_update_not_store(tmp_path) -> None:
    node, tool = await _owned_seed(tmp_path, recorded_for="RESEARCHED TEXT")
    assert node.facts["legacy-tool"] != "RESEARCHED TEXT", "an unedited owned fact kept a stale body"
    assert node.meta["legacy-tool"][IMPORT_HASH_FIELD] == text_digest(node.facts["legacy-tool"])
    # The other template items are new on this node (stored); the found one must go through update_fact.
    assert node.updated == 1, "update_fact must be used when the id was found (store_fact replaces every column)"
    assert [f for f, m in node.meta.items() if m.get("tool_name") == tool] == ["legacy-tool"]


@pytest.mark.asyncio
async def test_a_user_edited_owned_fact_keeps_the_edit_and_gains_the_link(tmp_path) -> None:
    node, tool = await _owned_seed(tmp_path, recorded_for="WHAT THE IMPORT WROTE")
    assert node.facts["legacy-tool"] == "RESEARCHED TEXT", "the import overwrote a user edit"
    assert node.meta["legacy-tool"]["system_fact_id"] == system_fact_id("tool", tool)


@pytest.mark.asyncio
async def test_a_failed_store_is_counted_and_retried(tmp_path) -> None:
    kb = _FakeKB()
    kb.fail = True
    assert await _import(kb, tmp_path) > 0, "failed writes were reported as imported"
    assert not kb.facts
    kb.fail = False
    assert await _import(kb, tmp_path) == 0 and kb.facts, "the failed items were not retried"


@pytest.mark.asyncio
async def test_a_failed_import_does_not_refresh_the_file_state_cache(tmp_path) -> None:
    kb = _FakeKB()
    kb.fail = True
    manager = _manager(kb, tmp_path)
    manager._check_system_knowledge_changes = AsyncMock(return_value=(True, ["x"]))
    manager._update_system_knowledge_cache = AsyncMock()
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        await manager.initialize_system_knowledge()
    manager._update_system_knowledge_cache.assert_not_awaited()


def _tree_state(root) -> dict:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.mark.asyncio
async def test_the_import_writes_nothing_under_the_templates_dir(tmp_path) -> None:
    before = _tree_state(system_knowledge_templates_dir())
    await _import(_FakeKB(), tmp_path)
    assert _tree_state(system_knowledge_templates_dir()) == before
    assert (tmp_path / "runtime" / "tools").is_dir(), "the runtime copies were not written"


@pytest.mark.asyncio
async def test_missing_templates_generate_defaults_into_the_runtime_dir_only(tmp_path) -> None:
    manager = _manager(_FakeKB(), tmp_path)
    manager.system_knowledge_dir = tmp_path / "no-templates"
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        await manager._import_system_knowledge()
    assert not manager.system_knowledge_dir.exists(), "defaults were generated into the template location"
    assert (tmp_path / "runtime" / "tools" / "steganography.yaml").is_file()


@pytest.mark.asyncio
async def test_an_operator_edited_runtime_copy_is_kept(tmp_path) -> None:
    await _import(_FakeKB(), tmp_path)
    edited = sorted((tmp_path / "runtime" / "tools").glob("*.yaml"))[0]
    await asyncio.to_thread(edited.write_text, "# operator edit\n", encoding="utf-8")
    await _import(_FakeKB(), tmp_path)
    kept = await asyncio.to_thread(edited.read_text, encoding="utf-8")
    assert kept == "# operator edit\n", "an edited runtime copy was replaced"


@pytest.mark.asyncio
async def test_a_duplicate_answer_is_an_existing_fact_linked_not_an_error(tmp_path) -> None:
    kb = _FakeKB()
    kb.duplicate = True
    manager = _manager(kb, tmp_path)
    manager._check_system_knowledge_changes = AsyncMock(return_value=(True, ["x"]))
    manager._update_system_knowledge_cache = AsyncMock()
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        await manager.initialize_system_knowledge()
        manager._update_system_knowledge_cache.assert_awaited_once()  # no failure: the cache is written
        assert manager._import_failures == []
        assert all(m.get("system_fact_id") for f, m in kb.meta.items() if f.startswith("dup-")), "duplicate not linked"
        names = [m for f, m in kb.meta.items() if f.startswith("dup-")]
        assert all(
            ("tool_name" in m) or ("workflow_name" in m) or ("title" in m) for m in names
        ), "absent name not filled"
        writes = kb.writes
        assert await manager._import_system_knowledge() == 0
    assert kb.writes == writes, "the second run wrote again"


@pytest.mark.asyncio
async def test_an_owned_fact_without_an_import_hash_is_only_linked(tmp_path) -> None:
    node, tool, _ = await _seeded(tmp_path, {"source": "system_knowledge"})
    assert node.facts["legacy-tool"] == "RESEARCHED TEXT", "an unverifiable owned fact was rewritten"
    assert node.meta["legacy-tool"]["system_fact_id"] == system_fact_id("tool", tool)
    assert IMPORT_HASH_FIELD not in node.meta["legacy-tool"]


@pytest.mark.asyncio
async def test_the_second_run_over_an_adopted_legacy_fact_makes_zero_writes(tmp_path) -> None:
    node, _, _ = await _seeded(tmp_path, {})
    writes = node.writes
    assert await _import(node, tmp_path) == 0
    assert node.writes == writes


@pytest.mark.asyncio
async def test_a_duplicate_of_another_kind_keeps_its_type_and_name_and_gains_only_the_link(tmp_path) -> None:
    kb = _FakeKB()
    kb.duplicate = True
    kb.dup_type = "user_note"
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        await _manager(kb, tmp_path)._import_system_knowledge()
    dups = {f: m for f, m in kb.meta.items() if f.startswith("dup-")}
    assert dups and all(m["type"] == "user_note" for m in dups.values()), "a foreign fact was re-typed"
    assert all(m["system_fact_id"] for m in dups.values())
    assert not any(k.endswith("_name") or k == "title" for m in dups.values() for k in m), "a name was written"


@pytest.mark.asyncio
async def test_a_duplicate_linked_to_another_item_is_reported_unresolved_and_never_written(tmp_path) -> None:
    kb = _FakeKB()
    kb.duplicate = True
    kb.dup_link = "someone-elses-stable-id"
    manager = _manager(kb, tmp_path)
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        assert await manager._import_system_knowledge() == 0, "unresolved must not be a retry-causing failure"
        assert manager._import_unresolved, "the unresolved items were not reported"
        assert kb.writes == 0
        assert all(m["system_fact_id"] == "someone-elses-stable-id" for f, m in kb.meta.items() if f.startswith("dup-"))
        assert await manager._import_system_knowledge() == 0
    assert kb.writes == 0, "a second run flip-flopped the link"


async def _import_twice_against(dup_meta: dict, tmp_path) -> tuple[_FakeKB, SystemKnowledgeManager, int]:
    """Two imports whose every store is a semantic duplicate of a fact carrying *dup_meta* (#19296)."""
    kb = _FakeKB()
    kb.duplicate = True
    kb.dup_meta = dup_meta
    manager = _manager(kb, tmp_path)
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        assert await manager._import_system_knowledge() == 0, "unresolved must not be a retry-causing failure"
        first = kb.writes
        assert await manager._import_system_knowledge() == 0
    return kb, manager, first


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "held_by",
    [
        {"owner_id": "u42"},
        {"user_id": "u42", "visibility": "system"},
        {"visibility": "private"},
        {"visibility": " Organization ", "organization_id": "org-7"},
        {"visibility": "group", "group_ids": ["g1"]},
        {"shared_with": ["u42"]},
        # CodeRabbit on #19309: an explicit narrow access level with no visibility is someone's data too.
        {"access_level": "private"},
        {"access_level": " Owner "},
    ],
)
async def test_a_duplicate_a_principal_holds_is_never_written_and_reported_unresolved(held_by, tmp_path) -> None:
    kb, manager, first = await _import_twice_against(held_by, tmp_path)
    assert first == 0 and kb.writes == 0, "the system import wrote into a fact a principal holds"
    assert manager._import_unresolved, "the held duplicates were not reported unresolved"
    assert not any("system_fact_id" in m for f, m in kb.meta.items() if f.startswith("dup-"))


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [{}, {"visibility": "system"}, {"visibility": "PUBLIC"}])
async def test_an_ownerless_or_system_duplicate_is_still_adopted_and_stable(scope, tmp_path) -> None:
    kb, manager, first = await _import_twice_against(scope, tmp_path)
    assert first > 0 and manager._import_unresolved == []
    assert all(m.get("system_fact_id") for f, m in kb.meta.items() if f.startswith("dup-")), "duplicate not linked"
    assert kb.writes == first, "the second run wrote again (flip-flop)"


@pytest.mark.asyncio
# None: not read back; a record with no metadata dict is unreadable too, never "ownerless" (CodeRabbit #19364).
@pytest.mark.parametrize("record", [None, {"id": "x"}, {"id": "x", "metadata": None}, {"id": "x", "metadata": "{}"}])
async def test_a_duplicate_that_cannot_be_read_back_is_unresolved_not_written(record, tmp_path) -> None:
    kb = _FakeKB()
    kb.duplicate = True
    kb.get_fact = lambda fact_id: record  # owner unknown -> fail closed
    manager = _manager(kb, tmp_path)
    with patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()):
        assert await manager._import_system_knowledge() == 0
    assert kb.writes == 0 and manager._import_unresolved
