# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SSO config field-level encryption helpers (GH#9501)."""

import base64
import os

import pytest


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    """Inject a deterministic 32-byte test key."""
    key = base64.urlsafe_b64encode(b"x" * 32).decode()
    monkeypatch.setenv("AUTOBOT_FIELD_ENCRYPTION_KEY", key)
    yield


from autobot_shared.field_encryption import (  # noqa: E402
    SSO_SENSITIVE_FIELDS,
    _ENCRYPTED_PREFIX,
    decrypt_sso_config,
    encrypt_sso_config,
    is_sso_config_encrypted,
)


class TestEncryptSsoConfig:
    def test_sensitive_fields_are_encrypted(self):
        cfg = {"client_id": "abc", "client_secret": "s3cr3t"}
        enc = encrypt_sso_config(cfg)
        assert enc["client_id"] == "abc"
        assert enc["client_secret"].startswith(_ENCRYPTED_PREFIX)
        assert enc["client_secret"] != "s3cr3t"

    def test_non_sensitive_fields_are_unchanged(self):
        cfg = {"auth_url": "https://example.com", "token_url": "https://t.example.com"}
        enc = encrypt_sso_config(cfg)
        assert enc == cfg

    def test_all_sensitive_field_names_are_handled(self):
        cfg = {f: "secret-value" for f in SSO_SENSITIVE_FIELDS}
        enc = encrypt_sso_config(cfg)
        for field in SSO_SENSITIVE_FIELDS:
            assert enc[field].startswith(_ENCRYPTED_PREFIX), field

    def test_idempotent_already_encrypted(self):
        cfg = {"client_secret": "plaintext"}
        enc1 = encrypt_sso_config(cfg)
        enc2 = encrypt_sso_config(enc1)
        assert enc1["client_secret"] == enc2["client_secret"]

    def test_missing_sensitive_field_not_added(self):
        cfg = {"client_id": "only"}
        enc = encrypt_sso_config(cfg)
        assert "client_secret" not in enc

    def test_none_value_skipped(self):
        cfg = {"client_secret": None}
        enc = encrypt_sso_config(cfg)
        assert enc["client_secret"] is None

    def test_empty_string_skipped(self):
        cfg = {"client_secret": ""}
        enc = encrypt_sso_config(cfg)
        assert enc["client_secret"] == ""


class TestDecryptSsoConfig:
    def test_roundtrip(self):
        original = {"client_id": "id", "client_secret": "mysecret", "bind_password": "pass"}
        assert decrypt_sso_config(encrypt_sso_config(original)) == original

    def test_plaintext_passthrough_backward_compat(self):
        """Rows written before encryption was enabled must still be readable."""
        cfg = {"client_secret": "legacy-plaintext", "client_id": "id"}
        assert decrypt_sso_config(cfg) == cfg

    def test_mixed_encrypted_and_plaintext(self):
        cfg = {"client_secret": _ENCRYPTED_PREFIX + "garbage"}
        # Should raise on bad ciphertext
        with pytest.raises(Exception):
            decrypt_sso_config(cfg)


class TestIsSsoConfigEncrypted:
    def test_returns_true_when_any_field_encrypted(self):
        cfg = {"client_secret": _ENCRYPTED_PREFIX + "data"}
        assert is_sso_config_encrypted(cfg) is True

    def test_returns_false_when_all_plaintext(self):
        cfg = {"client_secret": "plain", "client_id": "id"}
        assert is_sso_config_encrypted(cfg) is False

    def test_returns_false_for_empty_config(self):
        assert is_sso_config_encrypted({}) is False

    def test_returns_true_after_encrypt(self):
        cfg = {"client_secret": "s"}
        assert is_sso_config_encrypted(encrypt_sso_config(cfg)) is True
