# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin Loader

Dynamic plugin discovery and loading system.

Issue #730 - Plugin SDK for extensible tool architecture.
Issue #6970 - Validate declared hooks against HOOK_REGISTRY on load.
Issue #6971 - Raise PluginLoadError for missing required env vars.
"""

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Type

from .base import BasePlugin, PluginLoadError, PluginManifest, PluginRegistry, PluginStatus
from .hooks import validate_hook_names
from .unified_registry import get_unified_registry

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Plugin discovery and loading system.

    Discovers plugins from filesystem, loads manifests, and instantiates plugins.
    """

    def __init__(self, plugin_dirs: List[Path] | None = None) -> None:
        """
        Initialize plugin loader.

        Args:
            plugin_dirs: List of directories to search for plugins
        """
        self.plugin_dirs = plugin_dirs or []
        self.registry = PluginRegistry()
        # Plugin name -> on-disk directory, captured at discovery. Core plugins
        # live in hyphenated dirs (plugins/core-plugins/hello-plugin) whose dotted
        # entry_point (plugins.core_plugins.hello_plugin.main) is not importable;
        # the dir lets the loader import the module file by path instead (#10294).
        self._manifest_dirs: Dict[str, Path] = {}

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
                    self._manifest_dirs[manifest.name] = manifest_file.parent
                    logger.info("Discovered plugin: %s v%s", manifest.name, manifest.version)

                except Exception as e:
                    logger.error(
                        "Failed to load manifest %s: %s",
                        manifest_file,
                        e,
                        exc_info=True,
                    )

        return manifests

    async def load_plugin(self, manifest: PluginManifest, config: Dict | None = None) -> BasePlugin | None:
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

            # Validate declared hooks against HOOK_REGISTRY (GH#6970)
            if manifest.hooks:
                validate_hook_names(manifest.hooks, plugin_name=manifest.name)

            # Check required environment variables (GH#6971)
            missing_required, missing_optional = self._check_required_env(manifest)
            if missing_required:
                raise PluginLoadError(
                    f"Cannot load plugin '{manifest.name}': " f"required env vars not set: {missing_required}"
                )
            if missing_optional:
                logger.info(
                    "Plugin %s loaded with optional env vars unset: %s",
                    manifest.name,
                    missing_optional,
                )

            # Import plugin module
            plugin_class = self._import_plugin_class(manifest.entry_point, self._manifest_dirs.get(manifest.name))
            if not plugin_class:
                return None

            # Instantiate plugin
            plugin = plugin_class(manifest, config)

            # Initialize plugin
            await plugin.initialize()
            plugin.status = PluginStatus.LOADED

            # Register with plugin registry and unified registry
            self.registry.register(plugin)
            get_unified_registry().register(manifest)

            logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)
            return plugin

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", manifest.name, e, exc_info=True)
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

            # Unregister from plugin registry and unified registry
            self.registry.unregister(name)
            get_unified_registry().unregister(name)

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

    def _check_required_env(self, manifest: PluginManifest) -> Tuple[List[str], List[str]]:
        """
        Check which env vars declared by the manifest are unset.

        Returns:
            Tuple of (missing_required, missing_optional) env var names.
            An env var set to an empty string is treated as missing.
        """
        missing_required: List[str] = []
        missing_optional: List[str] = []
        for env in manifest.required_env:
            if not os.environ.get(env.name):
                if env.required:
                    missing_required.append(env.name)
                else:
                    missing_optional.append(env.name)
        return missing_required, missing_optional

    def get_env_status(self, plugin_name: str) -> Dict[str, Dict[str, object]] | None:
        """
        Return per-env-var configuration status for a loaded plugin.

        SECURITY: response NEVER contains env var values, only the
        configured/missing boolean and the manifest metadata.

        Args:
            plugin_name: Name of a loaded plugin

        Returns:
            Dict mapping env-var name to status dict, or None if the
            plugin is not loaded.
        """
        plugin = self.registry.get_plugin(plugin_name)
        if plugin is None:
            return None
        return {
            env.name: {
                "configured": bool(os.environ.get(env.name)),  # ssot-config-exempt: dynamic env var name
                "secret": env.secret,
                "required": env.required,
                "description": env.description,
                "docs_url": env.docs_url,
                "obtain_steps": list(env.obtain_steps),
            }
            for env in plugin.manifest.required_env
        }

    def _import_plugin_class(self, entry_point: str, plugin_dir: Path | None = None) -> Type[BasePlugin] | None:
        """
        Import plugin class from entry point.

        Tries ``importlib.import_module(entry_point)`` first. When that fails
        (core plugins whose hyphenated directory is not importable as a dotted
        module — #10294), falls back to loading the module file from the plugin's
        on-disk directory via ``importlib.util.spec_from_file_location``.

        Args:
            entry_point: Python module path (e.g., 'plugins.core_plugins.hello_plugin.main')
            plugin_dir:  Directory containing plugin.json — used for the file-path fallback.

        Returns:
            Plugin class or None on failure
        """
        try:
            module = None
            try:
                module = importlib.import_module(entry_point)
            except ModuleNotFoundError as exc:
                module = self._import_from_file(entry_point, plugin_dir)
                if module is None:
                    logger.error("Failed to import plugin module %s: %s", entry_point, exc)
                    return None

            # Look for Plugin class or class with 'Plugin' suffix
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                    return attr

            logger.error("No plugin class found in module: %s", entry_point)
            return None

        except Exception as e:
            logger.error("Failed to import plugin %s: %s", entry_point, e, exc_info=True)
            return None

    def _import_from_file(self, entry_point: str, plugin_dir: Path | None):
        """Load a plugin module by file path from its on-disk directory (#10294)."""
        if plugin_dir is None:
            return None
        module_file = entry_point.rsplit(".", 1)[-1] + ".py"  # "...main" -> main.py
        module_path = Path(plugin_dir) / module_file
        if not module_path.is_file():
            logger.error("Plugin module file not found for %s at %s", entry_point, module_path)
            return None
        spec = importlib.util.spec_from_file_location(entry_point, module_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Register before exec so intra-plugin dataclasses / relative refs resolve.
        sys.modules[entry_point] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(entry_point, None)
            logger.error("File-path import failed for %s at %s: %s", entry_point, module_path, exc)
            return None
        logger.info("Loaded plugin module %s from %s (file-path fallback)", entry_point, module_path)
        return module

    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        """Get all loaded plugins."""
        return self.registry.get_all_plugins()

    def get_plugin_info(self, name: str) -> Dict | None:
        """Get plugin information."""
        plugin = self.registry.get_plugin(name)
        return plugin.get_info() if plugin else None
