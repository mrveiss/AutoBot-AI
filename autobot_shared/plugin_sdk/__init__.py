# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK for AutoBot

Provides infrastructure for developing and loading extensible plugins.
Issue #730 - Plugin SDK for extensible tool architecture.
"""

from plugin_sdk.base import BasePlugin, PluginManifest, PluginRegistry
from plugin_sdk.hooks import Hook, HookRegistry
from plugin_sdk.loader import PluginLoader

__all__ = [
    "BasePlugin",
    "PluginManifest",
    "PluginRegistry",
    "Hook",
    "HookRegistry",
    "PluginLoader",
]
