# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the unified AUTOBOT_GUARD_PROFILE switch (GH#11150).

Acceptance criteria:
  - The profile selects a documented guard matrix (minimal / standard / strict).
  - Per-guard env vars override the profile.
  - The default (standard) profile reproduces today's AgentLoopConfig defaults.
  - Unknown/unset profile falls back to standard.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop.guard_profile import (
    DEFAULT_PROFILE,
    resolve_guard_config_overrides,
    resolve_profile_name,
)
from agent_loop.loop import AgentLoop
from agent_loop.types import AgentLoopConfig

_GUARD_FIELDS = (
    "require_approval_for_sensitive",
    "pre_action_verifier_enabled",
    "halt_on_stagnation",
    "abstain_on_low_confidence",
    "max_identical_tool_calls",
)


@pytest.fixture(autouse=True)
def _clear_guard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "AUTOBOT_GUARD_PROFILE",
        "AUTOBOT_GUARD_REQUIRE_APPROVAL",
        "AUTOBOT_GUARD_VERIFIER",
        "AUTOBOT_GUARD_STAGNATION_HALT",
        "AUTOBOT_GUARD_ABSTAIN",
        "AUTOBOT_GUARD_MAX_IDENTICAL",
    ):
        monkeypatch.delenv(var, raising=False)


class TestProfileName:
    def test_unset_is_standard(self) -> None:
        assert resolve_profile_name() == "standard"

    def test_unknown_falls_back_to_standard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "bananas")
        assert resolve_profile_name() == DEFAULT_PROFILE

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "STRICT")
        assert resolve_profile_name() == "strict"


class TestOverrides:
    def test_standard_has_no_overrides(self) -> None:
        assert resolve_guard_config_overrides() == {}

    def test_minimal_relaxes_guards(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "minimal")
        o = resolve_guard_config_overrides()
        assert o["require_approval_for_sensitive"] is False
        assert o["pre_action_verifier_enabled"] is False
        assert o["max_identical_tool_calls"] == 5

    def test_strict_tightens_guards(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "strict")
        o = resolve_guard_config_overrides()
        assert o["require_approval_for_sensitive"] is True
        assert o["max_identical_tool_calls"] == 2

    def test_per_guard_env_overrides_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "minimal")
        # minimal disables approval; explicit env re-enables it.
        monkeypatch.setenv("AUTOBOT_GUARD_REQUIRE_APPROVAL", "1")
        monkeypatch.setenv("AUTOBOT_GUARD_MAX_IDENTICAL", "9")
        o = resolve_guard_config_overrides()
        assert o["require_approval_for_sensitive"] is True
        assert o["max_identical_tool_calls"] == 9

    def test_invalid_int_override_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_MAX_IDENTICAL", "not-a-number")
        assert "max_identical_tool_calls" not in resolve_guard_config_overrides()


class TestConfigMapping:
    def test_standard_equals_default_config(self) -> None:
        profiled = AgentLoopConfig.with_guard_profile()
        default = AgentLoopConfig()
        for field_name in _GUARD_FIELDS:
            assert getattr(profiled, field_name) == getattr(default, field_name)

    def test_strict_profile_applied_to_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "strict")
        cfg = AgentLoopConfig.with_guard_profile()
        assert cfg.max_identical_tool_calls == 2
        assert cfg.abstain_on_low_confidence is True

    def test_explicit_override_wins_over_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "strict")
        cfg = AgentLoopConfig.with_guard_profile(max_identical_tool_calls=7)
        assert cfg.max_identical_tool_calls == 7


class TestLoopWiring:
    def _loop(self, config: AgentLoopConfig | None = None) -> AgentLoop:
        event_stream = MagicMock()
        event_stream.get_latest = AsyncMock(return_value=[])
        event_stream.publish = AsyncMock()
        return AgentLoop(event_stream=event_stream, config=config)

    def test_no_config_applies_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "minimal")
        loop = self._loop()
        assert loop.config.require_approval_for_sensitive is False
        assert loop.config.max_identical_tool_calls == 5

    def test_explicit_config_is_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOBOT_GUARD_PROFILE", "minimal")
        # Caller passes an explicit config → profile must NOT override it.
        explicit = AgentLoopConfig(require_approval_for_sensitive=True, max_identical_tool_calls=3)
        loop = self._loop(config=explicit)
        assert loop.config.require_approval_for_sensitive is True
        assert loop.config.max_identical_tool_calls == 3

    def test_default_loop_matches_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        loop = self._loop()
        default = AgentLoopConfig()
        for field_name in _GUARD_FIELDS:
            assert getattr(loop.config, field_name) == getattr(default, field_name)
