# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both authenticate_user entry points verify through one function (#21088)."""

import logging
from unittest.mock import patch

import pytest

from autobot_shared.auth import configured_users as cu
from autobot_shared.auth.jwt_core import hash_password
from security_layer import SecurityLayer

STORED = hash_password("correct-value")
PLAIN = "unhashed-config-value"  # pragma: allowlist secret


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
    mw._handle_failed_login = lambda *a, **k: None
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
    assert spy.call_count == 1


@pytest.mark.parametrize("bad", [None, "", "text", ["a"]])
def test_non_mapping_config_yields_no_users(bad):
    assert cu.load_hashed_users(bad) == {}
