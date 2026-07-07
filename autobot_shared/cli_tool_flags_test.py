# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared claude_code tool-flag sanitizer (GH#11186)."""

from autobot_shared.cli_tool_flags import sanitize_tool_names


def test_keeps_valid_names():
    assert sanitize_tool_names(["Bash", "Read", "Write"]) == ["Bash", "Read", "Write"]


def test_none_and_empty():
    assert sanitize_tool_names(None) == []
    assert sanitize_tool_names([]) == []


def test_drops_empty_and_flag_looking():
    assert sanitize_tool_names(["", "Bash", "--dangerously-skip-permissions"]) == ["Bash"]


def test_drops_delimiter_bearing():
    assert sanitize_tool_names(["Bash", "Edit,--evil", "Wr\nite", "Write"]) == ["Bash", "Write"]


def test_coerces_non_str():
    assert sanitize_tool_names([1, "Bash"]) == ["1", "Bash"]
