# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GET /conversations/{session_id}/export`` follows read access: owner or participant, same company (#22002, #21997).

The route is driven through a real FastAPI app, so the dependency the router declares is what runs. The
ownership validator is a stand-in that, like the real one, starts at ``authenticated_user`` (where the company
refusal lives) and then decides by who is asking.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import conversation_export as export_route
from auth_middleware import get_current_user
from security import session_company, session_posture

_SID = "chat_" + "a" * 32
_CO_A, _CO_B = str(uuid.uuid4()), str(uuid.uuid4())


class _Validator:
    """Owner and a share participant are authorised; anyone else is the canonical 403."""

    def __init__(self, *_a, **_k):
        pass

    async def validate_ownership(self, session_id, request):
        user = await session_posture.authenticated_user(session_id, request)
        if user["username"] == "owner":
            return {"authorized": True, "user_data": user, "reason": "owner_match"}
        if user["username"] == "participant":
            return {"authorized": True, "user_data": user, "reason": "shared_access"}
        raise HTTPException(status_code=403, detail="Access denied: You do not own this session")


def _client(monkeypatch, stored_company=None):
    app = FastAPI()
    app.include_router(export_route.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"username": "x"}
    monkeypatch.setattr("security.session_ownership.SessionOwnershipValidator", _Validator)
    monkeypatch.setattr("autobot_shared.redis_client.get_redis_client", AsyncMock())
    monkeypatch.setattr("services.feature_flags.get_feature_flags", AsyncMock(return_value=None))
    monkeypatch.setattr("services.access_control_metrics.get_metrics_service", AsyncMock(return_value=None))
    monkeypatch.setattr(export_route, "_run_export", AsyncMock(return_value="{}"))
    monkeypatch.setattr(export_route, "get_chat_history_manager", lambda request: MagicMock())
    monkeypatch.setattr(session_company, "may_act_in_company", AsyncMock(return_value=True))
    monkeypatch.setattr(session_company, "company_of_session", AsyncMock(return_value=stored_company))
    return TestClient(app)


def _as(monkeypatch, username):
    user = {"username": username, "user_id": str(uuid.uuid4()), "role": "user"}
    monkeypatch.setattr(session_posture, "resolve_human_user", AsyncMock(return_value=user))


def _export(client, company=None):
    headers = {session_company.ACTIVE_COMPANY_HEADER: company} if company else {}
    with patch("auth_middleware.get_auth_middleware") as auth:
        auth.return_value.enable_auth = True
        return client.get(f"/api/conversations/{_SID}/export", headers=headers)


def test_a_non_owner_non_participant_is_refused_with_the_canonical_403(monkeypatch):
    _as(monkeypatch, "stranger")
    response = _export(_client(monkeypatch))
    assert response.status_code == 403
    export_route._run_export.assert_not_awaited()


def test_the_owner_can_export(monkeypatch):
    _as(monkeypatch, "owner")
    assert _export(_client(monkeypatch)).status_code == 200


def test_a_share_participant_can_export(monkeypatch):
    _as(monkeypatch, "participant")
    assert _export(_client(monkeypatch)).status_code == 200


def test_a_chat_of_another_company_is_refused_even_for_the_owner(monkeypatch):
    _as(monkeypatch, "owner")
    response = _export(_client(monkeypatch, stored_company=_CO_B), company=_CO_A)
    assert (response.status_code, response.json()["detail"]) == (403, "Forbidden")
    export_route._run_export.assert_not_awaited()


def test_the_owner_exports_a_chat_of_the_active_company(monkeypatch):
    _as(monkeypatch, "owner")
    assert _export(_client(monkeypatch, stored_company=_CO_A), company=_CO_A).status_code == 200
