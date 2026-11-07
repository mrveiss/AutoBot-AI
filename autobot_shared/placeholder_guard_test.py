# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20886 AC 8: a placeholder config value fails once, naming every offender."""

import pytest

from autobot_shared.placeholder_guard import PlaceholderConfigError, enforce_no_placeholders, find_placeholders


def test_placeholder_values_are_found_and_named_together() -> None:
    env = {"AUTOBOT_REDIS_HOST": "YOUR_REDIS_IP", "AUTOBOT_BACKEND_HOST": "YOUR_BACKEND_IP", "OK": "10.0.0.1"}
    with pytest.raises(PlaceholderConfigError) as exc:
        enforce_no_placeholders(env)
    assert "AUTOBOT_REDIS_HOST" in str(exc.value) and "AUTOBOT_BACKEND_HOST" in str(exc.value)
    assert "YOUR_REDIS_IP" not in str(exc.value) and "YOUR_BACKEND_IP" not in str(exc.value), "values are not echoed"
    assert "OK" not in find_placeholders(env)


def test_unrelated_variables_do_not_block_startup() -> None:
    env = {"SOME_TOOL_TOKEN": "YOUR_TOKEN", "AUTOBOT_REDIS_HOST": "redis.internal"}
    assert find_placeholders(env) == {}
    enforce_no_placeholders(env)


@pytest.mark.parametrize(
    "value",
    ["redis.internal", "10.0.0.1", "", "prefix_YOUR_REDIS_IP", "YOUR_redis_ip"],
    ids=["host", "ip", "empty", "prefixed", "lowercase"],
)
def test_real_values_pass(value: str) -> None:
    enforce_no_placeholders({"AUTOBOT_REDIS_HOST": value})


def test_startup_enforcement_fails_on_a_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backend's startup gate runs the check before anything connects."""
    from startup_validator import enforce_system_requirements

    monkeypatch.setenv("AUTOBOT_REDIS_HOST", "YOUR_REDIS_IP")
    with pytest.raises(PlaceholderConfigError, match="AUTOBOT_REDIS_HOST"):
        enforce_system_requirements()
