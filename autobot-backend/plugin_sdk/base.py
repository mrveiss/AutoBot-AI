# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK Base Classes

Defines the core plugin system abstractions: manifests, base plugin class,
and the global plugin registry.

Issue #9049 - Plugin capability manifest system.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .capabilities import Capability, TrustTier


class PluginManifest(BaseModel):
    """Plugin manifest loaded from plugin.json.

    Defines metadata, capabilities, configuration schema, and runtime requirements.
    """

    name: str = Field(..., description="Plugin identifier (kebab-case)")
    version: str = Field(..., description="Semantic version")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Plugin purpose")
    author: str = Field(..., description="Author/organization")
    entry_point: str = Field(..., description="Python module path to Plugin class")

    # Capability declarations (Issue #9049)
    capabilities: List[Capability] = Field(
        default_factory=list,
        description="Required capabilities (e.g. kb:read, llm:call, network:outbound)",
    )
    trust_tier: TrustTier = Field(
        default=TrustTier.COMMUNITY,
        description="Plugin trust level: official, verified, community, unverified",
    )

    # Configuration and dependencies
    dependencies: List[str] = Field(
        default_factory=list,
        description="Python package dependencies",
    )
    config_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for plugin configuration",
    )
    hooks: List[str] = Field(
        default_factory=list,
        description="Lifecycle hooks this plugin implements",
    )
    required_env: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Required environment variables with metadata",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate plugin name follows kebab-case convention."""
        import re
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,62}$", v):
            raise ValueError(
                "Plugin name must be lowercase alphanumeric with dashes/underscores, "
                "start with letter or digit, max 63 chars"
            )
        return v


class BasePlugin(ABC):
    """Abstract base class for all AutoBot plugins.

    Provides common lifecycle hooks, configuration management, and capability
    enforcement integration.
    """

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        """Initialize plugin with manifest and configuration.

        Args:
            manifest: Plugin manifest from plugin.json
            config: Runtime configuration (merged with defaults from manifest)
        """
        self.manifest = manifest
        self.config = config or {}
        self.enabled = False
        self._logger = logging.getLogger(f"plugin.{manifest.name}")

    def get_info(self) -> Dict[str, Any]:
        """Get plugin information for API responses."""
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "display_name": self.manifest.display_name,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "enabled": self.enabled,
            "capabilities": [cap.value for cap in self.manifest.capabilities],
            "trust_tier": self.manifest.trust_tier.value,
        }

    async def initialize(self) -> None:
        """Initialize plugin resources (database connections, caches, etc.).

        Called once when the plugin is first loaded. Override to set up
        persistent resources.
        """
        pass

    async def shutdown(self) -> None:
        """Clean up plugin resources.

        Called when the plugin is unloaded or the system shuts down.
        Override to close connections, flush caches, etc.
        """
        pass

    async def enable(self) -> None:
        """Enable the plugin.

        Called when an admin activates the plugin. Override to start
        background tasks, register hooks, etc.
        """
        self.enabled = True
        self._logger.info("Plugin '%s' enabled", self.manifest.name)

    async def disable(self) -> None:
        """Disable the plugin.

        Called when an admin deactivates the plugin. Override to stop
        background tasks, unregister hooks, etc.
        """
        self.enabled = False
        self._logger.info("Plugin '%s' disabled", self.manifest.name)


class PluginRegistry:
    """Global registry for loaded plugins.

    Singleton pattern ensures all plugin manager instances share the same
    plugin state.
    """

    _instance: Optional[PluginRegistry] = None
    _plugins: Dict[str, BasePlugin] = {}

    def __new__(cls) -> PluginRegistry:
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._plugins = {}
        return cls._instance

    def register(self, plugin: BasePlugin) -> None:
        """Register a loaded plugin."""
        self._plugins[plugin.manifest.name] = plugin

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name."""
        self._plugins.pop(name, None)

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def get_all(self) -> Dict[str, BasePlugin]:
        """Get all registered plugins."""
        return self._plugins.copy()

    def clear(self) -> None:
        """Clear all registered plugins (for testing)."""
        self._plugins.clear()
