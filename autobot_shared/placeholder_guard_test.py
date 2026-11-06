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
    assert "AUTOBOT_REDIS_HOST=YOUR_REDIS_IP" in str(exc.value)
    assert "AUTOBOT_BACKEND_HOST=YOUR_BACKEND_IP" in str(exc.value)
    assert "OK" not in find_placeholders(env)


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
    with pytest.raises(PlaceholderConfigError, match="AUTOBOT_REDIS_HOST=YOUR_REDIS_IP"):
        enforce_system_requirements()
