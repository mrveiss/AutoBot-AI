# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for configured-user password verification (#21088)."""

import logging
from unittest.mock import patch

import pytest

import security_layer_credentials as creds
from autobot_shared.auth.jwt_core import hash_password
from security_layer import SecurityLayer

HASH = hash_password("correct-value")


def _layer(allowed, caplog=None):
    cfg = {"allowed_users": allowed, "user_roles": {"alice": "developer"}}
    with patch("security_layer.get_config_manager") as mgr:
        mgr.return_value.get.return_value = cfg
        with patch.object(SecurityLayer, "__init__", lambda self: None):
            layer = SecurityLayer()
    layer.enable_auth = True
    layer.security_config = cfg
    layer.allowed_users = creds.load_hashed_users(allowed)
    return layer


def test_hashed_entry_authenticates():
    assert _layer({"alice": HASH}).authenticate_user("alice", "correct-value") == "developer"


def test_password_hash_dict_entry_authenticates():
    layer = _layer({"alice": {"password_hash": HASH}})
    assert layer.authenticate_user("alice", "correct-value") == "developer"


def test_wrong_password_fails():
    assert _layer({"alice": HASH}).authenticate_user("alice", "wrong") is None


def test_unknown_user_fails():
    assert _layer({"alice": HASH}).authenticate_user("bob", "correct-value") is None


def test_plaintext_entry_rejected_at_load_and_reported(caplog):
    with caplog.at_level(logging.ERROR):
        layer = _layer({"alice": "plain-secret-value"})
    assert layer.allowed_users == {}
    assert "alice" in caplog.text
    assert "plain-secret-value" not in caplog.text
    assert layer.authenticate_user("alice", "plain-secret-value") is None


def test_plaintext_assigned_after_load_still_refused():
    layer = _layer({"alice": HASH})
    layer.allowed_users = {"alice": "plain-secret-value"}
    assert layer.authenticate_user("alice", "plain-secret-value") is None


def test_canonical_hasher_is_the_verifier():
    layer = _layer({"alice": HASH})
    with patch.object(creds, "verify_password", return_value=True) as spy:
        assert layer.authenticate_user("alice", "anything") == "developer"
    spy.assert_called_once_with("anything", HASH)


def test_unknown_user_still_runs_one_verification():
    with patch.object(creds, "verify_password", return_value=False) as spy:
        assert creds.verify_user_password({}, "bob", "x") is False
    assert spy.call_count == 1


def test_helper_output_authenticates(monkeypatch, capsys):
    monkeypatch.setattr(creds.getpass, "getpass", lambda prompt="": "operator-value")
    assert creds.main(["alice"]) == 0
    produced = capsys.readouterr().out.strip()
    assert _layer({"alice": produced}).authenticate_user("alice", "operator-value") == "developer"


def test_helper_rejects_mismatched_entries(monkeypatch):
    answers = iter(["one", "two"])
    monkeypatch.setattr(creds.getpass, "getpass", lambda prompt="": next(answers))
    assert creds.main(["alice"]) == 1


@pytest.mark.parametrize("bad", [None, "", "text", ["a"]])
def test_non_mapping_config_yields_no_users(bad):
    assert creds.load_hashed_users(bad) == {}
