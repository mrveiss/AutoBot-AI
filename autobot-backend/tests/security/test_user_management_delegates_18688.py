# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""user_management's ``get_current_user`` is the canonical gate (#18688).

Two things follow from delegating ~357 user_management-gated routes (mostly
``llc/api``) to ``auth_middleware.get_current_user``:

* a token minted before its subject's password changed is refused on those
  routes too (it was honoured there before), and
* the internal service key now resolves to a ``service`` principal, which is
  NOT a tenant admin (owner decision 2026-10-17): the wrapper refuses it with
  the 401 main answered, while a route on ``auth_middleware`` directly still
  admits it (no wrapper route has a named service caller).

The real canonical gate runs here; only storage (the epoch lookup) is stood in.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.user_management.dependencies as user_deps
import llc.api.approvals as llc_api
from llc.deps import get_session as llc_get_session
from testkit.canonical_gate import install_canonical_gate, no_user_middleware

INTERNAL_KEY = "internal-service-key-for-tests"
_JWT_USER = {
    "username": "alice",
    "role": "admin",
    "user_id": str(uuid.uuid4()),
    "iat": 1,
    "auth_method": "jwt",
}


def _llc_client() -> TestClient:
    app = FastAPI()
    app.include_router(llc_api.router, prefix="/api/llc")

    async def _session():
        yield AsyncMock()

    app.dependency_overrides[llc_get_session] = _session
    app.dependency_overrides[user_deps.get_db_session] = _session
    return TestClient(app, raise_server_exceptions=False)


def _jwt_middleware() -> MagicMock:
    middleware = no_user_middleware()
    middleware.get_user_from_request.return_value = dict(_JWT_USER)
    return middleware


@pytest.mark.parametrize("revoked, expected_401", [(True, True), (False, False)])
def test_a_password_change_revoked_jwt_is_refused_on_an_llc_route(monkeypatch, revoked, expected_401):
    import auth_revocation  # noqa: PLC0415

    install_canonical_gate(monkeypatch, _jwt_middleware())
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=revoked))

    response = _llc_client().get("/api/llc/approvals", params={"company_id": str(uuid.uuid4())})

    assert (response.status_code == 401) is expected_401, response.text
    if expected_401:
        assert "password was changed" in response.json()["detail"]


def _service_key_gate(monkeypatch):
    real = install_canonical_gate(monkeypatch, no_user_middleware())
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == INTERNAL_KEY)
    return real


@pytest.mark.parametrize(
    "headers, params",
    [
        ({"X-Organization-Id": str(uuid.uuid4())}, {}),
        ({}, {"company_id": str(uuid.uuid4())}),
        ({}, {}),  # no org at all: still refused, not "org context required"
    ],
)
def test_the_internal_service_key_is_refused_at_the_wrapper_on_an_org_scoped_route(monkeypatch, headers, params):
    _service_key_gate(monkeypatch)

    response = _llc_client().get(
        "/api/llc/approvals", params=params, headers={"X-Internal-API-Key": INTERNAL_KEY, **headers}
    )

    # 401 is what main answered the key on this dependency (JWT/session only).
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required"


def test_the_internal_service_key_gets_no_cross_tenant_company_list(monkeypatch):
    import llc.api.companies as companies_api  # noqa: PLC0415

    _service_key_gate(monkeypatch)
    svc = MagicMock()
    svc.list_root_companies = AsyncMock(return_value=[MagicMock()])
    app = FastAPI()
    app.include_router(companies_api.router, prefix="/api/llc")
    app.dependency_overrides[companies_api._get_service] = lambda: svc

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/llc/companies/", headers={"X-Internal-API-Key": INTERNAL_KEY}
    )

    assert response.status_code == 401, response.text
    svc.list_root_companies.assert_not_called()


@pytest.mark.parametrize("path", ["/report", "/summary"])
def test_the_internal_service_key_is_refused_on_a_wrapper_only_route(monkeypatch, path):
    import api.analytics_reporting as analytics  # noqa: PLC0415

    _service_key_gate(monkeypatch)
    app = FastAPI()
    app.include_router(analytics.router)

    response = TestClient(app, raise_server_exceptions=False).get(path, headers={"X-Internal-API-Key": INTERNAL_KEY})

    assert response.status_code == 401, response.text


def test_the_tenant_context_still_refuses_a_service_principal_handed_to_it_directly():
    service = {"username": "service:slm", "role": "admin", "service": True}
    request = MagicMock()
    request.headers = {}
    request.path_params = {}
    request.query_params = {}

    with pytest.raises(HTTPException) as refused:
        asyncio.run(user_deps._resolve_tenant_context(request, service, AsyncMock()))

    assert refused.value.status_code == 403
    assert refused.value.detail == user_deps._SERVICE_PRINCIPAL_DENIED


@pytest.mark.parametrize(
    "claims, expected",
    [
        ({"username": "service:slm", "role": "admin", "service": True}, False),
        ({"username": "alice", "role": "admin"}, True),  # control: the same role, no service marker
    ],
)
def test_me_derives_platform_admin_from_the_shared_predicate(claims, expected):
    import api.user_management.users as users_api  # noqa: PLC0415
    from tests.user_management.test_users_me_18786 import _stored_user  # noqa: PLC0415

    uid = uuid.uuid4()
    service = MagicMock()
    service.get_user = AsyncMock(return_value=_stored_user(uid))

    # The real UserResponse is built (#18786): the flag is the claims', not the stored row's.
    response = asyncio.run(
        users_api.get_current_user_profile(current_user={**claims, "user_id": str(uid)}, user_service=service)
    )

    assert response.is_platform_admin is expected


def test_a_human_admin_jwt_still_lists_companies(monkeypatch):
    import auth_revocation  # noqa: PLC0415
    import llc.api.companies as companies_api  # noqa: PLC0415

    install_canonical_gate(monkeypatch, _jwt_middleware())
    # #19061 review: a username-only login token is now epoch-checked (it was silently skipped
    # without a `sub`), so this test stands in the epoch store like its neighbours.
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))
    svc = MagicMock()
    svc.list_root_companies = AsyncMock(return_value=[])
    app = FastAPI()
    app.include_router(companies_api.router, prefix="/api/llc")
    app.dependency_overrides[companies_api._get_service] = lambda: svc

    response = TestClient(app, raise_server_exceptions=False).get("/api/llc/companies/")

    assert response.status_code == 200, response.text
    svc.list_root_companies.assert_awaited_once()


def test_the_internal_service_key_still_works_on_a_non_tenant_route(monkeypatch):
    real = _service_key_gate(monkeypatch)
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: dict = Depends(real.get_current_user)):
        return user

    response = TestClient(app).get("/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY})

    assert response.status_code == 200, response.text
    assert response.json() == {"username": "service:slm", "role": "admin", "service": True}


def test_a_service_principal_is_not_a_platform_admin_or_reporting_line_writer():
    service = {"username": "service:slm", "role": "admin", "service": True}

    assert user_deps._is_platform_admin_claim(service) is False
    assert user_deps._holds_reporting_line_write(service) is False
    # Control: the same role without the service marker keeps both grants.
    human = {"username": "alice", "role": "admin"}
    assert user_deps._is_platform_admin_claim(human) is True
    assert user_deps._holds_reporting_line_write(human) is True


def _key_and_jwt_gate(monkeypatch, middleware):
    real = install_canonical_gate(monkeypatch, middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == INTERNAL_KEY)
    return real


def _whoami_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: dict = Depends(user_deps.get_current_user)):
        return user

    return app


def test_the_internal_key_with_a_valid_user_jwt_resolves_to_the_human_user(monkeypatch):
    # The SLM nginx adds the key to every proxied call next to the user's own JWT.
    import auth_revocation  # noqa: PLC0415

    _key_and_jwt_gate(monkeypatch, _jwt_middleware())
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))

    response = TestClient(_whoami_app()).get("/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY})

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "alice"
    assert not response.json().get("service")


def test_the_internal_key_with_a_revoked_user_jwt_is_refused(monkeypatch):
    import auth_revocation  # noqa: PLC0415

    _key_and_jwt_gate(monkeypatch, _jwt_middleware())
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=True))

    response = TestClient(_whoami_app(), raise_server_exceptions=False).get(
        "/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY}
    )

    assert response.status_code == 401, response.text


def test_the_internal_key_with_an_expired_user_jwt_is_refused(monkeypatch):
    # An expired token resolves to no user (get_user_from_request -> None).
    _key_and_jwt_gate(monkeypatch, no_user_middleware())

    response = TestClient(_whoami_app(), raise_server_exceptions=False).get(
        "/whoami",
        headers={"X-Internal-API-Key": INTERNAL_KEY, "Authorization": "Bearer expired"},
    )

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required"


def test_the_internal_key_alone_is_refused_on_a_wrapper_route(monkeypatch):
    _key_and_jwt_gate(monkeypatch, no_user_middleware())

    response = TestClient(_whoami_app(), raise_server_exceptions=False).get(
        "/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY}
    )

    assert response.status_code == 401, response.text


def test_a_service_principal_resolved_as_the_human_is_still_refused(monkeypatch):
    middleware = no_user_middleware()
    middleware.get_user_from_request.return_value = {"username": "service:slm", "role": "admin", "service": True}
    _key_and_jwt_gate(monkeypatch, middleware)

    response = TestClient(_whoami_app(), raise_server_exceptions=False).get(
        "/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY}
    )

    assert response.status_code == 401, response.text


def test_a_user_jwt_alone_is_unchanged_on_a_wrapper_route(monkeypatch):
    import auth_revocation  # noqa: PLC0415

    _key_and_jwt_gate(monkeypatch, _jwt_middleware())
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))

    response = TestClient(_whoami_app()).get("/whoami")

    assert response.status_code == 200, response.text
    assert response.json()["username"] == "alice"


def test_the_internal_key_with_an_admin_jwt_resolves_to_the_human_admin(monkeypatch):
    import auth_revocation  # noqa: PLC0415

    _key_and_jwt_gate(monkeypatch, _jwt_middleware())  # _JWT_USER carries role admin
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))

    response = TestClient(_whoami_app()).get("/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY})

    assert response.status_code == 200, response.text
    assert (response.json()["username"], response.json()["role"]) == ("alice", "admin")
    assert not response.json().get("service")


_SIGNING_SECRET = "s" * 40


def _real_jwt_middleware(real):
    """The real middleware, verifying with ``_SIGNING_SECRET`` -- no mocked decode."""
    cls = real.AuthenticationMiddleware
    middleware = cls.__new__(cls)
    middleware.jwt_secret = _SIGNING_SECRET
    middleware.jwt_public_key = None
    middleware.failed_attempts = {}
    middleware.enable_auth = True
    middleware.get_session = {}.get
    return middleware


@pytest.mark.parametrize("secret, expected", [("f" * 40, 401), (_SIGNING_SECRET, 200)])
def test_the_internal_key_with_a_forged_jwt_is_refused_by_real_verification(monkeypatch, secret, expected):
    """A forged signature fails the real verify_jwt_token; the correctly signed control passes."""
    import auth_revocation  # noqa: PLC0415
    from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE  # noqa: PLC0415
    from autobot_shared.auth.jwt_core import encode_jwt  # noqa: PLC0415
    from tests.conftest import load_real_auth_middleware  # noqa: PLC0415

    real = load_real_auth_middleware()
    _key_and_jwt_gate(monkeypatch, _real_jwt_middleware(real))
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))
    claims = {"username": "alice", "role": "admin", "user_id": str(uuid.uuid4()), "token_type": LOGIN_TOKEN_TYPE}
    token = encode_jwt(claims, secret=secret, expiry_hours=1)

    response = TestClient(_whoami_app(), raise_server_exceptions=False).get(
        "/whoami", headers={"X-Internal-API-Key": INTERNAL_KEY, "Authorization": f"Bearer {token}"}
    )

    assert response.status_code == expected, response.text
    assert not response.json().get("service")
