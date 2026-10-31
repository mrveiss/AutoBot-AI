# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A configured model reaches the CLI on resumed runs too (#20268).

Probed against the CLI: a session started with one model and resumed with
``--model`` another reports the requested model in its init event.
"""

from llc.adapters.claude_code_adapter import ClaudeCodeAdapter


def _cmd(resume, cfg):
    return ClaudeCodeAdapter._build_command("claude", resume, cfg, "go", session_id="sid")


def test_resumed_session_passes_the_configured_model() -> None:
    cmd = _cmd("sess-1", {"model": "opus"})
    assert cmd[cmd.index("--resume") + 1] == "sess-1"
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_fresh_session_passes_the_configured_model() -> None:
    cmd = _cmd(None, {"model": "opus"})
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_no_configured_model_adds_no_flag_on_either() -> None:
    assert "--model" not in _cmd("sess-1", {})
    assert "--model" not in _cmd(None, {})


def test_model_precedes_the_prompt_terminator() -> None:
    cmd = _cmd("sess-1", {"model": "opus"})
    assert cmd.index("--model") < cmd.index("--")
    assert cmd[-2:] == ["--", "go"]
