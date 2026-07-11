# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin SDK — re-export shim.

Issue #11636: this package was a stale fork of ``autobot_shared.plugin_sdk``
(the canonical plugin SDK used by plugin_manager.py, chat_workflow, and
middleware). It now re-exports the canonical implementations so both import
paths resolve to the SAME classes and the SAME singleton registries.

New code should import from ``autobot_shared.plugin_sdk`` directly.
"""

from autobot_shared.plugin_sdk.base import (
    BasePlugin,
    PluginLoadError,
    PluginManifest,
    PluginRegistry,
    PluginStatus,
    RequiredEnvVar,
)
from autobot_shared.plugin_sdk.capabilities import (
    Capability,
    CapabilityChecker,
    CapabilityContext,
    CapabilityError,
    TrustTier,
)
from autobot_shared.plugin_sdk.hooks import Hook, HookRegistry
from autobot_shared.plugin_sdk.loader import PluginLoader, validate_plugin_config

__all__ = [
    "BasePlugin",
    "PluginLoadError",
    "PluginManifest",
    "PluginRegistry",
    "PluginStatus",
    "RequiredEnvVar",
    "PluginLoader",
    "validate_plugin_config",
    "Capability",
    "CapabilityChecker",
    "CapabilityContext",
    "CapabilityError",
    "TrustTier",
    "Hook",
    "HookRegistry",
]
