# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A token minted for a purpose is not a login (#17049).

The backend accepted ANY HS256 token signed with the platform key as its
subject's ordinary login, whatever it was minted for. `_extract_user_from_jwt`
runs FIRST in `get_user_from_request`, ahead of the run-JWT and device-JWT
readers and their path allow-lists, so it answered before the guarded paths saw
the token:

- a **device JWT** authenticated as its owning user on every endpoint, bypassing
  the GH#9493 `/api/devices/` allow-list and its read-scope;
- an **SLM MFA-pending temp token** was a full login *before* the second factor
  — nothing in this service reads `mfa_pending`;
- a **service-to-service token** resolved to a role-`user` login.

The compatibility constraint that shapes the fix
------------------------------------------------
The obvious fix — reject unless `is_login_token(claims)` — **breaks login**.
That predicate requires a positive `token_type: login` claim, and only the
backend mints it (`auth_middleware.py`). Tokens from `autobot-slm-backend` carry
identity in `sub` and no `token_type` at all, and #12135 established those must
keep working. So the rule is a NEGATIVE check on purpose claims, and
`test_an_slm_login_token_is_still_accepted` is the test that would have caught
the naive version.
"""

from __future__ import annotations

import pathlib

import pytest

from autobot_shared.auth.interactive_principal import is_login_token, is_purpose_bound

# The four token shapes from #17049's table, plus the two that must keep working.
_BACKEND_LOGIN = {"sub": "alice", "username": "alice", "role": "user", "token_type": "login"}
_SLM_LOGIN = {"sub": "alice"}  # #12135: identity in `sub`, no token_type at all
_DEVICE_JWT = {"sub": "alice", "device_id": "dev-1", "scope": "read", "aud": "device"}
_MFA_PENDING = {"sub": "alice", "mfa_pending": True, "user_id": "u1", "admin": False}
_SERVICE = {"sub": "service:backend", "service": True}
_DEVICE_TOKEN_SERVICE = {"sub": "alice", "token_type": "device"}
_RUN_JWT = {"sub": "alice", "run_id": "r-1", "scope": "mcp"}


@pytest.mark.parametrize(
    ("name", "claims"),
    [
        ("device JWT", _DEVICE_JWT),
        ("SLM MFA-pending temp token", _MFA_PENDING),
        ("backend-to-SLM service token", _SERVICE),
        ("device-token-service token", _DEVICE_TOKEN_SERVICE),
        ("run JWT", _RUN_JWT),
    ],
)
def test_a_purpose_bound_token_is_not_a_login(name: str, claims: dict) -> None:
    assert is_purpose_bound(claims) is True, f"{name} must not authenticate as a login"


def test_a_backend_login_token_is_accepted() -> None:
    assert is_purpose_bound(_BACKEND_LOGIN) is False


def test_an_slm_login_token_is_still_accepted() -> None:
    """#12135. This is the test the naive fix fails.

    `is_login_token(_SLM_LOGIN)` is **False** — there is no `token_type` claim to
    satisfy it — so a gate written as `not is_login_token(...)` would refuse
    every SLM-issued login while looking entirely correct.
    """
    assert is_login_token(_SLM_LOGIN) is False, "premise: the positive predicate rejects this token"
    assert is_purpose_bound(_SLM_LOGIN) is False, "...and the negative one must still accept it"


def test_the_device_token_service_shape_needs_the_token_type_arm() -> None:
    """`token_type: device` carries no NON_LOGIN_CLAIMS member.

    Without the second arm of `is_purpose_bound`, the claim-set check alone
    would admit it — the row #17049 marked "not verified".
    """
    from autobot_shared.auth.interactive_principal import NON_LOGIN_CLAIMS

    assert NON_LOGIN_CLAIMS.isdisjoint(_DEVICE_TOKEN_SERVICE), "premise: no purpose CLAIM is present"
    assert is_purpose_bound(_DEVICE_TOKEN_SERVICE) is True


# ---------------------------------------------------------------------------
# The two extraction paths that consume it
# ---------------------------------------------------------------------------


def _load_real_auth_middleware():
    """Load `auth_middleware.py` by path, bypassing the testkit stub.

    The backend conftest replaces `auth_middleware` in `sys.modules` with
    `testkit/auth_middleware_stub.py`, which has no `_extract_user_from_jwt` —
    so an ordinary import here would test nothing, and #17343 tracks that
    harness gap. The module loads standalone, so these assert against the real
    extraction rather than a stand-in.
    """
    import importlib.util
    import sys

    backend = pathlib.Path(__file__).resolve().parents[2]
    for entry in (str(backend), str(backend.parent)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("_real_auth_middleware_17049", backend / "auth_middleware.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _middleware():
    module = _load_real_auth_middleware()
    return module.AuthenticationMiddleware.__new__(module.AuthenticationMiddleware)


class _Req:
    def __init__(self, token: str) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.cookies: dict = {}
        self.url = type("_U", (), {"path": "/api/anything"})()


@pytest.mark.parametrize("claims", [_DEVICE_JWT, _MFA_PENDING, _SERVICE], ids=["device", "mfa", "service"])
def test_the_http_path_refuses_a_purpose_bound_token(monkeypatch: pytest.MonkeyPatch, claims: dict) -> None:
    """`_extract_user_from_jwt` returns None so the guarded readers get their turn.

    Refusal here is a fall-through, not a dead end: `get_user_from_request` tries
    this, then the run-JWT reader, then the device-JWT reader.
    """
    mw = _middleware()
    monkeypatch.setattr(type(mw), "verify_jwt_token", lambda self, token: claims, raising=False)

    assert mw._extract_user_from_jwt(_Req("t")) is None


def test_the_http_path_still_accepts_an_slm_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive control. Without it, "refuses purpose-bound tokens" is
    indistinguishable from "refuses everything"."""
    mw = _middleware()
    monkeypatch.setattr(type(mw), "verify_jwt_token", lambda self, token: _SLM_LOGIN, raising=False)

    user = mw._extract_user_from_jwt(_Req("t"))

    assert user is not None
    assert user["username"] == "alice"
    assert user["auth_method"] == "jwt"
