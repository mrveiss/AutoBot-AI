# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embedding-model switch endpoints: start (admin), status, cancel (admin) (#19379)."""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from api import embeddings
from api.schemas_embeddings import EmbeddingSwitchRequest
from knowledge import embedding_switch

pytestmark = pytest.mark.asyncio

_STATUS = {"state": "building", "model": "bge-m3:latest", "collection": "kb_bge", "done": 3, "total": 9}


@pytest.fixture
def switch(monkeypatch):
    calls = []

    async def _start(kb, model, actor="unknown"):
        calls.append(("start", kb, model, actor))
        if model == "phi3:mini":
            raise embedding_switch.SwitchRefused("'phi3:mini' is not an embedding model")
        if model == "busy":
            raise embedding_switch.SwitchRefused("a switch is already running")
        return dict(_STATUS, failed_ids=[], extra="ignored")

    async def _status():
        return dict(_STATUS, failed_ids=[])

    async def _kb(request):
        return "the-kb"

    import dependencies

    monkeypatch.setattr(embedding_switch, "start_switch", _start)
    monkeypatch.setattr(embedding_switch, "switch_status", _status)
    monkeypatch.setattr(dependencies, "provide_knowledge_base", _kb)
    return calls


async def test_start_runs_the_switch_against_the_app_kb(switch):
    result = await embeddings.start_embedding_switch(
        EmbeddingSwitchRequest(model="bge-m3:latest"), request=None, current_user={"user_id": "admin-1"}
    )
    assert switch == [("start", "the-kb", "bge-m3:latest", "admin-1")], "the actor reaches the audit"
    assert result.data.state == "building" and (result.data.done, result.data.total) == (3, 9)


@pytest.mark.parametrize("model, code", [("phi3:mini", 400), ("busy", 409)])
async def test_a_refused_start_is_a_client_error(switch, model, code):
    with pytest.raises(HTTPException) as exc:
        await embeddings.start_embedding_switch(EmbeddingSwitchRequest(model=model), request=None, current_user={})
    assert exc.value.status_code == code


async def test_status_reports_progress(switch):
    result = await embeddings.get_embedding_switch_status()
    assert result.data.model == "bge-m3:latest" and result.data.failed_ids == []


async def test_cancel_without_a_running_switch_is_409(switch, monkeypatch):
    async def _none(actor="unknown"):
        return "none"

    monkeypatch.setattr(embedding_switch, "request_switch_cancel", _none)
    with pytest.raises(HTTPException) as exc:
        await embeddings.cancel_embedding_switch(current_user={})
    assert exc.value.status_code == 409


async def test_cancel_after_cutover_began_is_409(switch, monkeypatch):
    async def _late(actor="unknown"):
        return "too_late"

    monkeypatch.setattr(embedding_switch, "request_switch_cancel", _late)
    with pytest.raises(HTTPException) as exc:
        await embeddings.cancel_embedding_switch(current_user={})
    assert exc.value.status_code == 409 and "cutover" in exc.value.detail


@pytest.mark.parametrize("outcome", ["cancel_requested", "force_closed"])
async def test_cancel_or_force_close_returns_the_status(switch, monkeypatch, outcome):
    async def _done(actor="unknown"):
        return outcome

    monkeypatch.setattr(embedding_switch, "request_switch_cancel", _done)
    result = await embeddings.cancel_embedding_switch(current_user={"user_id": "admin-1"})
    assert result.data.state == "building"


def test_start_and_cancel_require_admin_status_does_not():
    """Maintainer decision (2026-10-25): only admins start or cancel a switch."""
    for handler in (embeddings.start_embedding_switch, embeddings.cancel_embedding_switch):
        assert "check_admin_permission" in inspect.getsource(handler)
    assert "get_current_user" in inspect.getsource(embeddings.get_embedding_switch_status)
