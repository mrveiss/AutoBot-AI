# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK for AutoBot

Provides infrastructure for developing and loading extensible plugins.
Issue #730 - Plugin SDK for extensible tool architecture.
Issue #3278 - Plugin and extension system for third-party integrations.
"""

from plugin_sdk.base import BasePlugin, PluginLoadError, PluginManifest, PluginRegistry
from plugin_sdk.extension_manifest import ExtensionManifest
from plugin_sdk.hooks import HOOK_REGISTRY, Hook, HookRegistry, HookSignature, validate_hook_names
from plugin_sdk.loader import PluginLoader
from plugin_sdk.manifest_contract import ManifestContract
from plugin_sdk.plugin_manager import PluginManager
from plugin_sdk.unified_registry import UnifiedRegistry, get_unified_registry

__all__ = [
    "BasePlugin",
    "ExtensionManifest",
    "HOOK_REGISTRY",
    "Hook",
    "HookRegistry",
    "HookSignature",
    "ManifestContract",
    "PluginLoadError",
    "PluginManifest",
    "PluginRegistry",
    "PluginLoader",
    "PluginManager",
    "UnifiedRegistry",
    "get_unified_registry",
    "validate_hook_names",
]
