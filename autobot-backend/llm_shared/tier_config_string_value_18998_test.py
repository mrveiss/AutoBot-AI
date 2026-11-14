# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``llm.tiered_routing`` arrives from Redis as a ``str``; it must become a dict (#18998)."""

import json
import logging
from unittest.mock import patch

import pytest

from llm_shared.tiered_routing.tier_config import TierConfig, _decode_tier_config


@pytest.fixture(autouse=True)
def _fresh_decode_memo():
    _decode_tier_config.cache_clear()
    yield
    _decode_tier_config.cache_clear()


def _from(value):
    with patch("llm_shared.tiered_routing.tier_config.ConfigRegistry.get", return_value=value):
        return TierConfig.from_config()


def test_a_json_string_is_decoded_to_a_dict():
    """Reverting the ``json.loads`` branch in ``_tier_config_mapping`` raises AttributeError (str.get)."""
    cfg = _from(json.dumps({"enabled": False, "complexity_threshold": 7, "models": {"ssm": "mamba"}}))
    assert cfg.enabled is False
    assert cfg.complexity_threshold == 7.0
    assert cfg.models.ssm == "mamba"


def test_a_dict_still_works():
    """Reverting the ``isinstance(raw, dict)`` early return would send dicts to the warning path."""
    assert _from({"enabled": False}).enabled is False


def test_a_non_json_string_warns_and_falls_back_to_defaults(caplog):
    """Reverting the ``logger.warning`` / ``return {}`` tail makes this raise or stay silent."""
    with caplog.at_level(logging.WARNING, logger="llm_shared.tiered_routing.tier_config"):
        cfg = _from("not json at all")
    assert cfg == TierConfig()
    assert any("llm.tiered_routing" in r.getMessage() for r in caplog.records)


def test_a_json_non_object_is_rejected_too(caplog):
    """Reverting the ``isinstance(decoded, dict)`` check lets a JSON list through to ``.get``."""
    with caplog.at_level(logging.WARNING, logger="llm_shared.tiered_routing.tier_config"):
        assert _from("[1, 2]") == TierConfig()
    assert caplog.records


def test_the_same_bad_string_decodes_and_warns_once(caplog):
    """Reverting the ``lru_cache`` on ``_decode_tier_config`` warns on every call (2, not 1)."""
    with caplog.at_level(logging.WARNING, logger="llm_shared.tiered_routing.tier_config"):
        _from("not json at all")
        _from("not json at all")
    assert len(caplog.records) == 1


def test_a_different_bad_string_warns_again(caplog):
    """Contrast: the memo is keyed by the raw string, so a new bad value is still reported."""
    with caplog.at_level(logging.WARNING, logger="llm_shared.tiered_routing.tier_config"):
        _from("not json at all")
        _from("still {not json")
    assert len(caplog.records) == 2
