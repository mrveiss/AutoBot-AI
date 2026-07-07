# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Config-protection guard for the agent loop (GH#11148).

The detection logic now lives in the dependency-free ``autobot_shared.config_guard``
(GH#11177) so the production tool-dispatch seam can reuse it without importing the
heavy ``agent_loop`` package. This module re-exports the loop-facing surface.
"""

from autobot_shared.config_guard import (
    config_edits_allowed,
    is_protected_config,
    protected_config_for,
    protected_config_write,
)

__all__ = [
    "config_edits_allowed",
    "is_protected_config",
    "protected_config_for",
    "protected_config_write",
]
