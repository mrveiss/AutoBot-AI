# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.base`` (#11636)."""

from autobot_shared.plugin_sdk.base import (
    BasePlugin,
    PluginLoadError,
    PluginManifest,
    PluginRegistry,
    PluginStatus,
    RequiredEnvVar,
)

__all__ = [
    "BasePlugin",
    "PluginLoadError",
    "PluginManifest",
    "PluginRegistry",
    "PluginStatus",
    "RequiredEnvVar",
]
