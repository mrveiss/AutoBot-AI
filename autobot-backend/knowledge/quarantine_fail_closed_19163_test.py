# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An opt-out read of quarantined facts fails closed when its audit entry cannot be written (#19163).

Every caller kind runs the REAL ``audit_quarantine_read`` over a failing ``audit_log``; the read must
raise (503) or return an error status, and no quarantined content may be served. The actor tests pin
that the backup/export audit names the requesting human and that the admin routes require a request.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge_chroma, knowledge_maintenance
from autobot_shared.ssot_config import config
from knowledge.adapters.okf_adapter import OKFAdapter
from knowledge.backup_export_quarantine_19163_test import _KB
from knowledge.quarantine import QuarantineAuditFailed, audit_quarantine_read
from knowledge.search_quarantine_19163_test import _ENGINE, _engine, _Facts, _Store

_RESEARCH = config.research_quarantine_collection
_AUDIT_LOG = "services.audit_logger.audit_log"
_ADMIN_AUDIT = "api.quarantine_read_audit.resolve_human_user"
_HELD = "held"


@pytest.fixture(params=["returns_false", "raises"])
def failed_audit(request):
    """``audit_log`` failing both ways it can: reporting False, and raising."""
    mock = AsyncMock(return_value=False) if request.param == "returns_false" else AsyncMock(side_effect=OSError("x"))
    with patch(_AUDIT_LOG, mock):
        yield mock


@pytest.mark.asyncio
async def test_the_audit_helper_refuses_when_the_entry_is_not_written(failed_audit):
    with pytest.raises(QuarantineAuditFailed) as caught:
        await audit_quarantine_read("admin", "kb.search", ["a"])
    assert caught.value.status_code == 503
    failed_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_opt_out_serves_nothing_when_the_audit_fails(failed_audit):
    with patch(_ENGINE, AsyncMock(return_value=_engine())), pytest.raises(QuarantineAuditFailed):
        await _Store().search("autobot", top_k=10, include_quarantined=True, audit_actor="admin")
    with pytest.raises(QuarantineAuditFailed):
        await _Store().search("autobot", limit=10, mode="keyword", include_quarantined=True, audit_actor="admin")


@pytest.mark.asyncio
async def test_get_all_facts_opt_out_raises_not_an_empty_list_when_the_audit_fails(failed_audit):
    with pytest.raises(QuarantineAuditFailed):
        await _Facts().get_all_facts(include_quarantined=True, audit_actor="admin")


@pytest.mark.asyncio
async def test_get_all_facts_default_read_needs_no_audit(failed_audit):
    assert [f["fact_id"] for f in await _Facts().get_all_facts()] == ["good"]
    failed_audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_backup_writes_no_file_when_the_audit_fails(tmp_path, failed_audit):
    with pytest.raises(QuarantineAuditFailed):
        await _KB().create_backup(backup_dir=str(tmp_path), compression=False, include_embeddings=False)
    assert list(tmp_path.glob("*")) == []


@pytest.mark.asyncio
async def test_export_facts_and_export_all_data_serve_nothing_when_the_audit_fails(tmp_path, failed_audit):
    with pytest.raises(QuarantineAuditFailed):
        await _KB().export_facts()
    all_data = await _KB().export_all_data(str(tmp_path))

    assert all_data["status"] == "error" and not (tmp_path / "facts.json").exists()


@pytest.mark.asyncio
async def test_okf_export_raises_and_writes_nothing_when_the_audit_fails(tmp_path, failed_audit):
    with pytest.raises(QuarantineAuditFailed):
        await OKFAdapter(_KB()).export_from_kb(str(tmp_path))
    assert list(tmp_path.rglob("*.md")) == []


def _collection(ids, metadatas):
    collection = AsyncMock()
    collection.get = AsyncMock(return_value={"ids": ids, "documents": ["d"] * len(ids), "metadatas": metadatas})
    collection.query = AsyncMock(
        return_value={
            "ids": [ids],
            "documents": [["d"] * len(ids)],
            "metadatas": [metadatas],
            "distances": [[0.1] * len(ids)],
        }
    )
    collection.count = AsyncMock(return_value=len(ids))
    client = AsyncMock()
    client.get_collection = AsyncMock(return_value=collection)
    return client


@pytest.mark.asyncio
async def test_chroma_explorer_serves_nothing_when_the_audit_fails(failed_audit):
    client = _collection(["a", _HELD], [{}, {"collection": _RESEARCH}])
    with (
        patch.object(knowledge_chroma, "get_async_chromadb_client", AsyncMock(return_value=client)),
        patch(_ADMIN_AUDIT, AsyncMock(return_value={"username": "root"})),
    ):
        with pytest.raises(QuarantineAuditFailed):
            await knowledge_chroma.list_documents("kb", MagicMock(), limit=10, offset=0, _=True)
        with pytest.raises(QuarantineAuditFailed):
            await knowledge_chroma.search_collection(
                "kb", SimpleNamespace(query="q", n_results=2, where=None), MagicMock(), _=True
            )


@pytest.mark.asyncio
async def test_lint_queues_no_scan_when_the_audit_fails(failed_audit):
    store = MagicMock()
    store._collection.get.return_value = {"ids": [_HELD], "documents": ["x"], "metadatas": [{"collection": _RESEARCH}]}
    tasks = MagicMock()
    with (
        patch.object(
            knowledge_maintenance,
            "get_or_create_knowledge_base",
            AsyncMock(return_value=SimpleNamespace(vector_store=store)),
        ),
        patch(_ADMIN_AUDIT, AsyncMock(return_value={"username": "root"})),
        pytest.raises(HTTPException) as caught,
    ):
        await knowledge_maintenance.start_lint(tasks, MagicMock(), admin_check=True)

    assert caught.value.status_code == 503
    tasks.add_task.assert_not_called()


@pytest.mark.parametrize(
    "route, name",
    [
        (knowledge_chroma.list_documents, "request"),
        (knowledge_chroma.search_collection, "http_request"),
        (knowledge_maintenance.start_lint, "req"),
    ],
)
def test_an_admin_route_that_audits_requires_its_request(route, name):
    param = inspect.signature(route).parameters[name]
    assert param.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_backup_and_export_audit_name_the_human_requester(tmp_path):
    with patch("knowledge.quarantine.audit_quarantine_read", AsyncMock(return_value=True)) as audit:
        await _KB().create_backup(
            backup_dir=str(tmp_path), compression=False, include_embeddings=False, audit_actor="alice"
        )
        await _KB().export_facts(audit_actor="bob")
        await _KB().export_all_data(str(tmp_path), audit_actor="carol")
        await OKFAdapter(_KB()).export_from_kb(str(tmp_path), audit_actor="dave")

    assert [c.args[0] for c in audit.await_args_list] == ["alice", "bob", "carol", "dave"]


@pytest.mark.asyncio
@pytest.mark.parametrize("route, method", [("export_knowledge", "export_facts"), ("create_backup", "create_backup")])
async def test_the_routes_pass_the_requesting_user_not_a_service_identity(route, method):
    kb = SimpleNamespace(**{method: AsyncMock(return_value={"status": "success"})})
    request = SimpleNamespace(
        format=SimpleNamespace(value="json"),
        filters=None,
        include_metadata=True,
        include_tags=True,
        include_embeddings=False,
        compression=False,
        description="",
    )
    with (
        patch.object(knowledge_maintenance, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch(_ADMIN_AUDIT, AsyncMock(return_value={"username": "root"})),
    ):
        await getattr(knowledge_maintenance, route)(admin_check=True, request=request, req=MagicMock())

    assert getattr(kb, method).await_args.kwargs["audit_actor"] == "root"
