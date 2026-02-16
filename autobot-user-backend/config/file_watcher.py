#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File watching and callback management for config changes.
"""

import asyncio
import logging
from typing import Any, Callable, Dict

from backend.constants.threshold_constants import FileWatcherConfig

logger = logging.getLogger(__name__)


class FileWatcherMixin:
    """Mixin providing file watching and change callback functionality"""

    async def _handle_config_file_change(
        self, config_type: str, file_path: Any, new_data: Any
    ) -> None:
        """Handle detected config file change (Issue #315: extracted to reduce nesting).

        Args:
            config_type: Type of config (e.g., 'main', 'settings')
            file_path: Path to the changed file
            new_data: Newly loaded config data
        """
        import time

        logger.info("Config file %s changed, reloading", file_path)

        # Update cache for main config
        if config_type == "main":
            self._config = new_data
            self._sync_cache_timestamp = time.time()

        # Save to Redis cache
        await self._save_to_redis_cache(config_type, new_data)

        # Notify callbacks
        await self._notify_callbacks(config_type, new_data)

    async def _check_file_change(
        self, config_type: str, file_path: Any, last_modified: float | None
    ) -> float | None:
        """Check for file changes and reload if needed (Issue #315: extracted).

        Args:
            config_type: Type of config being watched
            file_path: Path to the config file
            last_modified: Last known modification time

        Returns:
            Current modification time (or None if file doesn't exist)
        """
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_path.exists):
            return None

        # Issue #358 - avoid blocking
        file_stat = await asyncio.to_thread(file_path.stat)
        current_modified = file_stat.st_mtime

        # Detect change and reload
        if last_modified is not None and current_modified != last_modified:
            new_data = await self._read_file_async(file_path)
            if new_data:
                await self._handle_config_file_change(config_type, file_path, new_data)

        return current_modified

    def add_change_callback(self, config_type: str, callback: Callable) -> None:
        """Add callback for config changes"""
        if config_type not in self._callbacks:
            self._callbacks[config_type] = []
        self._callbacks[config_type].append(callback)

    async def _notify_callbacks(self, config_type: str, data: Dict[str, Any]) -> None:
        """Notify callbacks of config changes"""
        if config_type in self._callbacks:
            for callback in self._callbacks[config_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(config_type, data)
                    else:
                        callback(config_type, data)
                except Exception as e:
                    logger.error("Config callback error for %s: %s", config_type, e)

    async def start_file_watcher(self, config_type: str) -> None:
        """Start watching config file for changes"""
        if not self.settings.auto_reload:
            return

        if config_type in self._file_watchers:
            return  # Already watching

        # Determine file path
        if config_type == "settings":
            file_path = self.settings_file
        elif config_type == "main":
            file_path = self.base_config_file
        else:
            file_path = self.config_dir / f"{config_type}.json"

        async def watch_file():
            """Watch file for changes (Issue #315: refactored to reduce nesting)."""
            last_modified = None

            while True:
                try:
                    last_modified = await self._check_file_change(
                        config_type, file_path, last_modified
                    )
                    await asyncio.sleep(FileWatcherConfig.CHECK_INTERVAL_S)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("File watcher error for %s: %s", config_type, e)
                    await asyncio.sleep(FileWatcherConfig.ERROR_RETRY_INTERVAL_S)

        self._file_watchers[config_type] = asyncio.create_task(watch_file())
        logger.info("Started file watcher for %s config", config_type)

    async def stop_file_watcher(self, config_type: str) -> None:
        """Stop watching config file"""
        if config_type in self._file_watchers:
            self._file_watchers[config_type].cancel()
            try:
                await self._file_watchers[config_type]
            except asyncio.CancelledError:
                logger.debug("File watcher for %s cancelled", config_type)

            del self._file_watchers[config_type]
            logger.info("Stopped file watcher for %s config", config_type)
