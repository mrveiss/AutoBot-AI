# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin Loader

Discovers, loads, and manages plugin lifecycle with capability enforcement.

Issue #9049 - Plugin capability manifest system.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

from .base import BasePlugin, PluginManifest, PluginRegistry
from .capabilities import CapabilityChecker

logger = get_logger(__name__)


class PluginLoader:
    """Plugin discovery and loading service with capability enforcement.

    Scans plugin directories for plugin.json manifests, loads plugin modules,
    and enforces capability permissions at install/load time.

    Issue #9049.
    """

    def __init__(self, plugin_dirs: List[Path]):
        """Initialize plugin loader.

        Args:
            plugin_dirs: List of directories to scan for plugins
        """
        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self.registry = PluginRegistry()
        self.capability_checker = CapabilityChecker()
        self._logger = get_logger(__name__)
        # Plugin name -> on-disk source directory, captured at discovery so the
        # loader can import the module by file path. The manifest entry_point
        # (e.g. "plugins.core_plugins.hello_plugin.main") is NOT importable: the
        # on-disk dirs are hyphenated ("plugins/core-plugins/hello-plugin") and
        # not on sys.path, so import_module silently failed for every core
        # plugin (#10294).
        self._manifest_dirs: Dict[str, Path] = {}

    def discover_plugins(self) -> List[PluginManifest]:
        """Discover all plugins from configured directories.

        Scans each plugin directory for plugin.json manifests and parses them.

        Returns:
            List of discovered plugin manifests
        """
        manifests: List[PluginManifest] = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                self._logger.debug("Plugin directory does not exist: %s", plugin_dir)
                continue

            for subdir in plugin_dir.iterdir():
                if not subdir.is_dir():
                    continue

                manifest_path = subdir / "plugin.json"
                if not manifest_path.is_file():
                    continue

                try:
                    with manifest_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    manifest = PluginManifest(**data)
                    manifests.append(manifest)
                    self._manifest_dirs[manifest.name] = subdir
                    self._logger.debug(
                        "Discovered plugin: %s v%s",
                        manifest.name,
                        manifest.version,
                    )
                except Exception as exc:
                    self._logger.error(
                        "Failed to parse plugin manifest at %s: %s",
                        manifest_path,
                        exc,
                        exc_info=True,
                    )

        return manifests

    def _import_entry_point(self, manifest: PluginManifest):
        """Import a plugin's module, preferring file-path import (#10294).

        Core plugins live in hyphenated dirs (``plugins/core-plugins/hello-plugin``)
        that are not importable via the dotted ``entry_point``. Load the module
        file directly from the discovered source directory; fall back to
        ``import_module`` for plugins genuinely installed on ``sys.path``.

        The module is registered in ``sys.modules`` under ``entry_point`` so that
        intra-plugin dataclasses and relative refs resolve to the correct module name.
        """
        import sys

        source_dir = self._manifest_dirs.get(manifest.name)
        if source_dir is not None:
            module_file = manifest.entry_point.rsplit(".", 1)[-1] + ".py"  # "...main" -> main.py
            module_path = source_dir / module_file
            if module_path.is_file():
                spec = importlib.util.spec_from_file_location(manifest.entry_point, module_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    # Register before exec so intra-plugin dataclasses/relative refs resolve.
                    sys.modules[manifest.entry_point] = module
                    try:
                        spec.loader.exec_module(module)  # type: ignore[union-attr]
                        self._logger.info(
                            "Loaded plugin module %r from %s (file-path fallback)",
                            manifest.entry_point,
                            module_path,
                        )
                        return module
                    except Exception as exc:
                        sys.modules.pop(manifest.entry_point, None)
                        self._logger.warning(
                            "File-path fallback failed for %r at %s: %s",
                            manifest.entry_point,
                            module_path,
                            exc,
                        )
        try:
            return importlib.import_module(manifest.entry_point)
        except ModuleNotFoundError as exc:
            self._logger.error(
                "Plugin '%s' module not importable (entry_point=%s, source_dir=%s): %s",
                manifest.name,
                manifest.entry_point,
                source_dir,
                exc,
            )
            return None

    @staticmethod
    def _resolve_plugin_class(module):
        """Return the plugin class: explicit ``Plugin`` export, else a BasePlugin subclass (#10294)."""
        plugin_class = getattr(module, "Plugin", None)
        if isinstance(plugin_class, type) and issubclass(plugin_class, BasePlugin):
            return plugin_class
        for attr in vars(module).values():
            if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                if getattr(attr, "__module__", None) == module.__name__:
                    return attr
        return None

    async def load_plugin(
        self,
        manifest: PluginManifest,
        config: Optional[Dict[str, Any]] = None,
        grant_capabilities: bool = True,
    ) -> Optional[BasePlugin]:
        """Load a plugin from its manifest.

        Args:
            manifest: Plugin manifest
            config: Runtime configuration
            grant_capabilities: If True, automatically grant declared capabilities
                                (used for auto-install; set False for manual approval)

        Returns:
            Loaded plugin instance, or None if load failed
        """
        try:
            # Import plugin module (by file path; see _import_entry_point) (#10294)
            module = self._import_entry_point(manifest)
            if module is None:
                return None

            # Resolve the plugin class: prefer an explicit ``Plugin`` export,
            # otherwise fall back to the module's BasePlugin subclass so a plugin
            # that forgot the ``Plugin = MyPlugin`` alias still loads instead of
            # silently failing to register (#10294).
            plugin_class = self._resolve_plugin_class(module)
            if plugin_class is None:
                self._logger.error(
                    "Plugin module '%s' exports no 'Plugin' alias or BasePlugin subclass",
                    manifest.entry_point,
                )
                return None

            # Instantiate plugin
            plugin = plugin_class(manifest, config)

            # Grant capabilities if auto-approve is enabled
            if grant_capabilities:
                self.capability_checker.grant_capabilities(
                    manifest.name,
                    manifest.capabilities,
                )
                self._logger.info(
                    "Auto-granted capabilities for plugin '%s': %s",
                    manifest.name,
                    [cap.value for cap in manifest.capabilities],
                )

            # Initialize plugin
            await plugin.initialize()

            # Register in global registry
            self.registry.register(plugin)

            self._logger.info(
                "Loaded plugin: %s v%s (trust: %s, caps: %s)",
                manifest.name,
                manifest.version,
                manifest.trust_tier.value,
                len(manifest.capabilities),
            )

            return plugin

        except Exception as exc:
            self._logger.error(
                "Failed to load plugin '%s': %s",
                manifest.name,
                exc,
                exc_info=True,
            )
            return None

    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin by name.

        Args:
            plugin_name: Plugin identifier

        Returns:
            True if plugin was unloaded, False if not found
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            return False

        try:
            # Shutdown plugin
            await plugin.shutdown()

            # Revoke capabilities
            self.capability_checker.revoke_capabilities(plugin_name)

            # Unregister from registry
            self.registry.unregister(plugin_name)

            self._logger.info("Unloaded plugin: %s", plugin_name)
            return True

        except Exception as exc:
            self._logger.error(
                "Failed to unload plugin '%s': %s",
                plugin_name,
                exc,
                exc_info=True,
            )
            return False

    async def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin by name.

        Args:
            plugin_name: Plugin identifier

        Returns:
            True if plugin was reloaded, False if not found
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            return False

        manifest = plugin.manifest
        config = plugin.config

        # Unload existing plugin
        if not await self.unload_plugin(plugin_name):
            return False

        # Reload plugin
        reloaded = await self.load_plugin(manifest, config)
        return reloaded is not None

    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        """Get all loaded plugins.

        Returns:
            Dictionary mapping plugin names to plugin instances
        """
        return self.registry.get_all()

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get plugin information by name.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Plugin info dict, or None if not found
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            return None
        return plugin.get_info()

    def get_env_status(self, plugin_name: str) -> Optional[Dict[str, Dict]]:
        """Get environment variable status for a plugin.

        Returns configuration status for each required_env variable,
        never revealing actual values.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Dict mapping env var names to status metadata, or None if plugin not found
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            return None

        manifest = plugin.manifest
        env_status = {}

        for env_entry in manifest.required_env:
            var_name = env_entry.get("name")
            if not var_name:
                continue

            env_status[var_name] = {
                "configured": var_name in os.environ,
                "secret": env_entry.get("secret", False),
                "required": env_entry.get("required", False),
                "description": env_entry.get("description", ""),
                "docs_url": env_entry.get("docs_url"),
                "obtain_steps": env_entry.get("obtain_steps", []),
            }

        return env_status
