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

import sys
from pathlib import Path

from autobot_shared.ssot_config import config as ssot_config


def claude_agents_dir() -> Path:
    """Directory of the host's Claude Code user-level agent definitions."""
    base = ssot_config.path.claude_config_dir or str(Path.home() / ".claude")
    return Path(base).expanduser() / "agents"


if __name__ == "__main__":
    sys.stdout.write(f"{claude_agents_dir()}\n")
