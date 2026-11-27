# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The approval-gates requester is the verified caller; a body value is only a display label (#20521)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from api import approval_gates, approval_gates_requester
from api.schemas_approvals import CreateApprovalRequest
from services import approval_execution
from services.approval_execution import context_change_violation

# Fixed ids: they appear in parametrize ids, which must be identical on every xdist worker.
_ME = "3f2b8c1e-6a4d-4e0b-9c57-1d2e8a7b4f60"
_VICTIM = "9a1c7d42-0b5e-4f83-a6d2-5e8b1c3f7a90"


def _body(**extra) -> CreateApprovalRequest:
    return CreateApprovalRequest(title="t", approval_type="destructive_action", **extra)


async def _create(body: CreateApprovalRequest, user: dict) -> dict:
    """The keyword arguments the route hands the service."""
    created = SimpleNamespace(id=uuid.uuid4())
    svc = MagicMock(create_approval=AsyncMock(return_value=created))
    with (
        patch.object(approval_gates, "ApprovalGateService", return_value=svc),
        patch.object(approval_gates, "_to_response", return_value=None),
    ):
        await approval_gates.create_approval(body, user, AsyncMock())
    return svc.create_approval.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("forged", [f"user:{_VICTIM}", _VICTIM, "victim-username"])
async def test_a_body_requester_never_becomes_the_requester(forged: str) -> None:
    kwargs = await _create(_body(requested_by_agent=forged), {"id": _ME, "username": "me"})

    assert kwargs["requested_by_agent"] == f"user:{_ME}"
    assert kwargs["context"]["requested_label"] == forged, "kept for display only"


@pytest.mark.asyncio
async def test_the_label_joins_the_callers_context_and_no_label_leaves_it_alone() -> None:
    labelled = await _create(_body(requested_by_agent="data_hygiene_console", context={"note": "x"}), {"id": _ME})
    assert labelled["context"] == {"note": "x", "requested_label": "data_hygiene_console"}
    plain = await _create(_body(context={"note": "x"}), {"id": _ME})
    assert plain["context"] == {"note": "x"}


@pytest.mark.asyncio
async def test_a_caller_with_no_identity_cannot_create() -> None:
    with pytest.raises(HTTPException) as refused:
        await _create(_body(requested_by_agent=f"user:{_VICTIM}"), {})
    assert refused.value.status_code == 401


@pytest.mark.asyncio
async def test_the_person_a_body_named_cannot_resubmit_as_requester_but_the_real_requester_can() -> None:
    kwargs = await _create(_body(requested_by_agent=f"user:{_VICTIM}"), {"id": _ME})
    row = SimpleNamespace(requested_by_agent=kwargs["requested_by_agent"], context=kwargs["context"])

    with pytest.raises(HTTPException) as refused:
        approval_gates._guard_resubmit(row, None, {"id": _VICTIM, "username": "victim"})
    assert refused.value.status_code == 403
    approval_gates._guard_resubmit(row, None, {"id": _ME, "username": "me"})  # no refusal


def test_the_display_label_is_not_a_reviewed_field_on_resubmit() -> None:
    old = {"action": "act", "provider": "p", "requested_label": "console"}
    with patch.dict(approval_execution._REGISTRY, {"act": object()}):
        assert context_change_violation(old, {"action": "act", "provider": "p"}) is None
        assert context_change_violation(old, {"action": "act", "provider": "other"}) == "context.provider"


def test_a_sub_only_principal_can_resubmit_its_own_request() -> None:
    """#22222: the shared resolver reads ``sub``, so the requester check does too."""
    row = SimpleNamespace(requested_by_agent=f"user:{_ME}", context=None)
    approval_gates._guard_resubmit(row, None, {"sub": _ME})  # no refusal
    with pytest.raises(HTTPException):
        approval_gates._guard_resubmit(row, None, {"sub": _VICTIM})


def test_an_admitted_service_can_resubmit_a_request_it_made() -> None:
    """#22222: a service requester is its stable ``service:<caller>`` name."""
    row = SimpleNamespace(requested_by_agent="service:slm-x", context=None)
    approval_gates._guard_resubmit(row, None, {"username": "service:slm-x", "service": True})  # no refusal


@pytest.mark.asyncio
async def test_the_response_carries_the_requesters_name_for_a_known_id() -> None:
    """#22222: the stored id is resolved to a name at read time; unknown ids and services show as stored."""
    known = SimpleNamespace(id=uuid.uuid4(), requested_by_agent=f"cleanup-proposal:{_ME}")
    service = SimpleNamespace(id=uuid.uuid4(), requested_by_agent="service:slm-x")
    ghost = SimpleNamespace(id=uuid.uuid4(), requested_by_agent=_VICTIM)
    with patch.object(
        approval_gates_requester, "member_people", AsyncMock(return_value=({uuid.UUID(_ME): "Ada Admin"}, {}))
    ):
        names = await approval_gates_requester.requester_names(_session(), [known, service, ghost])
    assert names == {str(known.id): "Ada Admin"}
    built = [approval_gates_requester.display_requester(a, names) for a in (known, service, ghost)]
    assert built == ["Ada Admin", "service:slm-x", _VICTIM]


def _session() -> MagicMock:
    """A session whose SAVEPOINT (``begin_nested``) is an async context manager that records its exit."""
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock(return_value=None)
    savepoint.__aexit__ = AsyncMock(return_value=False)  # does not swallow: the error propagates after rollback
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=savepoint)
    session.savepoint = savepoint
    return session


@pytest.mark.asyncio
async def test_a_failed_name_lookup_rolls_back_only_its_savepoint_and_never_fails_the_response() -> None:
    """#22222: the lookup runs in a SAVEPOINT, so the request's session stays usable after a DB error."""
    row = SimpleNamespace(id=uuid.uuid4(), requested_by_agent=_ME)
    session = _session()
    with patch.object(approval_gates_requester, "member_people", AsyncMock(side_effect=SQLAlchemyError("db"))):
        assert await approval_gates_requester.requester_names(session, [row]) == {}
    session.begin_nested.assert_called_once()
    session.savepoint.__aexit__.assert_awaited_once()  # the SAVEPOINT was exited (rolled back), not the outer transaction
