#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hot Reload Manager for AutoBot Development
Enables reloading of chat workflow modules without backend restart
"""

import asyncio
import importlib
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Optional, Set

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Issue #380: Module-level constants to avoid repeated Path computation
_SRC_ROOT = Path(__file__).parent.parent  # src/
_PROJECT_ROOT = _SRC_ROOT.parent  # project root

# Issue #380: Module-level frozenset for valid source root directories
_SOURCE_ROOTS: FrozenSet[str] = frozenset({"src", "backend"})


class ModuleReloadHandler(FileSystemEventHandler):
    """File system event handler for module reloading"""

    def __init__(self, reload_manager: "HotReloadManager"):
        """Initialize handler with reload manager and debounce settings."""
        self.reload_manager = reload_manager
        self.last_reload_time = {}
        self.reload_debounce = 1.0  # 1 second debounce

    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process Python files
        if file_path.suffix != ".py":
            return

        # Debounce rapid file changes
        now = time.time()
        if file_path in self.last_reload_time:
            if now - self.last_reload_time[file_path] < self.reload_debounce:
                return

        self.last_reload_time[file_path] = now

        # Schedule async reload
        asyncio.create_task(self.reload_manager._handle_file_change(file_path))


class HotReloadManager:
    """
    Manager for hot reloading Python modules during development
    Specifically designed for chat workflow components
    """

    def __init__(self):
        """Initialize hot reload manager with module tracking structures."""
        self.watched_modules: Dict[str, Any] = {}
        self.module_callbacks: Dict[str, Set[Callable]] = {}
        self.observer: Optional[Observer] = None
        self.watched_paths: Set[Path] = set()
        self.reload_lock = asyncio.Lock()

        # Chat workflow specific modules to watch
        # Note: Obsolete modules removed in Issue #567 archive cleanup
        self.chat_workflow_modules = [
            "src.async_chat_workflow",
        ]

    async def start(self) -> None:
        """Start the hot reload manager"""
        try:
            self.observer = Observer()
            handler = ModuleReloadHandler(self)

            # Watch the src directory for changes
            self.observer.schedule(handler, str(_SRC_ROOT), recursive=True)
            self.watched_paths.add(_SRC_ROOT)

            # Watch backend/api directory for API changes
            api_path = _PROJECT_ROOT / "backend" / "api"
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(api_path.exists):
                self.observer.schedule(handler, str(api_path), recursive=True)
                self.watched_paths.add(api_path)

            self.observer.start()
            logger.info(
                f"Hot reload manager started, watching {len(self.watched_paths)} paths"
            )

        except Exception as e:
            logger.error("Failed to start hot reload manager: %s", e)

    async def stop(self) -> None:
        """Stop the hot reload manager.

        Issue #378: Uses lock to prevent race condition when stopping
        while a reload might be in progress.
        """
        try:
            async with self.reload_lock:
                if self.observer:
                    self.observer.stop()
                    self.observer.join(timeout=5)
                    self.observer = None

                self.watched_modules.clear()
                self.module_callbacks.clear()
                self.watched_paths.clear()

            logger.info("Hot reload manager stopped")

        except Exception as e:
            logger.error("Error stopping hot reload manager: %s", e)

    def register_module(
        self, module_name: str, callback: Optional[Callable] = None
    ) -> None:
        """Register a module for hot reloading"""
        try:
            # Import the module initially
            module = importlib.import_module(module_name)
            self.watched_modules[module_name] = module

            # Register callback for reload notifications
            if callback:
                if module_name not in self.module_callbacks:
                    self.module_callbacks[module_name] = set()
                self.module_callbacks[module_name].add(callback)

            logger.debug("Registered module for hot reload: %s", module_name)

        except ImportError as e:
            logger.warning("Could not register module %s: %s", module_name, e)

    def register_chat_workflow_modules(
        self, callback: Optional[Callable] = None
    ) -> None:
        """Register all chat workflow modules for hot reloading"""
        for module_name in self.chat_workflow_modules:
            self.register_module(module_name, callback)

    async def reload_module(self, module_name: str) -> bool:
        """Manually reload a specific module"""
        async with self.reload_lock:
            try:
                if module_name in self.watched_modules:
                    # Clear module from sys.modules to force reload
                    if module_name in sys.modules:
                        del sys.modules[module_name]

                    # Clear any submodules
                    submodules_to_clear = [
                        name
                        for name in sys.modules.keys()
                        if name.startswith(module_name + ".")
                    ]
                    for submodule in submodules_to_clear:
                        del sys.modules[submodule]

                    # Reload the module
                    new_module = importlib.import_module(module_name)
                    self.watched_modules[module_name] = new_module

                    # Notify callbacks
                    await self._notify_callbacks(module_name, new_module)

                    logger.info("Successfully reloaded module: %s", module_name)
                    return True
                else:
                    logger.warning(
                        f"Module {module_name} not registered for hot reload"
                    )
                    return False

            except Exception as e:
                logger.error("Failed to reload module %s: %s", module_name, e)
                return False

    async def reload_chat_workflow(self) -> Dict[str, bool]:
        """Reload all chat workflow modules"""
        results = {}

        logger.info("Reloading chat workflow modules...")

        for module_name in self.chat_workflow_modules:
            if module_name in self.watched_modules:
                success = await self.reload_module(module_name)
                results[module_name] = success

        successful_reloads = sum(1 for success in results.values() if success)
        logger.info(
            f"Chat workflow reload complete: {successful_reloads}/{len(results)} modules reloaded"
        )

        return results

    async def _handle_file_change(self, file_path: Path) -> None:
        """Handle a file change event"""
        try:
            # Convert file path to module name
            module_name = self._path_to_module_name(file_path)

            if module_name and module_name in self.watched_modules:
                logger.debug("File changed: %s -> reloading %s", file_path, module_name)
                await self.reload_module(module_name)

        except Exception as e:
            logger.error("Error handling file change for %s: %s", file_path, e)

    def _path_to_module_name(self, file_path: Path) -> Optional[str]:
        """Convert a file path to a Python module name"""
        try:
            # Get path relative to project root
            relative_path = file_path.relative_to(_PROJECT_ROOT)

            # Convert to module name
            parts = relative_path.with_suffix("").parts
            if parts[0] in _SOURCE_ROOTS:
                return ".".join(parts)

            return None

        except (ValueError, IndexError):
            return None

    async def _notify_callbacks(self, module_name: str, new_module: Any) -> None:
        """Notify registered callbacks of module reload"""
        if module_name in self.module_callbacks:
            for callback in self.module_callbacks[module_name]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(module_name, new_module)
                    else:
                        callback(module_name, new_module)
                except Exception as e:
                    logger.error("Callback error for %s: %s", module_name, e)

    def get_module(self, module_name: str) -> Optional[Any]:
        """Get a registered module"""
        return self.watched_modules.get(module_name)

    def is_watching(self, module_name: str) -> bool:
        """Check if a module is being watched"""
        return module_name in self.watched_modules

    async def get_status(self) -> Dict[str, Any]:
        """Get hot reload manager status"""
        return {
            "running": self.observer is not None and self.observer.is_alive(),
            "watched_modules": list(self.watched_modules.keys()),
            "watched_paths": [str(path) for path in self.watched_paths],
            "callback_count": {
                module: len(callbacks)
                for module, callbacks in self.module_callbacks.items()
            },
        }


# Global hot reload manager instance
hot_reload_manager = HotReloadManager()


# Convenience functions
async def start_hot_reload() -> None:
    """Start the global hot reload manager"""
    await hot_reload_manager.start()


async def stop_hot_reload() -> None:
    """Stop the global hot reload manager"""
    await hot_reload_manager.stop()


async def reload_chat_workflow() -> Dict[str, bool]:
    """Reload chat workflow modules"""
    return await hot_reload_manager.reload_chat_workflow()


def register_chat_workflow_callback(callback: Callable) -> None:
    """Register a callback for chat workflow reloads"""
    hot_reload_manager.register_chat_workflow_modules(callback)


async def get_hot_reload_status() -> Dict[str, Any]:
    """Get hot reload status"""
    return await hot_reload_manager.get_status()
