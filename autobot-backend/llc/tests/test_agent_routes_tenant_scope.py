# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenant-scope tests for the LLC agent API-key and diary routes (#13771).

All four routes bound ``require_org_context`` and never used it:

  POST   /agents/{agent_id}/api-keys          — minted keys for the body's company
  DELETE /agents/{agent_id}/api-keys/{key_id} — revoked any company's key
  GET    /agents/{agent_id}/api-keys          — listed any company's key metadata
  GET    /agents/{agent_id}/diary             — read any company's agent diary
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_COMPANY_A = "11111111-1111-1111-1111-111111111111"
_COMPANY_B = "22222222-2222-2222-2222-222222222222"
_AGENT = "agent-001"


def _make_app(router_name: str, caller_org_id: str, session: AsyncMock):
    """FastAPI app carrying one LLC agent router with auth/session overridden."""
    # Deferred imports: must not be at module level (see test_suggest_ac_endpoint.py).
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    if router_name == "api_keys":
        from llc.api.api_keys import router  # noqa: PLC0415
    else:
        from llc.api.runs import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)

    async def _fake_session():
        yield session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID), "user_id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_USER_ID, is_platform_admin=False
    )
    return TestClient(app)


def _where_text(session: AsyncMock) -> str:
    """Rendered WHERE clause of the last statement the route executed.

    Not the whole statement — ``company_id`` is one of the selected columns, so
    a full-statement match would pass even with no tenant predicate at all.
    """
    return str(session.execute.await_args.args[0].whereclause)


# --------------------------------------------------------------- create


def test_create_key_uses_caller_company_not_body() -> None:
    session = AsyncMock()
    issued = MagicMock()
    issued.id, issued.agent_id, issued.company_id = uuid.uuid4(), _AGENT, _COMPANY_A
    issued.name, issued.last_used_at, issued.revoked_at = "k", None, None
    issued.created_at = datetime.now(timezone.utc)

    issue = AsyncMock(return_value=(issued, "llc_plaintext"))
    with patch("llc.services.api_key.ApiKeyService.issue_key", new=issue):
        response = _make_app("api_keys", _COMPANY_A, session).post(
            f"/agents/{_AGENT}/api-keys", json={"name": "k"}
        )

    assert response.status_code == 201
    assert issue.await_args.kwargs["company_id"] == _COMPANY_A


def test_create_key_for_another_company_is_403() -> None:
    """Company B naming company A in the body cannot mint a key for A."""
    session = AsyncMock()
    issue = AsyncMock()
    with patch("llc.services.api_key.ApiKeyService.issue_key", new=issue):
        response = _make_app("api_keys", _COMPANY_B, session).post(
            f"/agents/{_AGENT}/api-keys", json={"name": "k", "company_id": _COMPANY_A}
        )

    assert response.status_code == 403
    issue.assert_not_awaited()


# --------------------------------------------------------------- revoke


def test_revoke_key_passes_caller_company() -> None:
    session = AsyncMock()
    revoke = AsyncMock()
    with patch("llc.services.api_key.ApiKeyService.revoke_key", new=revoke):
        response = _make_app("api_keys", _COMPANY_B, session).delete(f"/agents/{_AGENT}/api-keys/{uuid.uuid4()}")

    assert response.status_code == 204
    assert revoke.await_args.kwargs["company_id"] == _COMPANY_B


def test_revoke_key_outside_company_is_404() -> None:
    """The service reports a cross-tenant key as missing; the route maps that to 404."""
    session = AsyncMock()
    with patch("llc.services.api_key.ApiKeyService.revoke_key", new=AsyncMock(side_effect=KeyError("nope"))):
        response = _make_app("api_keys", _COMPANY_B, session).delete(f"/agents/{_AGENT}/api-keys/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_key_service_filters_on_company() -> None:
    from llc.services.api_key import ApiKeyService  # noqa: PLC0415

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    with pytest.raises(KeyError):
        await ApiKeyService().revoke_key(session, _AGENT, uuid.uuid4(), company_id=_COMPANY_B)

    assert "company_id" in _where_text(session)


# --------------------------------------------------------------- list


def test_list_keys_filters_on_caller_company() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    response = _make_app("api_keys", _COMPANY_B, session).get(f"/agents/{_AGENT}/api-keys")

    assert response.status_code == 200
    assert response.json() == []
    assert "company_id" in _where_text(session)


# --------------------------------------------------------------- diary


def _diary_session(has_run_in_org: bool) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4() if has_run_in_org else None
    session.execute.return_value = result
    return session


def test_diary_readable_for_own_agent() -> None:
    session = _diary_session(has_run_in_org=True)
    entries = [{"content": "did work", "metadata": {"diary_timestamp": "2026-08-09T00:00:00Z"}}]

    with patch("memory.agent_diary.AgentDiaryService.read", new=AsyncMock(return_value=entries)):
        response = _make_app("runs", _COMPANY_A, session).get(f"/agents/{_AGENT}/diary")

    assert response.status_code == 200
    assert response.json() == entries
    assert "company_id" in _where_text(session)


def test_diary_of_another_companys_agent_is_empty() -> None:
    """No heartbeat run binds this agent to the caller's company — no entries, no KB read."""
    session = _diary_session(has_run_in_org=False)
    read = AsyncMock(return_value=[{"content": "company A secrets", "metadata": {}}])

    with patch("memory.agent_diary.AgentDiaryService.read", new=read):
        response = _make_app("runs", _COMPANY_B, session).get(f"/agents/{_AGENT}/diary")

    assert response.status_code == 200
    assert response.json() == []
    read.assert_not_awaited()
