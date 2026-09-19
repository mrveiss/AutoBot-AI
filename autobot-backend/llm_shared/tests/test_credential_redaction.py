# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for credential redaction (GH#9037)."""

from llm_shared.credential_redaction import (
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
