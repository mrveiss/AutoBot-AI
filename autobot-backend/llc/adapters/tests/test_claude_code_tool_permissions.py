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


def _cmd(resume, cfg, prompt="do it"):
    return ClaudeCodeAdapter._build_command("claude", resume, cfg, prompt, session_id="fresh-sid")


def test_fresh_session_command_has_model_and_tools_and_terminator():
    cmd = _cmd(None, {"model": "opus", "max_turns": 5, "disallowed_tools": ["Bash"]})
    assert cmd[:4] == ["claude", "--output-format", "stream-json", "--print"]
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert "--disallowedTools" in cmd
    assert cmd[-2] == "--" and cmd[-1] == "do it"


def test_resumed_session_still_enforces_disallowed_tools():
    # GH#11186: the governance flags MUST apply on resume, not just fresh sessions.
    cmd = _cmd("sess-123", {"disallowed_tools": ["Bash", "Edit"]})
    assert cmd[cmd.index("--resume") + 1] == "sess-123"
    assert cmd[cmd.index("--disallowedTools") + 1] == "Bash,Edit"
    # session-establishment options are NOT re-sent on resume
    assert "--model" not in cmd and "--max-turns" not in cmd
    assert cmd[-2] == "--" and cmd[-1] == "do it"


def test_prompt_is_positional_after_terminator():
    # A prompt starting with '-' can never be parsed as an option.
    cmd = _cmd(None, {}, prompt="--dangerously-skip-permissions")
    assert cmd[-2] == "--"
    assert cmd[-1] == "--dangerously-skip-permissions"
    assert cmd.count("--dangerously-skip-permissions") == 1
