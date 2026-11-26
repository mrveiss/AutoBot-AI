# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Host-side reversal of what a plugin registered (#19302).

The host removes a plugin's hooks, tools and capability grants itself on
unload, so cleanup never depends on the plugin's own ``shutdown()``. Tools are
attributed to the plugin that registered them by ``registering_for_plugin``.
"""

import importlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from autobot_shared.plugin_attribution import registering_for_plugin
from autobot_shared.tool_sdk.registry import get_tool_registry

from .base import BasePlugin, PluginRegistry, PluginStatus
from .capabilities import CapabilityChecker
from .hooks import HookRegistry

if TYPE_CHECKING:
    from .loader import PluginLoader

logger = logging.getLogger(__name__)


def reverse_registrations(plugin_name: str) -> None:
    """Remove every hook, tool and capability grant recorded against *plugin_name*."""
    HookRegistry().unregister_plugin(plugin_name)
    get_tool_registry().unregister_plugin(plugin_name)
    CapabilityChecker().revoke_capabilities(plugin_name)


def rollback_failed_load(
    plugins: "PluginRegistry", unified: Callable[[], Any], name: str, registered: bool, manifest_registered: bool
) -> None:
    """Leave nothing half-registered after a failed load; never raises (#19302).

    Skipped when a live plugin of that name exists that this attempt did not register. The unified manifest
    registry is touched only when this attempt registered the manifest.
    """
    if not (registered or not plugins.get_plugin(name)):
        return
    try:
        reverse_registrations(name)  # what a raising initialize() registered
    except Exception:  # noqa: BLE001 -- the registries below must still be cleared
        logger.error("Could not reverse the registrations of failed plugin %s", name, exc_info=True)
    if registered:
        plugins.unregister(name)
    if manifest_registered:
        try:
            unified().unregister(name)
        except Exception:  # noqa: BLE001 -- a failing cleanup must not turn a failed load into a raise
            logger.error("Could not remove manifest %s from the unified registry", name, exc_info=True)


async def initialize_attributed(plugin: BasePlugin) -> None:
    """Run ``plugin.initialize()`` with its tool registrations attributed to the plugin (#19302)."""
    with registering_for_plugin(plugin.manifest.name):
        await plugin.initialize()


async def enable_attributed(plugin: BasePlugin) -> None:
    """Run ``plugin.enable()`` with the tools it registers attributed to the plugin (#19302)."""
    with registering_for_plugin(plugin.manifest.name):
        await plugin.enable()


def _own_modules(entry_point: str) -> list[str]:
    """The plugin's entry module and the modules beneath it; never its shared parent packages."""
    return [m for m in sys.modules if m == entry_point or m.startswith(entry_point + ".")]


def forget_module(entry_point: str) -> dict:
    """Drop the plugin's own modules so the next import reads new code; return them for restore.

    Bytecode is validated by source mtime (whole seconds) and size, so an edit made
    within the same second with the same size would reuse a stale ``.pyc``. The
    cached bytecode is removed and the finder caches invalidated so the source is re-read.
    """
    old = {m: sys.modules.pop(m) for m in _own_modules(entry_point)}
    for module in old.values():
        cached = getattr(module, "__cached__", None)
        if cached:
            Path(cached).unlink(missing_ok=True)
    importlib.invalidate_caches()
    return old


async def reload_with_fresh_code(loader: "PluginLoader", plugin: BasePlugin) -> bool:
    """Unload then load *plugin* from freshly imported code (#19302).

    An in-place ``plugin.reload()`` keeps the old module in ``sys.modules``, so
    changed code never ran. Capability grants and the enabled state carry over.
    Returns False when the unload or the load did not happen.
    """
    manifest, config = plugin.manifest, plugin.config
    was_enabled = plugin.status == PluginStatus.ENABLED
    grants = CapabilityChecker().get_granted_capabilities(manifest.name)
    if not await loader.unload_plugin(manifest.name):
        return False
    old_modules = forget_module(manifest.entry_point)
    reloaded = await loader.load_plugin(manifest, config)
    if reloaded is None:
        sys.modules.update(old_modules)  # keep the working code importable when the new load failed
        return False
    if grants:
        CapabilityChecker().grant_capabilities(manifest.name, grants)
    if was_enabled:
        await enable_attributed(reloaded)
    return True
