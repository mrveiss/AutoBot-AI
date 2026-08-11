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
from typing import Any, Dict, List

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
        # #13677: the load tally, so "is the plugin subsystem working?" is a
        # QUERY and not a log-reading exercise. A stream of per-plugin lines
        # nobody totals is why 0-of-7 and "no plugins installed" looked the same.
        self._load_report: Dict[str, object] = {
            "discovered": 0,
            "loaded": 0,
            "failed": [],
            "conflicts": [],
            "started": False,
            # #13677 review: `started` alone made a CRASHED discovery
            # indistinguishable from an empty tree — both reported
            # discovered=0, loaded=0, started=True. That is this issue's own
            # conflation one level up, so the outcome is its own key.
            "completed": False,
        }

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

        # #14000: set BEFORE discovery, deliberately, and that is the wedge this
        # issue is about — a discovery that raises leaves the flag True, so every
        # later startup() is a no-op reporting success while nothing is loaded.
        # The flag stays as-is because callers rely on the idempotence contract;
        # `retry_discovery()` below is the way out, so an operator who sees the
        # #13677 report has an action that is not "restart the service".
        self._started = True
        logger.info("PluginManager: starting plugin discovery")

        # Dedupe by name. lifespan.py passes BOTH the deployed plugin root and
        # the dev fallback, which overlap — this issue's own title says
        # "discovery runs twice". Undeduped, the second registration of a
        # HEALTHY plugin raises "Plugin already registered", is swallowed, and
        # lands in `failed`: the live config reported discovered=14 with five
        # perfectly-loaded plugins named as casualties. A signal built to end a
        # misdiagnosis must not manufacture one (#13677 review).
        # The LOADER dedupes now, because it also owns `_manifest_dirs` — the map
        # that decides which code runs. Deduping in two places with opposite
        # precedence is what let one plugin's code run under another's manifest.
        manifests = self._loader.discover_plugins()
        logger.info("PluginManager: discovered %d plugin(s)", len(manifests))

        loaded: List[str] = []
        failed: List[str] = []

        for manifest in manifests:
            try:
                plugin = await self._loader.load_plugin(manifest)
                if plugin:
                    await plugin.enable()
                    loaded.append(manifest.name)
                    logger.info(
                        "PluginManager: loaded and enabled '%s' v%s",
                        manifest.name,
                        manifest.version,
                    )
                else:
                    # #13677: load_plugin returns None far more often than it
                    # raises, and this branch logged NOTHING — the loader's own
                    # error was the only trace, and it names a module rather than
                    # a plugin. Six of seven core plugins failed exactly here.
                    failed.append(manifest.name)
                    logger.error(
                        "PluginManager: plugin '%s' did not load (entry point %s)",
                        manifest.name,
                        manifest.entry_point,
                    )
            except Exception as exc:  # noqa: BLE001
                failed.append(manifest.name)
                logger.error(
                    "PluginManager: failed to load plugin '%s': %s",
                    manifest.name,
                    exc,
                    exc_info=True,
                )

        self._record_load_report(manifests, loaded, failed)

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
        # #13677: reset the tally too — after shutdown the previous run's counts would
        # describe a subsystem that is no longer running, and "loaded 5 of 7"
        # from a dead manager is worse than no answer.
        self._load_report = {
            "discovered": 0,
            "loaded": 0,
            "failed": [],
            "conflicts": [],
            "started": False,
            "completed": False,
        }
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

    def _record_load_report(self, manifests: List, loaded: List[str], failed: List[str]) -> None:
        """Emit the `loaded N of M` summary and store it for querying (#13677).

        The per-plugin lines above are necessary and not sufficient: nothing
        totalled them, so a run where every plugin failed produced the same
        shape of output as a healthy one — and a host with no plugins installed
        produced the same shape as a host where all seven were broken.

        Total failure is logged at CRITICAL rather than ERROR because it is a
        different condition: not "a plugin is broken" but "the plugin subsystem
        delivered nothing", which is invisible in every other signal.
        """
        self._load_report = {
            "discovered": len(manifests),
            "loaded": len(loaded),
            "failed": sorted(failed),
            # set(): three dirs claiming one name appended twice, so a check doing
            # len(conflicts) read two shadowed plugins where there is one.
            # Direct attribute access, not getattr-with-default: a duck-typed
            # loader missing it would have rendered as a clean "no conflicts".
            "conflicts": sorted(set(self._loader.name_conflicts)),
            "started": True,
            "completed": True,
        }

        if not manifests:
            logger.info("PluginManager: no plugins discovered — nothing to load")
            return

        if not loaded:
            logger.critical(
                "PluginManager: loaded 0 of %d plugin(s) — the plugin subsystem is " "delivering nothing. Failed: %s",
                len(manifests),
                ", ".join(sorted(failed)) or "unknown",
            )
            return

        level = logger.warning if failed else logger.info
        level(
            "PluginManager: loaded %d of %d plugin(s)%s",
            len(loaded),
            len(manifests),
            f" — failed: {', '.join(sorted(failed))}" if failed else "",
        )

    async def retry_discovery(self) -> Dict[str, Any]:
        """Re-run discovery after a crashed startup, and report what happened.

        #14000: `startup()` marks itself started before discovery runs, so a
        crash there wedges the manager permanently — no plugins, a flag saying
        startup succeeded, and no way back short of a process restart. #13677
        made that state *visible* (`completed: False`); this makes it
        recoverable.

        Refuses when the previous run completed, because re-importing modules
        that already registered their plugins raises "Plugin already
        registered" and would turn a healthy manager into a broken one — the
        exact failure #13677's dedupe work exists to prevent.

        Returns:
            The load report for the new attempt, or the existing one unchanged
            when there was nothing to recover.
        """
        if self._load_report.get("completed"):
            logger.info("PluginManager.retry_discovery(): last startup completed — nothing to retry")
            return self.get_load_report()

        logger.warning("PluginManager.retry_discovery(): re-running discovery after an incomplete startup")
        self._started = False
        await self.startup()
        return self.get_load_report()

    def get_load_report(self) -> Dict[str, object]:
        """Return the startup load tally.

        The umbrella (#13852) asks that a service which is running but not
        working be distinguishable by something a check can QUERY. A log line
        does not satisfy that; this does.
        """
        report = dict(self._load_report)
        # Copy the list too: `dict()` is shallow, so a caller appending to
        # report["failed"] was mutating the manager's own tally.
        failed = self._load_report.get("failed", [])
        report["failed"] = list(failed) if isinstance(failed, list) else []
        # `started` is derived (the manager IS running); `completed` stays
        # stored. Deriving both made a crashed discovery report exactly like an
        # empty tree — the conflation this issue exists to remove.
        report["started"] = self._started
        conflicts = self._load_report.get("conflicts", [])
        report["conflicts"] = list(conflicts) if isinstance(conflicts, list) else []
        return report

    def get_plugin_status(self) -> Dict[str, str]:
        """Return a mapping of plugin name → status string."""
        return {name: plugin.status.value for name, plugin in self._registry.get_all_plugins().items()}

    def is_enabled(self, plugin_name: str) -> bool:
        """Return True if the named plugin is in ENABLED state."""
        plugin = self._registry.get_plugin(plugin_name)
        return plugin is not None and plugin.status == PluginStatus.ENABLED
