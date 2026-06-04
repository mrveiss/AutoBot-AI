# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Centralised API path and endpoint constants.

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    PATH_API_HEALTH,
    PATH_HEALTH,
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_PULL,
    PATH_OLLAMA_TAGS,
)
