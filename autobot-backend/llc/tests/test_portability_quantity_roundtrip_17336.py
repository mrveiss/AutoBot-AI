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
