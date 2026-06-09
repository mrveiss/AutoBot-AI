# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PluginManager Service

Application-level service that wires together PluginLoader and HookRegistry.
Handles startup discovery, ordered plugin loading, and graceful shutdown.

Issue #3278 - Plugin and extension system for third-party integrations.
"""

import logging
from pathlib import Path
from typing import Dict, List

from .base import PluginRegistry, PluginStatus
from .hooks import HookRegistry
from .loader import PluginLoader

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Application-level plugin manager.

    Coordinates plugin discovery, loading, hook registration, and lifecycle
    management.  Intended as a singleton owned by the FastAPI application.
    """

    def __init__(self, plugin_dirs: List[Path] | None = None) -> None:
        """
        Initialize plugin manager.

        Args:
            plugin_dirs: Directories to search for plugins.  If omitted the
                         manager boots without any search paths (plugins can
                         still be loaded explicitly via ``load_plugin``).
        """
        self._loader = PluginLoader(plugin_dirs or [])
        self._registry = PluginRegistry()
        self._hook_registry = HookRegistry()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """
        Discover and load all plugins found in the configured directories.

        Called once during application startup.  Failures for individual
        plugins are logged but do not abort startup.
        """
        if self._started:
            logger.warning("PluginManager.startup() called more than once — skipping")
            return

        self._started = True
        logger.info("PluginManager: starting plugin discovery")

        manifests = self._loader.discover_plugins()
        logger.info("PluginManager: discovered %d plugin(s)", len(manifests))

        for manifest in manifests:
            try:
                plugin = await self._loader.load_plugin(manifest)
                if plugin:
                    await plugin.enable()
                    logger.info(
                        "PluginManager: loaded and enabled '%s' v%s",
                        manifest.name,
                        manifest.version,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "PluginManager: failed to load plugin '%s': %s",
                    manifest.name,
                    exc,
                    exc_info=True,
                )

        await self._hook_registry.call_hook("on_startup")
        logger.info(
            "PluginManager: startup complete — %d plugin(s) active",
            len(self._registry.get_enabled_plugins()),
        )

    async def shutdown(self) -> None:
        """
        Disable and unload all active plugins.

        Called during application shutdown.  Errors are logged and do not
        prevent other plugins from shutting down.
        """
        await self._hook_registry.call_hook("on_shutdown")

        for name in list(self._registry.get_all_plugins()):
            try:
                await self._loader.unload_plugin(name)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "PluginManager: error unloading plugin '%s': %s",
                    name,
                    exc,
                    exc_info=True,
                )

        self._started = False
        logger.info("PluginManager: shutdown complete")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def hook_registry(self) -> HookRegistry:
        """Return the shared HookRegistry."""
        return self._hook_registry

    @property
    def plugin_registry(self) -> PluginRegistry:
        """Return the shared PluginRegistry."""
        return self._registry

    def get_plugin_status(self) -> Dict[str, str]:
        """Return a mapping of plugin name → status string."""
        return {name: plugin.status.value for name, plugin in self._registry.get_all_plugins().items()}

    def is_enabled(self, plugin_name: str) -> bool:
        """Return True if the named plugin is in ENABLED state."""
        plugin = self._registry.get_plugin(plugin_name)
        return plugin is not None and plugin.status == PluginStatus.ENABLED
