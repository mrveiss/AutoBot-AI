# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Exported templates keep counts of a credential noun (#17336).

``max_tokens`` is a number in nearly every LLM adapter config. Under the canonical
PRECISE matcher ``tokens`` is a credential noun, so without the quantity rule it
became ``{{MAX_TOKENS}}`` on export and no longer imported as 4096.
"""

import json
from unittest.mock import MagicMock

import pytest

from llc.services.portability import PortabilityService, _scrub_adapter_config


def _roundtrip(config, secrets):
    exported = json.loads(json.dumps(_scrub_adapter_config(config, {})))
    service = PortabilityService(session=MagicMock())
    return exported, service._resolve_secrets(exported, secrets, "agent", [])


def test_max_tokens_survives_export_and_import_while_api_key_is_a_placeholder() -> None:
    exported, imported = _roundtrip({"max_tokens": 4096, "api_key": "sk-live-x"}, {"API_KEY": "sk-new"})
    assert exported["max_tokens"] == 4096
    assert exported["api_key"] == "{{API_KEY}}"
    assert "sk-live-x" not in json.dumps(exported)
    assert imported == {"max_tokens": 4096, "api_key": "sk-new"}  # pragma: allowlist secret


@pytest.mark.parametrize("name", ["num_tokens", "total_tokens", "token_count", "max_keys", "key_count", "key_length"])
def test_counts_and_limits_are_exported_verbatim(name: str) -> None:
    assert _scrub_adapter_config({name: 7}, {}) == {name: 7}


@pytest.mark.parametrize("name", ["max_token_secret", "max_password", "token_count_secret", "api_key", "x_secret"])
def test_secret_looking_names_are_still_placeholders(name: str) -> None:
    assert _scrub_adapter_config({name: "value"}, {})[name].startswith("{{")


_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijkl"  # pragma: allowlist secret


def test_a_quantity_name_holding_a_non_number_is_still_a_placeholder() -> None:
    out = _scrub_adapter_config({"token_count": _JWT, "max_tokens": 4096}, {})
    assert out["token_count"] == "{{TOKEN_COUNT}}"
    assert out["max_tokens"] == 4096


@pytest.mark.parametrize("value", ["123456", "4096"])
def test_a_digit_string_under_a_quantity_name_is_a_placeholder(value) -> None:
    # A digit string is PIN-shaped: only a real int/float is exempt.
    out = _scrub_adapter_config({"password_limit": value, "max_tokens": 4096}, {})
    assert out["password_limit"] == "{{PASSWORD_LIMIT}}"
    assert out["max_tokens"] == 4096


def test_max_tokens_is_unmasked_only_via_the_export_path_and_masked_at_every_other_caller() -> None:
    """The contrast pair (#17337 AC2): one caller exempts a count, all the others mask it."""
    from autobot_shared.secret_redaction import redact_mapping, redact_value

    assert _scrub_adapter_config({"max_tokens": 4096}, {}) == {"max_tokens": 4096}
    assert redact_mapping({"max_tokens": 4096}) == {"max_tokens": "***"}
    assert redact_value("max_tokens", 4096) == "**********"


def test_bool_and_none_values_survive_the_round_trip_without_a_placeholder() -> None:
    """`verify_cert: True` exported as `{{VERIFY_CERT}}` (cert is a credential noun) and imported as a string."""
    config = {
        "verify_cert": True,
        "ssl_verify": False,
        "refresh_token": None,
        "client_secret": None,
        "use_key": True,
        "api_key": "sk-live-x",  # pragma: allowlist secret
    }
    exported = json.loads(json.dumps(_scrub_adapter_config(config, {})))
    assert exported["api_key"] == "{{API_KEY}}"
    assert "{{" not in json.dumps({k: v for k, v in exported.items() if k != "api_key"})
    warnings: list = []
    service = PortabilityService(session=MagicMock())
    imported = service._resolve_secrets(exported, {"API_KEY": "sk-new"}, "agent", warnings)  # pragma: allowlist secret
    assert warnings == []
    assert imported == {**config, "api_key": "sk-new"}  # pragma: allowlist secret
    assert imported["verify_cert"] is True and imported["ssl_verify"] is False
    assert imported["refresh_token"] is None and imported["client_secret"] is None


def test_the_bool_exemption_is_export_only() -> None:
    from autobot_shared.secret_redaction import redact_mapping, redact_value

    assert _scrub_adapter_config({"verify_cert": True}, {}) == {"verify_cert": True}
    assert redact_mapping({"verify_cert": True}) == {"verify_cert": "***"}
    assert redact_value("verify_cert", True) == "**********"


@pytest.mark.parametrize(
    "name",
    ["access_token", "api_key", "api_secret", "auth_token", "bearer_token", "client_secret", "credentials"]
    + ["key", "password", "private_key", "secret", "token", "API_KEY", "Token"],
)
def test_true_under_main_s_twelve_export_names_is_still_a_placeholder(name: str) -> None:
    # #18196 (owner decision: `api_key: True` does not round-trip) and #17337 AC2: no key leaves
    # the masked set. Only these names; `verify_cert`/`use_key` above round-trip.
    assert _scrub_adapter_config({name: True}, {}) == {name: f"{{{{{name.upper()}}}}}"}


@pytest.mark.parametrize("name", ["api_key", "token", "verify_cert", "use_key"])
def test_false_and_none_are_never_a_placeholder(name: str) -> None:
    assert _scrub_adapter_config({name: False}, {}) == {name: False}
    assert _scrub_adapter_config({name: None}, {}) == {name: None}
