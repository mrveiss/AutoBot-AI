# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the host's Claude Code user-level config lives (agents, skills).

The account that runs the ``claude`` CLI keeps its agent definitions in
``<config dir>/agents``.  The config dir is the SSOT field ``path.claude_config_dir``
(env ``AUTOBOT_CLAUDE_CONFIG_DIR``, or the CLI's own ``CLAUDE_CONFIG_DIR``), else
``~/.claude`` of the account running the backend.  Never a path in the source tree.

``python -m autobot_shared.claude_config`` prints the directory for shell callers.
"""

import subprocess
import sys
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import scrubbed_git_env
from autobot_shared.ssot_config import config as ssot_config

logger = get_logger(__name__)


def claude_agents_dir() -> Path:
    """Directory of the host's Claude Code user-level agent definitions."""
    base = ssot_config.path.claude_config_dir or str(Path.home() / ".claude")
    return Path(base).expanduser() / "agents"


def backup_repo_problem(agents_dir: Path, allow_enclosing: bool) -> str | None:
    """Why a git backup of ``agents_dir`` would land in the wrong repository, else None.

    The backup tag and commit must live in the agents dir's OWN repository; a dir
    inside an unrelated enclosing repo (or in none) would tag/commit there.
    """
    run = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "-C", str(agents_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )
    top = run.stdout.strip()
    if not top:
        return f"{agents_dir} is not inside a git repository; run `git init` there first"
    logger.info("Git backup repository: %s", top)
    if Path(top).resolve() != agents_dir.resolve() and not allow_enclosing:
        return f"{agents_dir} sits inside the unrelated repository {top}; pass --allow-enclosing-repo to back up there"
    return None


if __name__ == "__main__":
    sys.stdout.write(f"{claude_agents_dir()}\n")
