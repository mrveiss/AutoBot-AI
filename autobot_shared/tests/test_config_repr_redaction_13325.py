# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests: config ``repr()`` must never carry credential values (#13325).

A misspelled ``patch.object(config.misc, ...)`` raises an ``AttributeError``
whose message embeds ``repr()`` of the settings object.  Before the fix that
dumped the whole configuration — ``jwt_secret`` and ``secret_key`` included —
into pytest output and therefore into public CI logs.

These tests deliberately compute leak checks into booleans before asserting, so
that a *failing* assertion still never prints the secret it is guarding.
"""

from unittest.mock import patch

import pytest

from autobot_shared.secret_redaction import (
    REDACTED_PLACEHOLDER,
    is_credential_field,
    redact_value,
)
from autobot_shared.ssot_config import RedactedSettings, get_config

# Obvious non-secret stand-ins. Never put a real credential in a fixture.
FAKE_SECRET = "placeholder-not-a-real-secret-13325"


class _SampleSettings(RedactedSettings):
    """Minimal model exercising credential and non-credential field shapes."""

    jwt_secret: str = ""
    searxng_basic_auth_pass: str = ""
    tls_key_path: str = ""
    speculation_num_tokens: str = ""


class TestCredentialFieldClassification:
    @pytest.mark.parametrize(
        "name",
        [
            "jwt_secret",
            "secret_key",
            "openai_api_key",
            "admin_password",
            "hf_token",
            "master_key",
            "password",
            "api_key",
            "redis.password".split(".")[-1],
            "searxng_basic_auth_pass",
            "google_oauth_client_secret",
        ],
    )
    def test_credential_names_are_detected(self, name):
        assert is_credential_field(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            # Substring matches that are NOT credentials — the reason suffix
            # matching is used instead of ``in``.
            "tokenizers_parallelism",
            "speculation_num_tokens",
            "llm_key_rotation_grace_secs",
            "service_auth_rate_limit_max_failures",
            # Locations pointing at a credential are not the credential.
            "tls_key_path",
            "service_key_file",
            "vnc_passwd_file",
            "ssh_key_path",
            # Public identifiers.
            "google_oauth_client_id",
            "searxng_basic_auth_user",
        ],
    )
    def test_non_credential_names_are_left_alone(self, name):
        assert is_credential_field(name) is False


class TestRedactValue:
    def test_populated_credential_is_masked(self):
        assert redact_value("jwt_secret", FAKE_SECRET) == REDACTED_PLACEHOLDER

    def test_unset_credential_is_shown_verbatim(self):
        """Unset is diagnosable and leaks nothing — do not mask it."""
        assert redact_value("jwt_secret", "") == ""
        assert redact_value("jwt_secret", None) is None

    def test_non_credential_untouched(self):
        assert redact_value("tls_key_path", "/etc/example/tls.key") == "/etc/example/tls.key"

    def test_mask_width_is_fixed(self):
        """The mask must not disclose the length of the real value."""
        short = redact_value("api_key", "ab")
        long = redact_value("api_key", "ab" * 100)
        assert short == long == REDACTED_PLACEHOLDER


class TestRedactedRepr:
    def test_field_name_preserved_and_value_masked(self):
        model = _SampleSettings(jwt_secret=FAKE_SECRET, searxng_basic_auth_pass=FAKE_SECRET)
        text = repr(model)
        assert "jwt_secret" in text, "field NAME must stay visible for diagnosis"
        assert "searxng_basic_auth_pass" in text
        assert FAKE_SECRET not in text
        assert REDACTED_PLACEHOLDER in text

    def test_non_credential_values_still_readable(self):
        model = _SampleSettings(tls_key_path="/etc/example/tls.key", speculation_num_tokens="4")
        text = repr(model)
        assert "/etc/example/tls.key" in text
        assert "speculation_num_tokens='4'" in text

    def test_str_is_redacted_too(self):
        model = _SampleSettings(jwt_secret=FAKE_SECRET)
        assert FAKE_SECRET not in str(model)

    def test_class_var_is_not_collected_as_a_settings_field(self):
        """NON_CREDENTIAL_FIELDS must stay a ClassVar, not become config."""
        assert "NON_CREDENTIAL_FIELDS" not in _SampleSettings.model_fields
        assert "NON_CREDENTIAL_FIELDS" not in repr(_SampleSettings())

    def test_non_credential_override_keeps_value_visible(self):
        """A path *to* a key is not a key — models may opt fields out."""

        class _PkiLike(RedactedSettings):
            NON_CREDENTIAL_FIELDS = frozenset({"ca_key"})
            ca_key: str = ""
            signing_key: str = ""

        text = repr(_PkiLike(ca_key="certs/ca/ca-key.pem", signing_key=FAKE_SECRET))
        assert "certs/ca/ca-key.pem" in text
        assert FAKE_SECRET not in text

    def test_attribute_access_returns_the_real_value(self):
        """Redaction is display-only — read sites must be unaffected."""
        model = _SampleSettings(jwt_secret=FAKE_SECRET)
        assert model.jwt_secret == FAKE_SECRET
        assert model.model_dump()["jwt_secret"] == FAKE_SECRET


def _credential_values(model) -> list[tuple[str, str]]:
    """Collect populated credential values from a settings model."""
    found = []
    for name in type(model).model_fields:
        value = getattr(model, name, None)
        if isinstance(value, str) and len(value) >= 8 and is_credential_field(name):
            found.append((name, value))
    return found


class TestLiveConfigNeverLeaks:
    """The actual regression guard, run against the real loaded config."""

    def test_repr_of_every_section_hides_credential_values(self):
        cfg = get_config()
        leaked = []
        for section in type(cfg).model_fields:
            model = getattr(cfg, section, None)
            if not hasattr(type(model), "model_fields"):
                continue
            text = repr(model)
            leaked += [f"{section}.{n}" for n, v in _credential_values(model) if v in text]
        # Only field NAMES are reported — never the values they hold.
        assert leaked == [], f"credential values present in repr(): {leaked}"

    def test_patch_object_typo_does_not_leak(self):
        """The exact reported vector: a typo'd patch target (#13325)."""
        cfg = get_config()
        message = ""
        with pytest.raises(AttributeError) as excinfo:
            with patch.object(cfg.misc, "definitely_not_a_real_config_field", "x"):
                pass
        message = str(excinfo.value)
        leaked = [n for n, v in _credential_values(cfg.misc) if v in message]
        assert leaked == [], f"credential values present in AttributeError: {leaked}"
        assert "jwt_secret" in message, "field names must survive so failures stay diagnosable"
