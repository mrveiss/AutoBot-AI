# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
