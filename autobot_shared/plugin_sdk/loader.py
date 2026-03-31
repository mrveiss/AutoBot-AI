# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin Loader

Dynamic plugin discovery and loading system.

Issue #730 - Plugin SDK for extensible tool architecture.
"""

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from plugin_sdk.base import BasePlugin, PluginManifest, PluginRegistry, PluginStatus

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Plugin discovery and loading system.

    Discovers plugins from filesystem, loads manifests, and instantiates plugins.
    """

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        """
        Initialize plugin loader.

        Args:
            plugin_dirs: List of directories to search for plugins
        """
        self.plugin_dirs = plugin_dirs or []
        self.registry = PluginRegistry()

    def discover_plugins(self) -> List[PluginManifest]:
        """
        Discover all plugins in configured directories.

        Returns:
            List of plugin manifests found
        """
        manifests = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                logger.warning("Plugin directory does not exist: %s", plugin_dir)
                continue

            # Look for plugin.json files
            for manifest_file in plugin_dir.rglob("plugin.json"):
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    manifest = PluginManifest(**data)
                    manifests.append(manifest)
                    logger.info(
                        "Discovered plugin: %s v%s", manifest.name, manifest.version
                    )

                except Exception as e:
                    logger.error(
                        "Failed to load manifest %s: %s",
                        manifest_file,
                        e,
                        exc_info=True,
                    )

        return manifests

    async def load_plugin(
        self, manifest: PluginManifest, config: Optional[Dict] = None
    ) -> Optional[BasePlugin]:
        """
        Load a plugin from its manifest.

        Args:
            manifest: Plugin manifest
            config: Plugin configuration

        Returns:
            Loaded plugin instance or None on failure
        """
        try:
            # Check dependencies
            missing_deps = self._check_dependencies(manifest)
            if missing_deps:
                logger.error(
                    "Cannot load plugin %s: missing dependencies %s",
                    manifest.name,
                    missing_deps,
                )
                return None

            # Import plugin module
            plugin_class = self._import_plugin_class(manifest.entry_point)
            if not plugin_class:
                return None

            # Instantiate plugin
            plugin = plugin_class(manifest, config)

            # Initialize plugin
            await plugin.initialize()
            plugin.status = PluginStatus.LOADED

            # Register with registry
            self.registry.register(plugin)

            logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)
            return plugin

        except Exception as e:
            logger.error(
                "Failed to load plugin %s: %s", manifest.name, e, exc_info=True
            )
            return None

    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if successfully unloaded
        """
        try:
            plugin = self.registry.get_plugin(name)
            if not plugin:
                logger.warning("Plugin not found: %s", name)
                return False

            # Shutdown plugin
            await plugin.shutdown()
            plugin.status = PluginStatus.UNLOADED

            # Unregister from registry
            self.registry.unregister(name)

            logger.info("Unloaded plugin: %s", name)
            return True

        except Exception as e:
            logger.error("Failed to unload plugin %s: %s", name, e, exc_info=True)
            return False

    async def reload_plugin(self, name: str) -> bool:
        """
        Reload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if successfully reloaded
        """
        try:
            plugin = self.registry.get_plugin(name)
            if not plugin:
                logger.warning("Plugin not found: %s", name)
                return False

            # Use plugin's reload method
            await plugin.reload()

            logger.info("Reloaded plugin: %s", name)
            return True

        except Exception as e:
            logger.error("Failed to reload plugin %s: %s", name, e, exc_info=True)
            return False

    def _check_dependencies(self, manifest: PluginManifest) -> List[str]:
        """
        Check if plugin dependencies are loaded.

        Args:
            manifest: Plugin manifest

        Returns:
            List of missing dependency names
        """
        missing = []
        for dep in manifest.dependencies:
            if not self.registry.get_plugin(dep):
                missing.append(dep)
        return missing

    def _import_plugin_class(self, entry_point: str) -> Optional[Type[BasePlugin]]:
        """
        Import plugin class from entry point.

        Args:
            entry_point: Python module path (e.g., 'plugins.hello.main')

        Returns:
            Plugin class or None on failure
        """
        try:
            # Import module
            module = importlib.import_module(entry_point)

            # Look for Plugin class or class with 'Plugin' suffix
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                ):
                    return attr

            logger.error("No plugin class found in module: %s", entry_point)
            return None

        except Exception as e:
            logger.error(
                "Failed to import plugin %s: %s", entry_point, e, exc_info=True
            )
            return None

    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        """Get all loaded plugins."""
        return self.registry.get_all_plugins()

    def get_plugin_info(self, name: str) -> Optional[Dict]:
        """Get plugin information."""
        plugin = self.registry.get_plugin(name)
        return plugin.get_info() if plugin else None
