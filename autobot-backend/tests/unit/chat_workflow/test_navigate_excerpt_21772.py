# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A navigate result carries a capped, whitespace-collapsed page-text excerpt (#21772)."""

from __future__ import annotations

from unittest.mock import patch

from chat_workflow import browser_tool_handler as bth


def _format(text):
    inner = {"url": "https://example.com", "title": "Example", "text": text}
    return bth.format_browser_action_text("navigate", {"url": "https://example.com"}, inner, {"result": inner})


def test_excerpt_follows_url_and_title_with_whitespace_collapsed():
    out = _format("Hello\n\n\n   world\t\tagain")
    assert out.startswith("Navigated to: https://example.com\nPage title: Example")
    assert "Hello world again" in out


def test_excerpt_is_capped_by_the_constant():
    with patch.object(bth, "BROWSER_NAVIGATE_EXCERPT_MAX_CHARS", 20):
        out = _format("word " * 100)
    assert "word " * 5 not in out.split("Page text:", 1)[1]


def test_no_text_keeps_the_old_shape():
    assert _format("") == "Navigated to: https://example.com\nPage title: Example"
    assert _format(None) == "Navigated to: https://example.com\nPage title: Example"
