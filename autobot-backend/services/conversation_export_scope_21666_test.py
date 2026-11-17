# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/conversations/export-all`` exports the caller's own sessions only; the instance-wide export is admin-only (#21666)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import chat_sessions
from api import conversation_export as export_route
from services.conversation_export import export_all_conversations_json

_OWNERS = {"s-a": "alice", "s-b": "bob"}


@pytest.fixture
def manager(monkeypatch):
    """Two stored sessions, one per user; the canonical filter keeps the sessions *username* owns."""
    ids = [{"id": sid} for sid in _OWNERS]
    chm = MagicMock()
    chm.list_sessions_fast = AsyncMock(return_value=ids)
    chm.list_sessions = AsyncMock(return_value=ids)
    chm.get_session_owner = AsyncMock(side_effect=lambda sid: _OWNERS[sid])
    chm.load_full_session = AsyncMock(
        side_effect=lambda sid: {"name": sid, "messages": [{"role": "user", "content": sid}]}
    )

    async def _own(sessions, username, read_owner):
        return [s for s in sessions if await read_owner(s["id"]) == username]

    monkeypatch.setattr(chat_sessions, "_filter_user_sessions", _own)
    return chm


async def _exported_ids(manager, username, **kwargs):
    archive = json.loads(await export_all_conversations_json(manager, username, **kwargs))
    return {c["session_id"] for c in archive["conversations"]}


@pytest.mark.asyncio
async def test_a_users_export_holds_their_own_sessions_and_not_anothers(manager) -> None:
    assert await _exported_ids(manager, "alice") == {"s-a"}
    assert await _exported_ids(manager, "bob") == {"s-b"}


@pytest.mark.asyncio
async def test_a_principal_with_no_username_exports_nothing(manager) -> None:
    assert await _exported_ids(manager, None) == set()


@pytest.mark.asyncio
async def test_the_instance_wide_export_holds_every_session(manager) -> None:
    assert await _exported_ids(manager, "root", all_users=True) == {"s-a", "s-b"}


def _request():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    return request


def test_a_non_admin_is_refused_and_the_attempt_audited(monkeypatch) -> None:
    audit = MagicMock()
    monkeypatch.setattr(export_route, "audit_record", audit)

    with pytest.raises(HTTPException) as refused:
        export_route._require_admin_for_instance_export(_request(), {"username": "alice", "role": "user"})

    assert refused.value.status_code == 403
    assert audit.call_args.kwargs["outcome"] == "denied"


def test_an_admin_passes_the_gate_without_a_success_audit_yet(monkeypatch) -> None:
    audit = MagicMock()
    monkeypatch.setattr(export_route, "audit_record", audit)

    export_route._require_admin_for_instance_export(_request(), {"username": "root", "role": "admin"})

    audit.assert_not_called()


@pytest.mark.asyncio
async def test_the_success_is_audited_only_after_the_archive_is_built(monkeypatch) -> None:
    order: list[str] = []
    monkeypatch.setattr(export_route, "audit_record", lambda **kw: order.append(f"audit:{kw['outcome']}"))
    monkeypatch.setattr(export_route, "get_chat_history_manager", lambda request: MagicMock())

    async def _build(*args, **kwargs):
        order.append("build")
        return "{}"

    monkeypatch.setattr(export_route, "export_all_conversations_json", _build)

    await export_route.export_all_conversations(_request(), True, {"username": "root", "role": "admin"})

    assert order == ["build", "audit:success"]
