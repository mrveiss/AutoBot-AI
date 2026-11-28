# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Field sealing is bound to where the value is stored, and fails closed (#17981)."""

import base64
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from autobot_shared.field_encryption import (
    FieldDecryptionError,
    decrypt_field,
    encrypt_field,
    is_legacy_ciphertext,
    open_tagged,
    seal_tagged,
)


@pytest.fixture(autouse=True)
def _root_key(monkeypatch):
    monkeypatch.setenv("AUTOBOT_SECRETS_ROOT_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    monkeypatch.delenv("AUTOBOT_FIELD_ENCRYPTION_KEY", raising=False)


def _legacy_blob(key: bytes, plaintext: bytes) -> str:
    """A value as the pre-#17981 code sealed it: nonce || ciphertext, no AAD."""
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, plaintext, None)).decode()


def test_a_sealed_value_round_trips_in_its_own_context():
    blob = encrypt_field("s3cret", context="organization:a:external_pm_config")
    assert not is_legacy_ciphertext(blob)
    assert decrypt_field(blob, context="organization:a:external_pm_config") == "s3cret"


def test_a_sealed_value_moved_to_another_record_does_not_open():
    blob = encrypt_field("s3cret", context="organization:a:external_pm_config")
    with pytest.raises(FieldDecryptionError, match="organization:b:external_pm_config"):
        decrypt_field(blob, context="organization:b:external_pm_config")


def test_a_sealed_value_moved_to_another_field_does_not_open():
    blob = encrypt_field("s3cret", context="redis:k1")
    with pytest.raises(FieldDecryptionError):
        decrypt_field(blob, context="redis:k2")


def test_an_empty_context_is_refused_at_seal_time():
    with pytest.raises(ValueError):
        encrypt_field("s3cret", context="")


def test_a_legacy_value_still_reads_while_its_key_is_set(monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("AUTOBOT_FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode())
    blob = _legacy_blob(key, b"old")
    assert is_legacy_ciphertext(blob)
    assert decrypt_field(blob, context="redis:k1") == "old"


def test_a_legacy_value_without_its_key_is_an_error_naming_the_field():
    blob = _legacy_blob(os.urandom(32), b"old")
    with pytest.raises(FieldDecryptionError, match="redis:k1.*AUTOBOT_FIELD_ENCRYPTION_KEY"):
        decrypt_field(blob, context="redis:k1")


@pytest.mark.parametrize("stored", ["fe1.AAAA", "fe1.!!!", "not-base64-%%%", ""])
def test_an_unreadable_value_raises_never_returns_empty(stored):
    with pytest.raises(FieldDecryptionError, match="redis:k1"):
        decrypt_field(stored, context="redis:k1")


def test_a_missing_root_key_is_an_error_not_an_empty_value(monkeypatch):
    blob = encrypt_field("s3cret", context="redis:k1")
    monkeypatch.delenv("AUTOBOT_SECRETS_ROOT_KEY")
    with pytest.raises(FieldDecryptionError, match="redis:k1"):
        decrypt_field(blob, context="redis:k1")


def test_tagged_values_pass_plaintext_through_and_seal_the_rest():
    assert open_tagged("plain", context="redis:k1") == "plain"
    tagged = seal_tagged("s3cret", context="redis:k1")
    assert tagged.startswith("enc:fe1.")
    assert open_tagged(tagged, context="redis:k1") == "s3cret"
    with pytest.raises(FieldDecryptionError):
        open_tagged(tagged, context="redis:k2")


def test_the_field_key_is_its_own_domain_not_a_vault_key():
    """#17981 review: separation must not depend on how vault ids parse."""
    from autobot_shared import secrets_envelope as env

    root = env.load_root_key()
    field_key = env._field_key()
    assert field_key != env.derive_vault_key(root, "field-encryption"), "same key as a vault named like it"
    assert field_key != env.derive_vault_key(root, "system"), "same key as a real vault KEK"
    assert len(field_key) == 32
    blob = encrypt_field("s3cret", context="redis:k1")
    assert decrypt_field(blob, context="redis:k1") == "s3cret"
