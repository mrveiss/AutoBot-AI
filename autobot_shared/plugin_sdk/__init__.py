# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK for AutoBot

Provides infrastructure for developing and loading extensible plugins.
Issue #730 - Plugin SDK for extensible tool architecture.
Issue #3278 - Plugin and extension system for third-party integrations.
Issue #9049 - Plugin capability manifest system.
"""

from .base import BasePlugin, PluginLoadError, PluginManifest, PluginRegistry
from .capabilities import (
    Capability,
    CapabilityChecker,
    CapabilityContext,
    CapabilityError,
    TrustTier,
)
from .extension_manifest import ExtensionManifest
from .hooks import HOOK_REGISTRY, Hook, HookRegistry, HookSignature, validate_hook_names
from .loader import PluginLoader
from .manifest_contract import ManifestContract
from .plugin_manager import PluginManager
from .unified_registry import UnifiedRegistry, get_unified_registry

__all__ = [
    "BasePlugin",
    "Capability",
    "CapabilityChecker",
    "CapabilityContext",
    "CapabilityError",
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
    "TrustTier",
    "UnifiedRegistry",
    "get_unified_registry",
    "validate_hook_names",
]
