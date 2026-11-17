# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""claude_config.claude_agents_dir(): the host's Claude Code user-level agents dir."""

from pathlib import Path

from autobot_shared import claude_config
from autobot_shared.ssot_config import PathConfig


def _configure(monkeypatch, value: str) -> None:
    monkeypatch.setattr(claude_config.ssot_config.path, "claude_config_dir", value, raising=False)


def test_configured_dir_is_used(monkeypatch, tmp_path):
    _configure(monkeypatch, str(tmp_path / "configured"))
    assert claude_config.claude_agents_dir() == tmp_path / "configured" / "agents"


def test_default_is_the_running_accounts_claude_dir(monkeypatch, tmp_path):
    _configure(monkeypatch, "")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert claude_config.claude_agents_dir() == tmp_path / ".claude" / "agents"


def test_field_reads_the_cli_variable_and_autobot_wins(monkeypatch):
    monkeypatch.delenv("AUTOBOT_CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/from-cli")
    assert PathConfig(_env_file=None).claude_config_dir == "/from-cli"
    monkeypatch.setenv("AUTOBOT_CLAUDE_CONFIG_DIR", "/from-autobot")
    assert PathConfig(_env_file=None).claude_config_dir == "/from-autobot"


def _init_repo(path: Path) -> None:
    import subprocess

    from autobot_shared.paths import scrubbed_git_env

    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, capture_output=True, env=scrubbed_git_env())


def test_backup_repo_ok_when_the_dir_is_its_own_repo(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    _init_repo(agents)
    assert claude_config.backup_repo_problem(agents, False) is None


def test_backup_repo_refuses_an_enclosing_repo_unless_allowed(tmp_path):
    _init_repo(tmp_path)
    agents = tmp_path / "agents"
    agents.mkdir()
    assert "unrelated repository" in claude_config.backup_repo_problem(agents, False)
    assert claude_config.backup_repo_problem(agents, True) is None


def test_backup_repo_refuses_a_dir_in_no_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    agents = tmp_path / "agents"
    agents.mkdir()
    assert "not inside a git repository" in claude_config.backup_repo_problem(agents, False)
