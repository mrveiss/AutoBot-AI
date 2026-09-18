# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Approval decisions come from a person and are attributed to them (#17042).

Two systems decide human-in-the-loop requests: the LLC board approvals
(``POST /api/llc/approvals/{id}/decide``) and the general approval gates
(``POST /api/approval-gates/{id}/approve|reject``). Before #17042 the LLC route
recorded the decider from the request body, and neither route checked that the
credential belonged to a person.

Every credential here is resolved by production code: the real
``AuthenticationMiddleware`` extraction, the real async ``get_current_user``
the gates use, and the real sync ``get_current_user`` + ``get_tenant_context``
the LLC route uses. Only storage is stood in for — the session store, the Redis
password-revocation check, and the run/device token validators, which verify
real signatures here with their own test secrets.

Each non-interactive credential is handed every other advantage (a user id, an
org id, an admin role where it can have one), so the only thing left to refuse
it is the human-decider check; where that check is the refuser, the response
detail is asserted, not just the status.
"""

import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.approval_gates as gates_api
import api.user_management.dependencies as user_deps
import llc.api.approvals as llc_api
from api.user_management.human_decider import HUMAN_DECISION_REQUIRED
from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE, is_interactive_human, is_login_token
from autobot_shared.auth.jwt_core import decode_jwt, encode_jwt
from llc.deps import get_session as llc_get_session

_PLATFORM_SECRET = "p" * 40  # the platform user-session key
_RUN_SECRET = "r" * 40
_DEVICE_SECRET = "d" * 40
_RUN_AUD, _DEVICE_AUD = "autobot-run", "autobot-device"
_INTERNAL_KEY = "internal-service-key-for-tests"
_CALLER = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER = uuid.UUID("22222222-2222-2222-2222-222222222222")
_ORG = uuid.UUID("33333333-3333-3333-3333-333333333333")
_SESSION_ID = "session-17042"

_HUMAN = {
    "username": "alice",
    "role": "user",
    "email": "alice@example.test",
    "user_id": str(_CALLER),
    "org_id": str(_ORG),
}
#: What every forged or non-login token also carries, so nothing but the
#: human-decider check stands between it and a recorded decision.
_ADVANTAGE = {"user_id": str(_CALLER), "org_id": str(_ORG)}
_LOGIN = {**_HUMAN, "token_type": LOGIN_TOKEN_TYPE}
_DEVICE_CLAIMS = {"aud": _DEVICE_AUD, "device_id": "dev-1", "scope": "write", **_ADVANTAGE}


def _bearer(claims: dict, secret: str = _PLATFORM_SECRET) -> dict:
    return {"Authorization": f"Bearer {encode_jwt(claims, secret=secret, expiry_hours=1)}"}


def _credentials() -> dict:
    """Credential kind -> request headers, as each is actually presented."""
    return {
        "login_jwt": _bearer(_LOGIN),
        # A person's login minted before 2026-09-18: no token_type, so no positive
        # evidence it is a login. Refused until the 24h token is re-issued.
        "pre_17042_login_jwt": _bearer(_HUMAN),
        "session": {"X-Session-ID": _SESSION_ID},
        "internal_service_key": {"X-Internal-API-Key": _INTERNAL_KEY},
        "run_jwt": _bearer({"aud": _RUN_AUD, "run_id": "run-1", "agent_id": "agent-1", "scope": []}, _RUN_SECRET),
        "device_jwt": _bearer(_DEVICE_CLAIMS, _DEVICE_SECRET),
        # DEVICE_JWT_SECRET unset: device_jwt falls back to the platform key.
        "device_jwt_on_platform_key": _bearer(_DEVICE_CLAIMS),
        # SLM_SECRET_KEY aligned with the platform key: its pre-MFA temp token.
        "slm_mfa_pending_token": _bearer({"sub": "alice", "mfa_pending": True, "admin": True, **_ADVANTAGE}),
        # The token the backend mints for itself to call the SLM.
        "slm_service_token": _bearer({"sub": "service:backend", "service": True, **_ADVANTAGE}),
        "dev_header": {"X-User-Role": "admin", "X-Organization-Id": str(_ORG)},
        "auth_disabled": {"X-Organization-Id": str(_ORG)},
        "llc_agent_api_key": {"Authorization": "Bearer llc-agent-key-not-a-jwt"},
    }


_HUMAN_KINDS = ("login_jwt", "session")
_REFUSED_BY_HUMAN_CHECK = "human"

#: (status, refuser) per credential kind for each system. "human" means the
#: #17042 check refused it; any other refuser is credential resolution, which
#: the LLC route's sync ``get_current_user`` never extends to service/run/device.
_LLC_EXPECTED = {
    "pre_17042_login_jwt": (403, _REFUSED_BY_HUMAN_CHECK),
    "internal_service_key": (401, "resolution"),
    "run_jwt": (401, "resolution"),
    "device_jwt": (401, "resolution"),
    "device_jwt_on_platform_key": (403, _REFUSED_BY_HUMAN_CHECK),
    "slm_mfa_pending_token": (403, _REFUSED_BY_HUMAN_CHECK),
    "slm_service_token": (403, _REFUSED_BY_HUMAN_CHECK),
    "dev_header": (403, _REFUSED_BY_HUMAN_CHECK),
    "auth_disabled": (403, _REFUSED_BY_HUMAN_CHECK),
    "llc_agent_api_key": (401, "resolution"),
}
_GATE_EXPECTED = {
    "pre_17042_login_jwt": (403, _REFUSED_BY_HUMAN_CHECK),
    "internal_service_key": (403, _REFUSED_BY_HUMAN_CHECK),
    "run_jwt": (403, "run-JWT path allow-list"),
    "device_jwt": (403, "device-JWT path allow-list"),
    "device_jwt_on_platform_key": (403, _REFUSED_BY_HUMAN_CHECK),
    "slm_mfa_pending_token": (403, _REFUSED_BY_HUMAN_CHECK),
    "slm_service_token": (403, _REFUSED_BY_HUMAN_CHECK),
    "dev_header": (403, _REFUSED_BY_HUMAN_CHECK),
    "auth_disabled": (403, _REFUSED_BY_HUMAN_CHECK),
    "llc_agent_api_key": (401, "resolution"),
}


def _token_validator(secret: str, audience: str):
    async def _validate(token: str) -> dict:
        return decode_jwt(token, secret, audience=audience)

    return _validate


def _real_middleware(real_auth_middleware, *, enable_auth: bool):
    cls = real_auth_middleware.AuthenticationMiddleware
    middleware = cls.__new__(cls)
    middleware.jwt_secret = _PLATFORM_SECRET
    middleware.jwt_public_key = None
    middleware.failed_attempts = {}
    middleware.enable_auth = enable_auth
    sessions = {_SESSION_ID: {"user_data": dict(_HUMAN)}}
    middleware.get_session = sessions.get
    return middleware


def _llc_approval() -> MagicMock:
    now = datetime.now(timezone.utc)
    approval = MagicMock()
    approval.id = uuid.uuid4()
    approval.company_id = str(_ORG)
    approval.type = "project_disposal"
    approval.status = "pending"
    approval.requested_by_agent_id = uuid.uuid4()
    approval.payload = {}
    approval.decided_by_agent_id = None
    approval.decided_at = None
    approval.created_at = now
    approval.updated_at = now
    return approval


def _gate_approval() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="Delete stale data",
        description=None,
        approval_type="destructive_action",
        status="approved",
        requested_by_agent="agent-1",
        decided_by_user="alice",
        workflow_id=None,
        workflow_step=None,
        context=None,
        decided_at=None,
        created_at=None,
        updated_at=None,
        comments=[],
        task_links=[],
    )


@pytest.fixture
def harness(real_auth_middleware, monkeypatch):
    """Both routers behind the production credential resolution.

    ``configure(kind)`` sets up the one deployment switch a kind needs (auth
    disabled, debug on); ``decide``/``gates`` are the service doubles whose
    awaits prove whether a decision was recorded.
    """
    state = SimpleNamespace(middleware=_real_middleware(real_auth_middleware, enable_auth=True))

    def configure(kind: str) -> None:
        state.middleware = _real_middleware(real_auth_middleware, enable_auth=kind != "auth_disabled")
        debug = kind == "dev_header"

        def _config_get(key, default=None):
            return True if debug and key == "development.debug" else default

        monkeypatch.setattr(real_auth_middleware, "config", SimpleNamespace(get=_config_get))

    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: state.middleware)
    monkeypatch.setattr(user_deps, "get_auth_middleware", lambda: state.middleware)
    monkeypatch.setattr(real_auth_middleware, "verify_internal_api_key", lambda provided: provided == _INTERNAL_KEY)
    monkeypatch.setattr(real_auth_middleware, "reject_if_revoked_by_password_change", AsyncMock())
    run_jwt = SimpleNamespace(validate_run_jwt=_token_validator(_RUN_SECRET, _RUN_AUD))
    device_jwt = SimpleNamespace(validate_device_jwt=_token_validator(_DEVICE_SECRET, _DEVICE_AUD))
    monkeypatch.setitem(sys.modules, "services.run_jwt", run_jwt)
    monkeypatch.setitem(sys.modules, "services.device_jwt", device_jwt)
    configure("login_jwt")

    app = FastAPI()
    app.include_router(llc_api.router, prefix="/api/llc")
    app.include_router(gates_api.router, prefix="/api")
    app.dependency_overrides[gates_api.get_current_user] = real_auth_middleware.get_current_user

    llc_session = AsyncMock()
    llc_session.begin = MagicMock(return_value=AsyncMock())
    found = MagicMock()
    found.scalar_one_or_none.return_value = _llc_approval()
    llc_session.execute = AsyncMock(return_value=found)

    async def _llc_session():
        yield llc_session

    async def _db_session():
        yield AsyncMock()

    app.dependency_overrides[llc_get_session] = _llc_session
    app.dependency_overrides[user_deps.get_db_session] = _db_session

    decide = AsyncMock(return_value=_llc_approval())
    gates = MagicMock()
    gates.return_value.approve = AsyncMock(return_value=_gate_approval())
    gates.return_value.reject = AsyncMock(return_value=_gate_approval())
    logger = MagicMock()
    with (
        patch.object(llc_api.ApprovalService, "decide", new=decide),
        patch.object(llc_api.ApprovalService, "publish_decided", new=AsyncMock()),
        patch.object(llc_api.ApprovalService, "log_decision_to_kb", new=AsyncMock()),
        patch.object(llc_api, "logger", new=logger),
        patch.object(gates_api, "ApprovalGateService", new=gates),
    ):
        yield SimpleNamespace(
            client=TestClient(app),
            configure=configure,
            decide=decide,
            gates=gates,
            logger=logger,
            middleware=lambda: state.middleware,
        )


def _decide(harness, kind: str, body: dict | None = None):
    harness.configure(kind)
    payload = body or {"decision": "approved"}
    return harness.client.post(f"/api/llc/approvals/{uuid.uuid4()}/decide", json=payload, headers=_credentials()[kind])


def _gate(harness, kind: str, action: str):
    harness.configure(kind)
    return harness.client.post(
        f"/api/approval-gates/{uuid.uuid4()}/{action}", json={"comment": None}, headers=_credentials()[kind]
    )


# --- attribution (AC1, AC3) ---------------------------------------------------


@pytest.mark.parametrize("kind", _HUMAN_KINDS)
def test_llc_decision_is_recorded_as_the_verified_caller(harness, kind):
    response = _decide(harness, kind)

    assert response.status_code == 200, response.text
    assert harness.decide.await_args.kwargs["decided_by"] == _CALLER


@pytest.mark.parametrize("kind", _HUMAN_KINDS)
def test_a_body_naming_someone_else_is_recorded_as_the_real_caller(harness, kind):
    response = _decide(harness, kind, {"decision": "approved", "decided_by_agent_id": str(_OTHER)})

    assert response.status_code == 200, response.text
    assert harness.decide.await_args.kwargs["decided_by"] == _CALLER
    warned = [call.args for call in harness.logger.warning.call_args_list]
    assert any(_OTHER in args for args in warned), f"no warning named the ignored decider: {warned}"


def test_a_body_without_a_decider_logs_no_warning(harness):
    assert _decide(harness, "login_jwt").status_code == 200
    harness.logger.warning.assert_not_called()


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("kind", _HUMAN_KINDS)
def test_a_person_can_decide_an_approval_gate_as_themselves(harness, kind, action):
    response = _gate(harness, kind, action)

    assert response.status_code == 200, response.text
    assert getattr(harness.gates.return_value, action).await_args.args[1] == "alice"


# --- negative controls, one per credential type (AC2) --------------------------


@pytest.mark.parametrize("kind", sorted(_LLC_EXPECTED))
def test_llc_decision_refuses_a_non_interactive_credential(harness, kind):
    status, refuser = _LLC_EXPECTED[kind]

    response = _decide(harness, kind)

    assert response.status_code == status, response.text
    if refuser == _REFUSED_BY_HUMAN_CHECK:
        assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    harness.decide.assert_not_awaited()


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("kind", sorted(_GATE_EXPECTED))
def test_approval_gate_refuses_a_non_interactive_credential(harness, kind, action):
    status, refuser = _GATE_EXPECTED[kind]

    response = _gate(harness, kind, action)

    assert response.status_code == status, response.text
    if refuser == _REFUSED_BY_HUMAN_CHECK:
        assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    getattr(harness.gates.return_value, action).assert_not_awaited()


def test_auth_disabled_deployment_is_refused(harness):
    """Auth-disabled resolves every caller to an admin with no auth_method (#17042 review)."""
    for response in (_decide(harness, "auth_disabled"), _gate(harness, "auth_disabled", "approve")):
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == HUMAN_DECISION_REQUIRED
    harness.decide.assert_not_awaited()
    harness.gates.return_value.approve.assert_not_awaited()


def test_every_credential_kind_has_a_control_in_both_systems():
    """A credential kind added to ``_credentials`` must be classified for both routes."""
    kinds = set(_credentials()) - set(_HUMAN_KINDS)
    assert kinds == set(_LLC_EXPECTED) == set(_GATE_EXPECTED)


def test_the_login_mint_and_the_check_agree(real_auth_middleware, monkeypatch):
    """What create_jwt_token signs is what is_login_token accepts — the positive evidence exists."""
    minted = {}

    def _capture(payload, **_kwargs):
        minted.update(payload)
        return "signed"

    monkeypatch.setattr(real_auth_middleware, "encode_jwt", _capture)
    middleware = _real_middleware(real_auth_middleware, enable_auth=True)
    middleware.jwt_private_key, middleware.jwt_kid, middleware.jwt_expiry_hours = "key", "kid", 24

    middleware.create_jwt_token({"username": "alice", "role": "user", "user_id": _CALLER, "org_id": _ORG})

    assert minted["token_type"] == LOGIN_TOKEN_TYPE
    assert (minted["user_id"], minted["org_id"]) == (str(_CALLER), str(_ORG))
    assert is_login_token(minted)


# --- the check itself, for credentials a route refuses before reaching it -------


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["run_jwt", "device_jwt"])
async def test_run_and_device_users_are_not_human_even_where_a_path_would_admit_them(harness, kind):
    """The path allow-lists refuse these today; the check must not depend on that."""
    harness.configure(kind)
    request = MagicMock()
    headers = _credentials()[kind]
    request.headers.get = lambda key, default=None: headers.get(key, default)
    middleware = harness.middleware()
    extract = middleware._extract_user_from_run_jwt if kind == "run_jwt" else middleware._extract_user_from_device_jwt

    user = await extract(request)

    assert user is not None, f"the real {kind} extractor did not resolve the test token"
    assert not is_interactive_human(user)
