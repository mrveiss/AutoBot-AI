# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK Base Classes

Core plugin infrastructure including manifest schema, base plugin class,
and plugin registry for managing plugin lifecycle.

Issue #730 - Plugin SDK for extensible tool architecture.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class PluginStatus(str, Enum):
    """Plugin lifecycle status."""

    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class PluginManifest(BaseModel):
    """
    Plugin manifest schema.

    Defines plugin metadata, dependencies, and configuration.
    """

    name: str = Field(..., description="Unique plugin identifier")
    version: str = Field(..., description="Semantic version (e.g., 1.0.0)")
    display_name: str = Field(..., description="Human-readable plugin name")
    description: str = Field(..., description="Plugin description")
    author: str = Field(..., description="Plugin author")
    entry_point: str = Field(
        ..., description="Python module path (e.g., 'plugins.hello_plugin.main')"
    )
    dependencies: List[str] = Field(
        default_factory=list, description="Required plugin names"
    )
    config_schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON schema for plugin configuration"
    )
    hooks: List[str] = Field(
        default_factory=list, description="Hook names this plugin provides"
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate semantic version format."""
        parts = v.split(".")
        if len(parts) != 3:
            raise ValueError("Version must be in format X.Y.Z")
        for part in parts:
            if not part.isdigit():
                raise ValueError("Version parts must be numeric")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate plugin name format."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Plugin name must be alphanumeric with - or _")
        return v


class BasePlugin(ABC):
    """
    Abstract base class for all plugins.

    Plugins must inherit from this class and implement lifecycle methods.
    """

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        """
        Initialize plugin.

        Args:
            manifest: Plugin manifest
            config: Plugin configuration dictionary
        """
        self.manifest = manifest
        self.config = config or {}
        self.status = PluginStatus.UNLOADED
        self._logger = logging.getLogger(f"plugin.{manifest.name}")

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize plugin resources.

        Called when plugin is loaded. Should set up any required resources.
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean up plugin resources.

        Called when plugin is unloaded. Should release all resources.
        """

    async def enable(self) -> None:
        """
        Enable plugin.

        Called when plugin transitions from disabled to enabled state.
        Override to add custom enable logic.
        """
        self.status = PluginStatus.ENABLED
        self._logger.info("Plugin enabled: %s", self.manifest.name)

    async def disable(self) -> None:
        """
        Disable plugin.

        Called when plugin transitions from enabled to disabled state.
        Override to add custom disable logic.
        """
        self.status = PluginStatus.DISABLED
        self._logger.info("Plugin disabled: %s", self.manifest.name)

    async def reload(self) -> None:
        """
        Reload plugin.

        Default implementation: shutdown then initialize.
        Override for custom reload logic.
        """
        self._logger.info("Reloading plugin: %s", self.manifest.name)
        await self.shutdown()
        await self.initialize()

    def get_info(self) -> Dict[str, Any]:
        """Get plugin information."""
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "display_name": self.manifest.display_name,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "status": self.status.value,
            "hooks": self.manifest.hooks,
        }


class PluginRegistry:
    """
    Singleton registry for managing loaded plugins.

    Provides centralized plugin management and lifecycle control.
    """

    _instance: Optional["PluginRegistry"] = None
    _plugins: Dict[str, BasePlugin] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, plugin: BasePlugin) -> None:
        """
        Register a plugin.

        Args:
            plugin: Plugin instance to register

        Raises:
            ValueError: If plugin name already registered
        """
        name = plugin.manifest.name
        if name in self._plugins:
            raise ValueError(f"Plugin already registered: {name}")

        self._plugins[name] = plugin
        logger.info("Registered plugin: %s v%s", name, plugin.manifest.version)

    def unregister(self, name: str) -> None:
        """
        Unregister a plugin.

        Args:
            name: Plugin name to unregister
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info("Unregistered plugin: %s", name)

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """
        Get plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name)

    def get_all_plugins(self) -> Dict[str, BasePlugin]:
        """Get all registered plugins."""
        return self._plugins.copy()

    def get_enabled_plugins(self) -> Dict[str, BasePlugin]:
        """Get all enabled plugins."""
        return {
            name: plugin
            for name, plugin in self._plugins.items()
            if plugin.status == PluginStatus.ENABLED
        }

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()
        logger.info("Cleared plugin registry")
