# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed browser tool reports a specific, sanitized reason (#21769)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from chat_workflow.browser_tool_handler import describe_browser_error


def test_timeout_names_tool_and_selector():
    exc = HTTPException(status_code=504, detail="Browser VM request timed out")
    msg = describe_browser_error("click", {"selector": "#buy"}, exc)
    assert "timed out" in msg and "'#buy'" in msg and "click" in msg


def test_selector_not_found():
    exc = RuntimeError("locator not found for xpath=/html")
    msg = describe_browser_error("click", {"selector": "a.go"}, exc)
    assert "element not found" in msg and "'a.go'" in msg


def test_internals_are_not_leaked():
    exc = HTTPException(status_code=502, detail="Browser VM error: 500 - token=SECRET at /opt/x")
    msg = describe_browser_error("navigate", {}, exc)
    assert "SECRET" not in msg and "/opt" not in msg and "selector" not in msg


@pytest.mark.parametrize("params", [{}, {"selector": 5}])
def test_no_selector_hint_without_string_selector(params):
    assert "selector:" not in describe_browser_error("x", params, RuntimeError("boom"))
