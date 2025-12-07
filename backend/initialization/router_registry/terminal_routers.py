# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Router Loader

This module handles loading of terminal-related API routers.
These routers provide terminal access, command execution, and remote terminal functionality.
"""

import logging

logger = logging.getLogger(__name__)


def load_terminal_routers():
    """
    Dynamically load terminal-related API routers with graceful fallback.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # Terminal router
    try:
        from backend.api.terminal import router as terminal_router

        optional_routers.append(
            (terminal_router, "/terminal", ["terminal"], "terminal")
        )
        logger.info("✅ Optional router loaded: terminal")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: terminal - {e}")

    # Agent Terminal router
    try:
        from backend.api.agent_terminal import router as agent_terminal_router

        optional_routers.append(
            (agent_terminal_router, "", ["agent-terminal"], "agent_terminal")
        )
        logger.info(
            "✅ Optional router loaded: agent_terminal (includes prefix /api/agent-terminal)"
        )
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: agent_terminal - {e}")

    # NOTE: remote_terminal and base_terminal were archived during terminal consolidation
    # - remote_terminal: Future feature, archived at backend/api/archive/remote_terminal.py.feature
    #   Re-enable when Vue UI components are built for SSH multi-host terminal
    # - base_terminal: Features migrated to terminal.py, archived at backend/api/archive/base_terminal.py.unused
    #   All endpoints now available in terminal.py (/health, /status, /capabilities, /security, /features, /stats)

    return optional_routers
