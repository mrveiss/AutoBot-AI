# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.loader`` (#11636)."""

from autobot_shared.plugin_sdk.loader import PluginLoader, validate_plugin_config

__all__ = [
    "PluginLoader",
    "validate_plugin_config",
]
