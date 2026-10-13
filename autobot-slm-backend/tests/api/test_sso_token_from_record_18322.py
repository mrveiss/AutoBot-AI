# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO completion mints its token from the provisioned User record (#18322).

All three completion paths (OAuth callback, LDAP login, SAML callback) built a stand-in
``type("User", (), {"username", "is_admin"})()`` and passed it to
``create_token_response``, which reads ``is_platform_admin``: an ``AttributeError``
that no ``except`` caught, so an SSO login never completed. The existing SSO tests
mocked ``auth_service`` and could not see it. Here the REAL ``create_token_response``
runs, and the role it signs is read from ``create_access_token``'s payload.

The user objects are ``SimpleNamespace``s carrying only what a record carries, so a
missing attribute raises instead of auto-vivifying as a ``MagicMock`` would.
"""

import asyncio
import secrets
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from test_sso_auth import _load_sso_auth_with_real_endpoints, _make_mock_request  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))


class _SSOAuthError(Exception):
    """Stands in for SSOAuthenticationError so the endpoints' except tuples stay valid."""


def _record(is_platform_admin: bool) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), username="sso-user", is_platform_admin=is_platform_admin)


def _service(user=None, error: Exception | None = None) -> MagicMock:
    outcome = {"side_effect": error} if error else {}
    service = MagicMock()
    service.complete_oauth_login = AsyncMock(return_value=(user, uuid.uuid4()), **outcome)
    service.authenticate_ldap = AsyncMock(return_value=user, **outcome)
    service.complete_saml_login = AsyncMock(return_value=(user, uuid.uuid4()), **outcome)
    service._validate_oauth_state = AsyncMock(return_value=(uuid.uuid4(), None))
    return service


async def _complete(sso_auth, path: str):
    audit_db = MagicMock(commit=AsyncMock())
    response = MagicMock(headers={})
    if path == "oauth":
        request = _make_mock_request("http", "localhost", {"x-forwarded-host": "localhost"})
        return await sso_auth.oauth_callback(
            request=request, response=response, code="c", state="s", db=MagicMock(), audit_db=audit_db
        )
    if path == "ldap":
        login = SimpleNamespace(username="sso-user", password="pw", provider_id=uuid.uuid4())  # nosec B106
        return await sso_auth.ldap_login(login_data=login, response=response, db=MagicMock(), audit_db=audit_db)
    return await sso_auth.saml_callback(SAMLResponse="x", RelayState="s", db=MagicMock(), audit_db=audit_db)


def _run(path: str, service: MagicMock):
    """Complete an SSO login through *path*; return the payloads the real auth service signed."""
    sso_auth, _ = _load_sso_auth_with_real_endpoints()
    with (
        patch.object(sso_auth, "create_audit_log", AsyncMock()),
        patch.object(sso_auth, "SSOService", MagicMock(return_value=service)),
        patch.object(sso_auth, "SSOAuthenticationError", _SSOAuthError),
        patch.object(sso_auth, "SSOProviderNotFoundError", _SSOAuthError),
        patch.object(sso_auth, "auth_service", _auth.auth_service),
        patch.object(_auth.auth_service, "create_access_token", wraps=_auth.auth_service.create_access_token) as mint,
    ):
        try:
            asyncio.run(_complete(sso_auth, path))
        except Exception as exc:  # the 401 path raises the harness's HTTPException stand-in
            if not hasattr(exc, "status_code"):
                raise
    return [call.kwargs["data"] for call in mint.call_args_list]


@pytest.mark.parametrize("path", ["oauth", "ldap", "saml"])
@pytest.mark.parametrize(("is_admin", "role"), [(False, "user"), (True, "admin")])
def test_the_token_role_comes_from_the_record(path, is_admin, role):
    (payload,) = _run(path, _service(user=_record(is_admin)))
    assert payload["role"] == role and payload["admin"] is is_admin and payload["sub"] == "sso-user"


@pytest.mark.parametrize("path", ["oauth", "ldap", "saml"])
def test_an_identity_the_service_refuses_gets_no_token(path):
    """Unprovisioned or JIT-refused: the service raises, and nothing is minted."""
    assert _run(path, _service(error=_SSOAuthError("not provisioned"))) == []


def test_contrast_the_old_stand_in_cannot_mint():
    stand_in = type("User", (), {"username": "sso-user", "is_admin": False})()
    with pytest.raises(AttributeError, match="is_platform_admin"):
        asyncio.run(_auth.auth_service.create_token_response(stand_in))
