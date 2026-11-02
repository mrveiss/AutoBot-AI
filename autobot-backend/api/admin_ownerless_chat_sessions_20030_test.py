# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: the routes report and propose, and refuse a proposal nobody should approve."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import admin_ownerless_chat_sessions as route
from api.schemas_ownerless_chat_sessions import OwnerlessChatSessionRequest

_BODY = OwnerlessChatSessionRequest(session_id="s1", owner="alice")
_USER = {"id": "admin-1"}


def _db(pending=None) -> MagicMock:
    found = MagicMock()
    found.scalars.return_value.first.return_value = pending
    db = MagicMock()
    db.execute = AsyncMock(return_value=found)
    return db


async def _propose(user=None, ownerless=True, active="user-1", pending=None):
    gate = MagicMock()
    gate.return_value.create_approval = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), status="pending"))
    with (
        patch.object(route, "get_chat_history_manager", return_value=MagicMock()),
        patch.object(route, "session_is_ownerless", AsyncMock(return_value=ownerless)),
        patch.object(route, "active_user_id", AsyncMock(return_value=active)),
        patch.object(route, "ApprovalGateService", gate),
    ):
        response = await route.propose_chat_session_owner(_BODY, MagicMock(), user or _USER, _db(pending))
    return response, gate


async def test_a_valid_proposal_creates_a_pending_approval_and_writes_no_owner() -> None:
    response, gate = await _propose()
    context = gate.return_value.create_approval.await_args.kwargs["context"]
    assert context == {"action": route.ACTION, "session_id": "s1", "owner": "alice"}
    assert response.status == "pending"


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"user": {"username": "no-id"}}, 403),
        ({"ownerless": False}, 409),
        ({"active": None}, 422),
        ({"pending": uuid.uuid4()}, 409),
    ],
    ids=["unattributable", "not-ownerless", "owner-not-active", "already-pending"],
)
async def test_a_refused_proposal_creates_nothing(kwargs: dict, code: int) -> None:
    with pytest.raises(HTTPException) as refused:
        await _propose(**kwargs)
    assert refused.value.status_code == code


async def test_the_report_counts_ownerless_and_lists_unreadable_apart() -> None:
    with (
        patch.object(route, "get_chat_history_manager", return_value=MagicMock()),
        patch.object(route, "ownerless_report", AsyncMock(return_value=(["a", "b"], ["c"]))),
    ):
        report = await route.ownerless_chat_sessions(MagicMock())
    assert (report.count, report.session_ids, report.unreadable) == (2, ["a", "b"], ["c"])
