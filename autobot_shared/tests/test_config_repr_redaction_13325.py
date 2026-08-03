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

import re
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
    tokenizers_parallelism: str = ""


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
        model = _SampleSettings(tls_key_path="/etc/example/tls.key", tokenizers_parallelism="false")
        text = repr(model)
        assert "/etc/example/tls.key" in text
        assert "tokenizers_parallelism='false'" in text

    def test_str_is_redacted_too(self):
        model = _SampleSettings(jwt_secret=FAKE_SECRET)
        assert FAKE_SECRET not in str(model)

    def test_count_field_is_exempted_at_the_model_level(self):
        """``speculation_num_tokens`` matches the ``tokens`` plural but is a count.

        The plural stays in the classifier so a future ``api_keys`` cannot fail
        open; the false positive is resolved explicitly, not by weakening it.
        """
        from autobot_shared.ssot_config import MiscConfig

        assert is_credential_field("speculation_num_tokens") is True
        assert "speculation_num_tokens" in MiscConfig.NON_CREDENTIAL_FIELDS

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




# ---------------------------------------------------------------------------
# Ground-truth regression guard
#
# These lists are written out by hand from the credential audit.  They are
# deliberately NOT derived from is_credential_field(): a guard that asks the
# classifier what counts as a credential can only ever confirm what the
# classifier already believes, and would report zero leaks while database_url
# was leaking its password (#13325 review).
# ---------------------------------------------------------------------------

#: section -> field names whose value must never appear in repr().
MUST_BE_MASKED = {
    "auth": [
        "admin_password",
        "google_oauth_client_secret",
        "microsoft_oauth_client_secret",
        "gitlab_oauth_client_secret",
    ],
    "llm": [
        "openai_api_key",
        "anthropic_api_key",
        "brave_search_api_key",
        "searxng_token",
        "searxng_basic_auth_pass",
    ],
    "redis": ["password"],
    "misc": [
        "jwt_secret",
        "run_jwt_secret",
        "jwt_private_key",
        "jwt_public_key",
        "secret_key",
        "secrets_key",
        "encryption_key",
        "master_key",
        "internal_api_key",
        "api_key",
        "service_key",
        "mcp_token",
        "slm_auth_token",
        "chromadb_auth_token",
        "service_auth_override_token",
        "postgres_password",
        "database_password",
        "smtp_password",
        "password",
        "hf_token",
        "huggingface_api_token",
        "google_api_key",
        "groq_api_key",
        "mistral_api_key",
        "nous_api_key",
        "openrouter_api_key",
        "custom_openai_api_key",
        "urlvoid_api_key",
        "virustotal_api_key",
        "slack_bot_token",
        "discord_bot_token",
    ],
}

#: section -> connection-string fields that must lose their userinfo password
#: while keeping host/port/database visible.
MUST_MASK_URL_PASSWORD = {
    "misc": ["database_url", "redis_url", "celery_broker_url"],
}

#: section -> fields that are credential-SHAPED but hold no secret.  Listed so
#: that over-redaction is caught too: masking a path costs diagnosability.
MUST_STAY_VISIBLE = {
    "misc": [
        "speculation_num_tokens",
        "tls_key_path",
        "tls_cert_path",
        "service_key_file",
        "chromadb_path",
        "db_path",
        "llm_key_rotation_grace_secs",
        "llm_key_rotation_interval_minutes",
        "tokenizers_parallelism",
    ],
    "tls": ["ca_cert", "cert_dir", "remote_cert_dir"],
    "path": ["ssh_key_path", "vnc_passwd_file"],
    "auth": ["google_oauth_client_id", "microsoft_oauth_client_id"],
    "llm": ["searxng_basic_auth_user"],
}

CANARY = "CANARY-VALUE-13325-MUST-NOT-APPEAR"
CANARY_URL = f"postgresql://dbuser:{CANARY}@db.example.invalid:5432/appdb"


def _section(name):
    """Return a freshly built config section, isolated from the host .env."""
    cfg = get_config()
    return getattr(cfg, name)


@pytest.mark.parametrize(
    ("section", "field"),
    [(s, f) for s, fields in MUST_BE_MASKED.items() for f in fields],
)
def test_seeded_credential_never_appears_in_repr(section, field):
    """Ground truth: seed a canary, assert repr() cannot show it."""
    seeded = _section(section).model_copy(update={field: CANARY})
    text = repr(seeded)
    assert CANARY not in text, f"{section}.{field} leaked its value into repr()"
    assert field in text, f"{section}.{field} lost its NAME — dumps must stay diagnosable"
    assert REDACTED_PLACEHOLDER in text


@pytest.mark.parametrize(
    ("section", "field"),
    [(s, f) for s, fields in MUST_MASK_URL_PASSWORD.items() for f in fields],
)
def test_seeded_url_password_never_appears_in_repr(section, field):
    """database_url and friends embed credentials — mask userinfo, keep host."""
    seeded = _section(section).model_copy(update={field: CANARY_URL})
    text = repr(seeded)
    assert CANARY not in text, f"{section}.{field} leaked its URL password into repr()"
    # Everything an operator needs to diagnose the connection survives.
    assert "db.example.invalid" in text
    assert "5432" in text
    assert "appdb" in text
    assert "dbuser" in text


@pytest.mark.parametrize(
    ("section", "field"),
    [(s, f) for s, fields in MUST_STAY_VISIBLE.items() for f in fields],
)
def test_non_secret_lookalike_stays_visible(section, field):
    """Over-redaction is a bug too: a path or a count must remain readable."""
    marker = "visible-marker-13325"
    seeded = _section(section).model_copy(update={field: marker})
    assert marker in repr(seeded), f"{section}.{field} was masked but holds no secret"


def test_patch_object_typo_does_not_leak_seeded_credentials():
    """The exact reported vector, driven by seeded ground truth (#13325)."""
    seeded = _section("misc").model_copy(update={"jwt_secret": CANARY, "database_url": CANARY_URL})
    with pytest.raises(AttributeError) as excinfo:
        with patch.object(seeded, "definitely_not_a_real_config_field", "x"):
            pass
    message = str(excinfo.value)
    assert CANARY not in message
    assert "jwt_secret" in message, "field names must survive so failures stay diagnosable"


# A deliberately over-broad, classifier-independent net.  Any field whose name
# merely *looks* credential-ish must appear in one of the ground-truth lists
# above, so a newly added field cannot be silently left untriaged.
_LOOKS_LIKE_CREDENTIAL = re.compile(
    r"(secret|key|token|password|passwd|pass|credential|salt|dsn|cert|pem|seed)",
    re.IGNORECASE,
)


def test_classifier_covers_every_str_field_named_like_a_credential():
    cfg = get_config()
    triaged = {
        f"{s}.{f}"
        for mapping in (MUST_BE_MASKED, MUST_MASK_URL_PASSWORD, MUST_STAY_VISIBLE)
        for s, fields in mapping.items()
        for f in fields
    }
    untriaged = []
    for section in type(cfg).model_fields:
        model = getattr(cfg, section, None)
        if not hasattr(type(model), "model_fields"):
            continue
        for field in type(model).model_fields:
            if not _LOOKS_LIKE_CREDENTIAL.search(field):
                continue
            if f"{section}.{field}" in triaged:
                continue
            # Untriaged: it must at least be masked or URL-redacted by default.
            seeded = model.model_copy(update={field: CANARY})
            if CANARY in repr(seeded):
                untriaged.append(f"{section}.{field}")
    assert untriaged == [], (
        "credential-looking fields are neither masked nor triaged as safe; "
        f"add them to a ground-truth list in this file: {untriaged}"
    )
