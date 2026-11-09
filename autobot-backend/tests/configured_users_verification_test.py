# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both authenticate_user entry points verify through one function (#21088)."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from autobot_shared.auth import configured_users as cu
from autobot_shared.auth.jwt_core import hash_password
from security_layer import SecurityLayer

STORED = hash_password("correct-value")
PLAIN = "unhashed-config-value"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _fresh_reports():
    cu._reported.clear()


def _layer(allowed):
    layer = object.__new__(SecurityLayer)
    layer.enable_auth = True
    layer.security_config = {"user_roles": {"alice": "developer"}}
    layer.allowed_users = cu.load_hashed_users(allowed)
    return layer


def _middleware(am, allowed):
    mw = object.__new__(am.AuthenticationMiddleware)
    mw.enable_auth = True
    mw.security_config = {"allowed_users": allowed}
    mw.is_account_locked = lambda username: False
    mw.reasons = []
    mw._handle_failed_login = lambda username, ip, reason: mw.reasons.append(reason)
    mw._build_successful_auth_response = lambda username, cfg, ip: {"username": username}
    return mw


def test_hashed_entry_authenticates_on_both(real_auth_middleware):
    allowed = {"alice": {"password_hash": STORED}}
    assert _layer(allowed).authenticate_user("alice", "correct-value") == "developer"
    assert _middleware(real_auth_middleware, allowed).authenticate_user("alice", "correct-value") == {
        "username": "alice"
    }


def test_wrong_password_fails_on_both(real_auth_middleware):
    allowed = {"alice": {"password_hash": STORED}}
    assert _layer(allowed).authenticate_user("alice", "wrong") is None
    assert _middleware(real_auth_middleware, allowed).authenticate_user("alice", "wrong") is None


@pytest.mark.parametrize("entry", [PLAIN, {"password_hash": PLAIN}])
def test_plaintext_entry_refused_on_both(real_auth_middleware, entry, caplog):
    allowed = {"alice": entry}
    with caplog.at_level(logging.ERROR):
        assert _layer(allowed).authenticate_user("alice", PLAIN) is None
        assert _middleware(real_auth_middleware, allowed).authenticate_user("alice", PLAIN) is None
    assert "alice" in caplog.text
    assert PLAIN not in caplog.text


def test_plaintext_reported_at_load(caplog):
    with caplog.at_level(logging.ERROR):
        assert cu.load_hashed_users({"alice": PLAIN}) == {}
    assert "alice" in caplog.text and PLAIN not in caplog.text


def test_both_entry_points_use_the_same_function(real_auth_middleware):
    allowed = {"alice": {"password_hash": STORED}}
    with patch("security_layer.verify_configured_user", return_value=allowed["alice"]) as a:
        _layer(allowed).authenticate_user("alice", "x")
    with patch.object(real_auth_middleware, "verify_configured_user", return_value=allowed["alice"]) as b:
        _middleware(real_auth_middleware, allowed).authenticate_user("alice", "x")
    assert a.call_count == 1 and b.call_count == 1


def test_canonical_hasher_is_the_verifier():
    entry = {"password_hash": STORED}
    with patch.object(cu, "verify_password", return_value=True) as spy:
        assert cu.verify_configured_user({"alice": entry}, "alice", "x") is entry
    spy.assert_called_once_with("x", STORED)


def test_unknown_user_still_costs_one_verification():
    with patch.object(cu, "verify_password", return_value=False) as spy:
        assert cu.verify_configured_user({}, "bob", "x") is None
    spy.assert_called_once_with("x", cu._placeholder_hash())
    assert cu._placeholder_hash().startswith("$2")


@pytest.mark.parametrize("bad", [None, "", "text", ["a"]])
def test_non_mapping_config_yields_no_users(bad):
    assert cu.load_hashed_users(bad) == {}


@pytest.mark.parametrize("bad", [None, "text", ["a"], 7])
def test_middleware_non_mapping_config_is_a_clean_failure(real_auth_middleware, bad):
    mw = _middleware(real_auth_middleware, bad)
    assert mw.authenticate_user("alice", "x") is None
    assert mw.reasons == ["user_not_found"]
    assert cu.verify_configured_user(bad, "alice", "x") is None


@pytest.mark.parametrize("stored", [None, 7, ["x"], {"a": 1}])
def test_non_str_password_hash_is_refused_with_its_own_reason(real_auth_middleware, stored):
    allowed = {"alice": {"password_hash": stored}}
    mw = _middleware(real_auth_middleware, allowed)
    assert mw.authenticate_user("alice", "x") is None
    assert mw.reasons == ["credential_not_hashed"]
    assert _layer(allowed).authenticate_user("alice", "x") is None


def test_empty_password_fails_on_both(real_auth_middleware):
    allowed = {"alice": {"password_hash": STORED}}
    assert _layer(allowed).authenticate_user("alice", "") is None
    mw = _middleware(real_auth_middleware, allowed)
    assert mw.authenticate_user("alice", "") is None
    assert mw.reasons == ["invalid_password"]


def test_failure_reasons():
    allowed = {"alice": {"password_hash": STORED}, "bob": PLAIN}
    assert cu.failure_reason(allowed, "alice") == "invalid_password"
    assert cu.failure_reason(allowed, "bob") == "credential_not_hashed"
    assert cu.failure_reason(allowed, "eve") == "user_not_found"


def test_rejected_entry_is_logged_once_per_user(caplog):
    allowed = {"alice": PLAIN}
    with caplog.at_level(logging.ERROR):
        for _ in range(3):
            cu.verify_configured_user(allowed, "alice", "x")
        cu.load_hashed_users(allowed)
    assert caplog.text.count("alice") == 1


def test_change_password_check_uses_the_shared_verifier():
    from fastapi import HTTPException

    from api import auth as api_auth

    allowed = {"alice": {"password_hash": STORED}, "bob": PLAIN}
    mw = SimpleNamespace(security_config={"allowed_users": allowed}, security_layer=Mock())
    with patch.object(api_auth, "get_auth_middleware", return_value=mw):
        with patch.object(api_auth, "verify_configured_user", wraps=cu.verify_configured_user) as spy:
            assert api_auth._verify_current_password("alice", "correct-value", "ip") == STORED
            assert spy.call_count == 1
        for user, pw, code in [("alice", "wrong", 401), ("bob", PLAIN, 401), ("eve", "x", 404)]:
            with pytest.raises(HTTPException) as exc:
                api_auth._verify_current_password(user, pw, "ip")
            assert exc.value.status_code == code
    mw.security_config = {"allowed_users": None}
    with patch.object(api_auth, "get_auth_middleware", return_value=mw):
        with pytest.raises(HTTPException) as exc:
            api_auth._verify_current_password("alice", "x", "ip")
        assert exc.value.status_code == 404
