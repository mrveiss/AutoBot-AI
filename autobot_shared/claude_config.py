# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the host's Claude Code user-level config lives (agents, skills).

The account that runs the ``claude`` CLI keeps its agent definitions in
``<config dir>/agents``.  The config dir is, in order: ``AUTOBOT_CLAUDE_CONFIG_DIR``
(SSOT ``path.claude_config_dir``), the CLI's own ``CLAUDE_CONFIG_DIR``, then
``~/.claude`` of the account running the backend.  Never a path in the source tree.
"""

import os
from pathlib import Path

from autobot_shared.ssot_config import config as ssot_config


def claude_agents_dir() -> Path:
    """Directory of the host's Claude Code user-level agent definitions."""
    base = ssot_config.path.claude_config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base).expanduser() / "agents"
