# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK

Provides the foundation for AutoBot's plugin system with capability-based
security, manifest management, and plugin lifecycle.

Issue #9049 - Plugin capability manifest system.
"""

from .base import BasePlugin, PluginManifest, PluginRegistry
from .capabilities import (
    Capability,
    CapabilityChecker,
    CapabilityContext,
    CapabilityError,
    TrustTier,
)
from .loader import PluginLoader

__all__ = [
    "BasePlugin",
    "PluginManifest",
    "PluginRegistry",
    "PluginLoader",
    "Capability",
    "CapabilityChecker",
    "CapabilityContext",
    "CapabilityError",
    "TrustTier",
]
