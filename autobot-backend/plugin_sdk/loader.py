# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export shim — canonical home is ``autobot_shared.plugin_sdk.loader`` (#11636)."""

from autobot_shared.plugin_sdk.loader import (
    PluginLoader,
    _validate_config_against_schema,
    _validate_config_schema,
    validate_plugin_config,
)

# Private validators re-exported too (#11637): the canonical test suite
# imports them via the bare path.
__all__ = [
    "PluginLoader",
    "_validate_config_against_schema",
    "_validate_config_schema",
    "validate_plugin_config",
]
