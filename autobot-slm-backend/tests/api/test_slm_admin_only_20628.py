# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20628: the SLM is a server admin panel, for admins only, on every way in."""

import secrets
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _real_auth_import import load_real_auth  # noqa: E402
from fastapi import HTTPException

_ROOT = Path(__file__).resolve().parents[2]


_REAL_AUTH = load_real_auth(secrets.token_hex(32))


def _auth():
    return _REAL_AUTH


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"admin": True}, True),
        ({"role": "admin"}, True),
        ({"role": "superadmin"}, True),
        ({"admin": False, "role": "user"}, False),
        ({"role": "operator"}, False),
        ({"sub": "says-nothing"}, False),
    ],
)
def test_only_an_admin_token_is_an_admin_session(payload, expected) -> None:
    assert _auth().is_admin_session(payload) is expected


@pytest.mark.asyncio
async def test_no_session_is_issued_to_a_non_admin() -> None:
    auth = _auth()
    user = SimpleNamespace(username="u", is_platform_admin=False)
    with pytest.raises(HTTPException) as refused:
        await auth.auth_service.create_token_response(user)
    assert refused.value.status_code == 403


def _source(path: str) -> str:
    return (_ROOT / path).read_text(encoding="utf-8")


def test_password_login_refuses_before_any_mfa_challenge() -> None:
    source = _source("api/auth.py")
    assert source.index("await _refuse_non_admin(") < source.index('action="mfa_challenge_issued"')


def test_sso_redirects_a_non_admin_with_a_reason() -> None:
    source = _source("api/sso_auth.py")
    assert source.index("error=admin_only") < source.index("create_token_response(user)")


def test_the_websocket_applies_the_same_rule() -> None:
    assert "is_admin_session(payload)" in _source("api/websocket.py")


def test_sso_and_ldap_share_the_audit_that_records_a_refusal_as_a_failure() -> None:
    source = _source("api/sso_auth.py")
    assert source.count("await _audit_sso_login(audit_db, user, provider_id_str") == 2
    assert "success=bool(user.is_platform_admin)" in source
    assert "success=True" not in source[source.index("async def oauth_callback") :].split("except (SSO")[0]
