# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""claude_config.claude_agents_dir(): the host's Claude Code user-level agents dir."""

from pathlib import Path

from autobot_shared import claude_config


def _configure(monkeypatch, value: str) -> None:
    monkeypatch.setattr(claude_config.ssot_config.path, "claude_config_dir", value, raising=False)


def test_configured_dir_wins_over_the_cli_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "from-cli-env"))
    _configure(monkeypatch, str(tmp_path / "configured"))
    assert claude_config.claude_agents_dir() == tmp_path / "configured" / "agents"


def test_cli_variable_is_used_when_unconfigured(monkeypatch, tmp_path):
    _configure(monkeypatch, "")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "from-cli-env"))
    assert claude_config.claude_agents_dir() == tmp_path / "from-cli-env" / "agents"


def test_default_is_the_running_accounts_claude_dir(monkeypatch, tmp_path):
    _configure(monkeypatch, "")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert claude_config.claude_agents_dir() == tmp_path / ".claude" / "agents"
