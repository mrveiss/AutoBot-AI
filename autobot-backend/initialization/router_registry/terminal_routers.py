# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal Router Loader

This module handles loading of terminal-related API routers.
These routers provide terminal access, command execution, and remote terminal functionality.
"""

from .loader import load_router_group


# (module_path, prefix, tags, name). agent_terminal and terminal_tools carry
# their own /api prefixes internally, hence the empty prefix.
TERMINAL_ROUTER_CONFIGS = [
    ("api.terminal", "/terminal", ["terminal"], "terminal"),
    ("api.agent_terminal", "", ["agent-terminal"], "agent_terminal"),
    ("api.terminal_tools", "", ["terminal-tools"], "terminal_tools"),
]

# NOTE: remote_terminal and base_terminal were archived and deleted in Issue #567
# - remote_terminal: Future feature - implement with new architecture when Vue UI components are built
# - base_terminal: Features migrated to terminal.py
#   All endpoints now available in terminal.py (/health, /status, /capabilities, /security, /features, /stats)


def load_terminal_routers():
    """
    Dynamically load terminal-related API routers with graceful fallback.

    #14207: was three hand-written try/except blocks, each swallowing
    ImportError with a WARNING and no record — so a terminal router that
    failed to import left its endpoints 404ing with nothing but one log line
    to say so. Now data-driven like every other registry, through the shared
    loader that records the outcome and escalates a short count to ERROR.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    return load_router_group("terminal", TERMINAL_ROUTER_CONFIGS)
