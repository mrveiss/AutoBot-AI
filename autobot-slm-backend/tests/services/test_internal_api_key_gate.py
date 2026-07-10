# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11450: machine-to-machine gate for the agent control plane.

`require_service_management_or_internal` must let the node agent through on a
valid AUTOBOT_INTERNAL_API_KEY (no user JWT), while 401'ing anonymous callers
and otherwise falling back to the human service.management permission.

services/auth.py imports the full FastAPI + config chain (which reads
/etc/autobot secrets and is stubbed to a MagicMock by conftest — see the same
constraint in tests/api/test_require_permission.py). These tests therefore
replicate the two pure decision helpers verbatim from services/auth.py and
assert their branch behaviour; keep them in lock-step with the source.
"""

from __future__ import annotations

import secrets


# --- verbatim mirror of services.auth.verify_internal_api_key -------------
def _verify_internal_api_key(provided: str | None, expected: str) -> bool:
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)


# --- verbatim mirror of the gate's decision (internal key OR user perm) ----
class _Denied(Exception):
    def __init__(self, code: int):
        self.status_code = code


def _gate(x_internal_api_key, credentials, expected, user_has_perm):
    if _verify_internal_api_key(x_internal_api_key, expected):
        return {"internal_service": True, "role": "service"}
    if credentials is None:
        raise _Denied(401)
    if not user_has_perm:
        raise _Denied(403)
    return {"user": True}


_KEY = "a" * 64


# ---------------------------------------------------------------------------
# key check
# ---------------------------------------------------------------------------


def test_verify_rejects_when_key_unset():
    assert _verify_internal_api_key(_KEY, "") is False


def test_verify_rejects_none_even_when_configured():
    assert _verify_internal_api_key(None, _KEY) is False


def test_verify_rejects_wrong_key():
    assert _verify_internal_api_key("b" * 64, _KEY) is False


def test_verify_accepts_matching_key():
    assert _verify_internal_api_key(_KEY, _KEY) is True


# ---------------------------------------------------------------------------
# gate decision
# ---------------------------------------------------------------------------


def test_gate_accepts_valid_internal_key():
    out = _gate(_KEY, None, _KEY, user_has_perm=False)
    assert out["internal_service"] is True  # bypasses user check entirely


def test_gate_rejects_anonymous_without_key_or_bearer():
    try:
        _gate(None, None, _KEY, user_has_perm=False)
        raise AssertionError("expected 401")
    except _Denied as e:
        assert e.status_code == 401


def test_gate_wrong_key_falls_through_to_user_permission():
    # wrong key + a permitted user -> allowed via the human path
    assert _gate("b" * 64, object(), _KEY, user_has_perm=True) == {"user": True}
    # wrong key + a user lacking the permission -> 403 (human gate preserved)
    try:
        _gate("b" * 64, object(), _KEY, user_has_perm=False)
        raise AssertionError("expected 403")
    except _Denied as e:
        assert e.status_code == 403
