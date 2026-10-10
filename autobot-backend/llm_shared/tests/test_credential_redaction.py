# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for credential redaction (GH#9037)."""

from pathlib import Path

import pytest

from autobot_shared.secret_redaction import REDACTED_PLACEHOLDER, redact_nested
from llm_shared.credential_redaction import (
    SENSITIVE_KEYS,
    redact_api_key,
    redact_dict,
    redact_string,
    safe_repr,
)


def test_redact_api_key():
    """No part of a key survives, whatever its length (#18205)."""
    assert redact_api_key("sk-1234567890abcdef") == REDACTED_PLACEHOLDER
    assert redact_api_key("short") == REDACTED_PLACEHOLDER
    assert redact_api_key("") == REDACTED_PLACEHOLDER


def test_redact_string():
    """Test string redaction for embedded API keys."""
    text = "Using API key sk-1234567890abcdefghij for requests"
    redacted = redact_string(text)
    assert "sk-1234567890abcdefghij" not in redacted
    assert "Using API key" in redacted
    # #18205: neither end of the key is revealed.
    assert "sk-1" not in redacted and "ghij" not in redacted
    assert REDACTED_PLACEHOLDER in redacted


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


def test_redact_dict_still_masks_a_count_of_a_credential_noun() -> None:
    # origin/main masked max_tokens here (normalized substring match); only the template
    # export unmasks a count (#17337 AC2: nothing leaves the masked set).
    assert redact_dict({"max_tokens": 4096, "retries": 3}) == {"max_tokens": REDACTED_PLACEHOLDER, "retries": 3}


# ---------------------------------------------------------------------------
# #18205: redact_dict is a thin composition over redact_nested. A credential is masked with the
# fixed-width placeholder (no fragment of the secret), and no caller's masked set shrinks.
# ---------------------------------------------------------------------------

_SECRET = "sk-" + "Zq7" * 8  # pragma: allowlist secret
_CORPUS = Path(__file__).resolve().parents[3] / "autobot_shared" / "redaction_corpus_17336.txt"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"  # pragma: allowlist secret


def test_a_credential_string_is_masked_with_the_fixed_width_placeholder_not_a_fragment() -> None:
    out = redact_dict({"api_key": _SECRET, "nested": {"password": "hunter2hunter2"}, "rows": [{"token": _SECRET}]})
    assert out == {
        "api_key": REDACTED_PLACEHOLDER,
        "nested": {"password": REDACTED_PLACEHOLDER},
        "rows": [{"token": REDACTED_PLACEHOLDER}],
    }
    assert _SECRET[:4] not in str(out) and _SECRET[-4:] not in str(out)


def test_redact_dict_still_scans_the_content_of_a_non_credential_string() -> None:
    """replay_service relies on this: a key pasted into prose, and the 32+ character generic pattern."""
    generic = "a1B2" * 9  # 36 alphanumerics, low entropy: only API_KEY_PATTERNS catches it
    out = redact_dict({"note": f"use {_SECRET} here", "blob": generic, "model": "gpt-4"})
    assert _SECRET not in out["note"] and "use " in out["note"]
    assert out["blob"] != generic
    assert out["model"] == "gpt-4"


def test_redact_dict_recurses_into_tuples_and_sets_the_old_walk_skipped() -> None:
    out = redact_dict({"rows": ({"api_key": _SECRET},), "s": {"x"}})
    assert out["rows"] == ({"api_key": REDACTED_PLACEHOLDER},)
    assert out["s"] == ["x"]


def test_redact_nested_count_rule_is_an_explicit_keyword() -> None:
    assert redact_nested({"max_tokens": 4096}) == {"max_tokens": 4096}
    assert redact_nested({"max_tokens": 4096}, exempt_counts=False) == {"max_tokens": REDACTED_PLACEHOLDER}
    plain = "hello"
    assert redact_nested({"a": plain}, extra_scan=str.upper) == {"a": "HELLO"}
    assert redact_nested({"api_key": plain}, extra_scan=str.upper) == {"api_key": REDACTED_PLACEHOLDER}


@pytest.mark.parametrize("name", ["webhook_secret_url", "api_key_url", "token_url", "auth_url", "oauth_token_endpoint"])
def test_redact_dict_masks_every_credential_named_url_whole_where_redact_nested_scrubs_an_endpoint(name) -> None:
    """The no-shrink layer: base masked these whole, so the URL (a webhook path IS the secret) never comes back."""
    url = "https://hooks.example.com/services/T0/B0/AbCdEfGh"
    assert redact_dict({name: url}) == {name: REDACTED_PLACEHOLDER}
    assert redact_nested({"token_url": url}) == {"token_url": url}


_BASE_MASKED = Path(__file__).with_name("redact_dict_base_masked_names_f0c9745f32.txt")
_HOOK_URL = "https://hooks.example.com/services/T0/B0/AbCdEfGh"  # a webhook whose path IS the secret
_ENDPOINT_URL = "https://auth.example.com/oauth/token"


def _base_masked_names() -> list:
    """Names base (f0c9745f32, before #18205) masked: pinned DATA, so vocabulary drift cannot move the 'before'."""
    lines = _BASE_MASKED.read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if ln and not ln.startswith("#")]


@pytest.mark.parametrize(
    "value",
    [1, 4.5, "4821", _JWT, True, _SECRET, _HOOK_URL, _ENDPOINT_URL],
    ids=lambda v: type(v).__name__ + str(v)[:12],
)
def test_no_name_leaves_redact_dicts_masked_set(value) -> None:
    """#17336 per-caller method, end to end: masked on main (value changed) and unmasked now is empty."""
    names = _CORPUS.read_text(encoding="utf-8").split()
    assert len(names) > 3000
    base_masked = _base_masked_names()
    assert len(base_masked) > 2000 and set(base_masked) <= set(names)
    gone = [n for n in base_masked if redact_dict({n: value})[n] == value]
    assert gone == [], gone[:20]
    leaked = [
        n
        for n in names
        if isinstance(value, str)
        and len(value) > 8
        and redact_dict({n: value})[n] != value
        and value[:4] in str(redact_dict({n: value})[n])
    ]
    assert leaked == [], leaked[:20]
