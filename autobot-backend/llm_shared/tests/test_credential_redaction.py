# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for credential redaction (GH#9037)."""

import pytest

from llm_shared.credential_redaction import (
    SENSITIVE_KEYS,
    redact_api_key,
    redact_dict,
    redact_string,
    safe_repr,
)


def test_redact_api_key():
    """Test API key redaction."""
    assert redact_api_key("sk-1234567890abcdef") == "sk-1...cdef"
    assert redact_api_key("short") == "***"
    assert redact_api_key("") == "***"


def test_redact_string():
    """Test string redaction for embedded API keys."""
    text = "Using API key sk-1234567890abcdefghij for requests"
    redacted = redact_string(text)
    assert "sk-1234567890abcdefghij" not in redacted
    assert "Using API key" in redacted


def test_redact_dict_simple():
    """Test dictionary redaction."""
    data = {
        "api_key": "sk-secret123456",
        "model": "gpt-4",
        "temperature": 0.7,
    }

    redacted = redact_dict(data)
    assert redacted["model"] == "gpt-4"
    assert redacted["temperature"] == 0.7
    assert "secret123456" not in str(redacted["api_key"])


def test_redact_dict_nested():
    """Test nested dictionary redaction."""
    data = {
        "provider": "anthropic",
        "settings": {
            "api_key": "sk-nested-secret",
            "base_url": "https://api.example.com",
        },
    }

    redacted = redact_dict(data)
    assert redacted["provider"] == "anthropic"
    assert redacted["settings"]["base_url"] == "https://api.example.com"
    assert "nested-secret" not in str(redacted["settings"]["api_key"])


def test_redact_dict_variations():
    """Test various key name variations."""
    data = {
        "api_key": "secret1",
        "apiKey": "secret2",
        "api-key": "secret3",
        "bearer_token": "secret4",
        "password": "secret5",
        "safe_value": "visible",
    }

    redacted = redact_dict(data)
    # All sensitive keys should be redacted
    for key in ["api_key", "apiKey", "api-key", "bearer_token", "password"]:
        assert "secret" not in str(redacted.get(key, ""))

    # Non-sensitive key should remain
    assert redacted["safe_value"] == "visible"


def test_safe_repr():
    """Test safe repr with redaction."""
    obj = {
        "api_key": "sk-dangerous",
        "nested": {
            "token": "bearer-xyz",
        },
    }

    repr_str = safe_repr(obj)
    assert "dangerous" not in repr_str
    assert "bearer-xyz" not in repr_str
    assert "api_key" in repr_str


# ---------------------------------------------------------------------------
# #13708: redact_string also catches free-text shapes API_KEY_PATTERNS never
# covered, via the cross-service content scanner (autobot_shared.secret_redaction).
# ---------------------------------------------------------------------------


def test_redact_string_catches_a_password_stated_in_prose():
    text = "Welcome! Your temporary password is Xy9#mK2!Zq. Please change it after login."
    redacted = redact_string(text)
    assert "Xy9#mK2!Zq" not in redacted
    assert "Welcome!" in redacted
    assert "Please change it after login." in redacted


def test_redact_string_catches_a_pem_private_key_block():
    pem = "\n".join(
        [
            "-----BEGIN " + "RSA PRIVATE KEY-----",
            "MIIBOgIBAAJBAK...",
            "-----END " + "RSA PRIVATE KEY-----",
        ]
    )
    text = f"Attached is our key:\n{pem}\nKeep it safe."
    redacted = redact_string(text)
    assert "MIIBOgIBAAJBAK" not in redacted
    assert "Keep it safe." in redacted


def test_redact_string_catches_a_basic_auth_url():
    text = "Connect via https://admin:sup3rSecret1@db.example.com:5432/mydb for the migration."
    redacted = redact_string(text)
    assert "sup3rSecret1" not in redacted
    assert "for the migration." in redacted


def test_redact_string_leaves_an_ordinary_sentence_untouched():
    text = "Hi team, the standup is moved to 10am tomorrow. Thanks, Alice."
    assert redact_string(text) == text


def test_redact_string_does_not_quarantine_a_forwarded_code_snippet():
    text = "import os\napi_key = os.environ.get('SOME_KEY')\ndef getKey():\n    return apiKey"
    assert redact_string(text) == text


# ---------------------------------------------------------------------------
# #16688: SENSITIVE_KEYS is derived from the shared vocabulary, not hand-copied.
# The derivation must only ever WIDEN. A redaction consolidation that narrows
# is a silent under-redaction, and nothing else in this suite would catch it.
# ---------------------------------------------------------------------------

# The literal set this module carried before the vocabulary was shared. Kept
# here deliberately as a frozen historical record -- it is the thing the union
# must never lose, so it must not be imported from the module under test.
_PRE_16688_SENSITIVE_KEYS = frozenset(
    {"apikey", "token", "bearer", "password", "secret", "credential", "auth", "authorization"}
)


def _normalized(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def _is_sensitive(key: str) -> bool:
    return any(fragment in _normalized(key) for fragment in SENSITIVE_KEYS)


def test_derived_vocabulary_still_covers_every_key_the_literal_set_covered() -> None:
    """Every pre-#16688 fragment must still match, or something stopped being redacted."""
    lost = sorted(f for f in _PRE_16688_SENSITIVE_KEYS if not _is_sensitive(f))
    assert not lost, f"these stopped being treated as sensitive: {lost}"


@pytest.mark.parametrize(
    "key",
    [
        # The authorization terms the shared suffix vocabulary does NOT carry --
        # a straight replacement would have dropped all three.
        "Authorization",
        "auth_header",
        "x_auth",
        "bearer_token",
        # Carried by the shared vocabulary.
        "api_key",
        "client_secret",
        "db_password",
        "session_token",
        # Gained from the shared vocabulary; previously missed here.
        "tls_cert",
        "db_dsn",
        "hmac_signature",
        "private_pem",
        "random_seed",
        "salt_value",
        "passphrase",
    ],
)
def test_a_sensitive_key_is_redacted(key: str) -> None:
    out = redact_dict({key: "sup3rSecretValue1234567890"})
    assert "sup3rSecretValue1234567890" not in str(out), f"{key} leaked its value"


@pytest.mark.parametrize("key", ["user_name", "model", "temperature", "message_count", "status"])
def test_an_ordinary_key_keeps_its_value(key: str) -> None:
    """The union widens the sensitive set, so guard the false-positive side too."""
    assert redact_dict({key: "plain-value"})[key] == "plain-value"
