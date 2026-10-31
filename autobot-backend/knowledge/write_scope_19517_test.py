# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A caller's ownership and visibility never reach a KB write unchecked (#19517).

The agent ``store_fact`` tool forwarded the LLM's metadata, so ``visibility: system`` made a
fact readable by every signed-in user and ``owner_id`` filed it under someone else. These tests
drive the real tool and the real ``KnowledgeBase.store_fact``; only persistence and the
duplicate check are stubbed, so what is asserted is the metadata that would have been written.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.ingest_sanitize import sanitize_update_metadata
from knowledge.write_scope import KbWriteDenied, add_document_as, caller_write_scope, guard_caller_metadata
from llm_shared.run_credentials import llm_principal_scope
from task_handlers.knowledge_base_handlers import KBStoreFactHandler
from tests.helpers.fake_kb import FactsFakeKB
from tools.tool_registry import ToolRegistry

_FORGED = {
    "visibility": "system",
    "owner_id": "victim",
    "user_id": "victim",
    "organization_id": "other-org",
    "shared_with": ["victim"],
    "access_level": "general",
    "source_type": "connector",
    "title": "kept",
}


class _RecordingKB(FactsFakeKB):
    """The real ``store_fact``, recording what it would persist."""

    persisted: list

    async def add_document(self, content, metadata=None, doc_id=None, **_kw):
        return await self.store_fact(content, metadata, doc_id)

    async def add_file(self, file_path, file_type, metadata=None):
        return await self.store_fact(file_path, metadata)


async def _recording_kb() -> tuple[_RecordingKB, list]:
    kb = _RecordingKB()
    kb.persisted = []

    async def _capture(fact_id, text, meta, **_kwargs):
        kb.persisted.append(dict(meta))
        return {"status": "success", "fact_id": fact_id, "action": "created"}

    patches = (
        patch.object(_RecordingKB, "_check_for_duplicates", new=AsyncMock(return_value=None)),
        patch.object(_RecordingKB, "_store_and_vectorize_fact", new=AsyncMock(side_effect=_capture)),
    )
    for p in patches:
        p.start()
    return kb, list(patches)


@pytest.fixture
async def kb():
    kb, patches = await _recording_kb()
    yield kb
    for p in patches:
        p.stop()


@pytest.mark.asyncio
async def test_an_agent_tool_write_cannot_set_system_visibility_or_a_foreign_owner(kb):
    """The defect: the tool's metadata went straight into the store."""
    with llm_principal_scope("user-1", "org-1"):
        result = await ToolRegistry(knowledge_base=kb).store_fact("a fact", dict(_FORGED))

    assert result["status"] == "success"
    (meta,) = kb.persisted
    assert meta["owner_id"] == "user-1" and meta["organization_id"] == "org-1"
    for key in ("visibility", "user_id", "shared_with", "access_level"):
        assert key not in meta, key
    assert meta["source_type"] != "connector"
    assert meta["title"] == "kept"


@pytest.mark.asyncio
async def test_an_agent_file_write_is_guarded_the_same_way(kb):
    with llm_principal_scope("user-1", "org-1"):
        await ToolRegistry(knowledge_base=kb).add_file_to_knowledge_base("/x.txt", "txt", dict(_FORGED))

    (meta,) = kb.persisted
    assert meta["owner_id"] == "user-1" and "visibility" not in meta


@pytest.mark.asyncio
async def test_an_agent_turn_with_no_signed_in_user_writes_nothing(kb):
    result = await ToolRegistry(knowledge_base=kb).store_fact("a fact", dict(_FORGED))

    assert result["status"] == "error"
    assert kb.persisted == []


@pytest.mark.asyncio
async def test_a_caller_claiming_to_be_internal_gains_nothing(kb):
    """``ingest_route`` is metadata the caller writes; only a scope entered by code counts."""
    claim = {**_FORGED, "ingest_route": "sync_incremental", "source": "project-documentation"}
    with llm_principal_scope("user-1"):
        await ToolRegistry(knowledge_base=kb).store_fact("a fact", claim)

    assert kb.persisted[0]["owner_id"] == "user-1" and "visibility" not in kb.persisted[0]


@pytest.mark.asyncio
async def test_system_internal_ingest_keeps_the_ownership_its_code_sets(kb):
    await kb.store_fact("a doc", {"visibility": "system", "owner_id": "svc", "ingest_route": "sync_incremental"})

    assert kb.persisted[0]["visibility"] == "system" and kb.persisted[0]["owner_id"] == "svc"


@pytest.mark.asyncio
async def test_an_admin_scope_sets_ownership_as_asked(kb):
    with caller_write_scope("admin-1", "org-1", "admin"):
        await kb.store_fact("a doc", {"visibility": "system", "owner_id": "someone"})

    assert kb.persisted[0]["visibility"] == "system" and kb.persisted[0]["owner_id"] == "someone"


@pytest.mark.asyncio
async def test_the_mcp_write_stamps_the_caller_and_drops_the_payloads_ownership(kb):
    user = {"user_id": "user-2", "org_id": "org-2", "role": "user"}
    await add_document_as(kb, user, content="doc", metadata=dict(_FORGED))

    assert kb.persisted[0]["owner_id"] == "user-2" and "visibility" not in kb.persisted[0]


@pytest.mark.asyncio
async def test_a_task_handler_write_is_owned_by_the_tasks_user_not_the_payload(kb):
    ctx = SimpleNamespace(
        require_payload_value=lambda _k: "content",
        get_payload_value=lambda _k, default=None: dict(_FORGED),
        worker=SimpleNamespace(resolve_knowledge_base=AsyncMock(return_value=kb)),
        metadata={"user_id": "user-3"},
        audit_log=lambda *_a, **_k: None,
    )
    await KBStoreFactHandler().execute(ctx)

    assert kb.persisted[0]["owner_id"] == "user-3" and "visibility" not in kb.persisted[0]


def test_an_update_by_a_caller_cannot_change_ownership_and_does_not_reown_the_fact():
    with caller_write_scope("user-1", "org-1", "user"):
        cleaned = sanitize_update_metadata({**_FORGED, "source": "https://u:p@h/x"})

    assert not set(cleaned) & {"visibility", "owner_id", "user_id", "shared_with", "organization_id"}
    assert cleaned["title"] == "kept" and "u:p@" not in cleaned["source"]


def test_a_non_admin_scope_with_no_principal_is_refused():
    with caller_write_scope(None, None, "user"):
        with pytest.raises(KbWriteDenied):
            guard_caller_metadata({"title": "t"})


def test_outside_a_scope_the_metadata_is_untouched():
    meta = {"visibility": "system"}
    assert guard_caller_metadata(meta) is meta
