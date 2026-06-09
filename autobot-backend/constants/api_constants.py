# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
