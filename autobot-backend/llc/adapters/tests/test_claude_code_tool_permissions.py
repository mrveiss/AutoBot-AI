# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ClaudeCodeAdapter tool-permission args — forbidden-tool enforcement (GH#11186).

The LLC claude_code adapter is the real governed-agent execution path; a governed
agent's forbidden tools must be blocked on the external CLI via --disallowedTools.
"""

from llc.adapters.claude_code_adapter import ClaudeCodeAdapter


def _args(cfg) -> list[str]:
    return ClaudeCodeAdapter._tool_permission_args(cfg)


def test_empty_config_no_flags():
    assert _args({}) == []


def test_allowed_only():
    assert _args({"allowed_tools": ["Bash", "Read"]}) == ["--allowedTools", "Bash,Read"]


def test_disallowed_only():
    assert _args({"disallowed_tools": ["Bash", "Edit"]}) == ["--disallowedTools", "Bash,Edit"]


def test_both_allowed_and_disallowed():
    out = _args({"allowed_tools": ["Read"], "disallowed_tools": ["Bash"]})
    assert out == ["--allowedTools", "Read", "--disallowedTools", "Bash"]


def test_sanitizes_injection_and_delimiters():
    out = _args({"disallowed_tools": ["Bash", "--evil", "Edit,x", "Write"]})
    assert out == ["--disallowedTools", "Bash,Write"]
