# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A configured model reaches the CLI on resumed runs too (#20268).

Probed against the CLI: a session started with one model and resumed with
``--model`` another reports the requested model in its init event.
"""

import logging

import pytest

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


@pytest.mark.parametrize("resume", [None, "sess-1"])
@pytest.mark.parametrize("bad", ["--evil", "-x", "opus --dangerously-skip-permissions", "two words", "a\nb"])
def test_unsafe_model_is_omitted_and_never_logged(resume, bad, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        cmd = _cmd(resume, {"model": bad})
    assert "--model" not in cmd and bad not in cmd
    assert cmd[-2:] == ["--", "go"]
    assert any("not a safe model name" in r.getMessage() for r in caplog.records)
    assert not any(bad in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("model", ["opus", "claude-opus-5[1m]", "us.anthropic.claude-x-v1:0"])
def test_real_model_names_pass(model) -> None:
    cmd = _cmd("sess-1", {"model": model})
    assert cmd[cmd.index("--model") + 1] == model
