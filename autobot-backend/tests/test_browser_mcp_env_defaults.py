# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An out-of-range browser MCP rate window falls back to its default; it is not clamped to a bound."""

import pytest

from autobot_shared.env_registry import env

_NAME = "AUTOBOT_MCP_BROWSER_RATE_WINDOW_S"


@pytest.mark.parametrize(("raw", "expected"), [("0", 60), ("-5", 60), ("86401", 60), ("junk", 60), ("30", 30)])
def test_rate_window_out_of_range_falls_back_to_default(monkeypatch, raw, expected):
    monkeypatch.setenv(_NAME, raw)
    assert env(_NAME) == expected


def test_browser_mcp_reads_the_window_through_the_registry():
    from api import browser_mcp  # noqa: PLC0415

    assert browser_mcp.RATE_LIMIT_WINDOW_SECONDS == 60


@pytest.mark.parametrize("name", ["AUTOBOT_BROWSER_VM_REQUEST_TIMEOUT_S", "AUTOBOT_BROWSER_VM_HEALTH_TIMEOUT_S"])
@pytest.mark.parametrize("raw", ["0", "-1", "nan", "inf", "junk"])
def test_timeouts_fall_back_to_default_not_a_bound(monkeypatch, name, raw):
    from autobot_shared.env_utils import env_float_clamped  # noqa: PLC0415

    monkeypatch.setenv(name, raw)
    default = 60.0 if "REQUEST" in name else 5.0
    assert env_float_clamped(name, default, positive_finite=True) == default
