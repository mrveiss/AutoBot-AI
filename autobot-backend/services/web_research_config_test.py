# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""services/web_research_config.py — the one home of the web research settings (#19226)."""

from typing import Any, Dict

import pytest

from services import web_research_config as wrc


class FakeConfigManager:
    """The get_nested/set_nested/save_settings surface of config_manager, over a dict."""

    def __init__(self, data: Dict[str, Any] | None = None):
        self.data = data or {}
        self.saves = 0

    def get_nested(self, path: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def set_nested(self, path: str, value: Any) -> None:
        *parents, leaf = path.split(".")
        node = self.data
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value

    def save_settings(self) -> None:
        self.saves += 1


def test_unsaved_settings_are_the_defaults():
    assert wrc.load_settings(FakeConfigManager()) == wrc.DEFAULTS


def test_every_field_round_trips_through_the_web_research_section():
    manager = FakeConfigManager()
    changed = {
        "enabled": False,
        "require_user_confirmation": False,
        "preferred_method": "advanced",
        "max_results": 9,
        "timeout_seconds": 45,
        "auto_research_threshold": 0.6,
        "rate_limit_requests": 7,
        "rate_limit_window": 120,
        "daily_limit": 20,
        "quality_threshold": 0.8,
        "store_results_in_kb": False,
        "filter_adult_content": False,
        "anonymize_requests": False,
    }
    assert set(changed) == set(wrc.DEFAULTS)
    assert wrc.save_settings(manager, changed) == changed
    assert manager.saves == 1
    # Stored where WebResearcher reads, under the config key names.
    assert manager.data["web_research"]["max_results"] == 9
    assert manager.data["web_research"]["daily_research_limit"] == 20
    assert manager.data["web_research"]["min_result_quality"] == 0.8
    assert "agents" not in manager.data


def test_a_value_the_old_put_left_under_agents_research_survives():
    manager = FakeConfigManager({"agents": {"research": {"max_results": 12, "timeout_seconds": 90}}})
    settings = wrc.load_settings(manager)
    assert settings["max_results"] == 12
    assert settings["timeout_seconds"] == 90


def test_the_web_research_section_wins_over_the_legacy_one():
    manager = FakeConfigManager({"agents": {"research": {"max_results": 12}}, "web_research": {"max_results": 3}})
    assert wrc.load_settings(manager)["max_results"] == 3


def test_a_partial_save_keeps_every_other_setting():
    manager = FakeConfigManager({"web_research": {"timeout_seconds": 60}})
    settings = wrc.save_settings(manager, {"max_results": 8})
    assert settings["timeout_seconds"] == 60
    assert settings["max_results"] == 8


def test_an_unknown_setting_is_refused_and_nothing_is_saved():
    manager = FakeConfigManager()
    with pytest.raises(ValueError, match="no_such_setting"):
        wrc.save_settings(manager, {"no_such_setting": 1})
    assert manager.saves == 0
    assert manager.data == {}


def test_a_failed_save_leaves_the_stored_settings_unchanged():
    """CodeRabbit on #19243: values set before a failing save are rolled back, not reported later."""
    manager = FakeConfigManager({"web_research": {"max_results": 4}})

    def boom() -> None:
        raise OSError("disk full")

    manager.save_settings = boom
    with pytest.raises(OSError):
        wrc.save_settings(manager, {"max_results": 9, "enabled": False})
    assert manager.data == {"web_research": {"max_results": 4}}
    assert wrc.load_settings(manager)["max_results"] == 4


def test_researcher_config_fills_every_setting_and_keeps_other_keys():
    manager = FakeConfigManager({"web_research": {"cache_ttl": 600, "max_results": 4}})
    config = wrc.researcher_config(manager)
    assert config["cache_ttl"] == 600
    assert config["max_results"] == 4
    assert config["rate_limit_window"] == wrc.DEFAULTS["rate_limit_window"]
    assert config["daily_research_limit"] == wrc.DEFAULTS["daily_limit"]


def test_every_field_the_old_put_wrote_to_agents_research_is_carried_over():
    # The pre-#19226 PUT wrote exactly these six to agents.research.* and nothing else there.
    legacy = {
        "enabled": False,
        "preferred_method": "advanced",
        "max_results": 12,
        "timeout_seconds": 90,
        "rate_limit_requests": 8,
        "rate_limit_window": 300,
    }
    settings = wrc.load_settings(FakeConfigManager({"agents": {"research": legacy}}))
    assert {field: settings[field] for field in legacy} == legacy
