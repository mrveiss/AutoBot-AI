# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
KB Folder Watcher Service - Auto-ingest files from watched directories.

Issue #9000: Watches user-configured directories for new files and automatically
ingests them into knowledge base collections.

Features:
- Multiple watch folders with individual configurations
- Support for PDF, DOCX, TXT, MD, CSV, HTML files
- Per-folder target KB collection
- Redis-based configuration persistence
- Debounced change detection
- Background processing
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# Redis keys
WATCH_FOLDERS_KEY = "kb:watch_folders"
WATCH_FOLDER_CONFIG_PREFIX = "kb:watch_folder:"

# Debounce settings
DEBOUNCE_SECONDS = 2.0  # Wait for file to stabilize before ingesting
BATCH_WINDOW_SECONDS = 5.0  # Batch multiple changes within this window

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".html", ".htm"}


class WatchFolderConfig:
    """Configuration for a single watch folder."""

    def __init__(
        self,
        folder_id: str,
        path: str,
        collection: str,
        enabled: bool = True,
        file_types: Optional[List[str]] = None,
        recursive: bool = True,
        category: str = "uploads",
        tags: Optional[List[str]] = None,
    ):
        self.folder_id = folder_id
        self.path = path
        self.collection = collection
        self.enabled = enabled
        self.file_types = file_types or ["pdf", "docx", "txt", "md", "csv", "html"]
        self.recursive = recursive
        self.category = category
        self.tags = tags or []
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "folder_id": self.folder_id,
            "path": self.path,
            "collection": self.collection,
            "enabled": self.enabled,
            "file_types": self.file_types,
            "recursive": self.recursive,
            "category": self.category,
            "tags": self.tags,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatchFolderConfig":
        """Create from dictionary."""
        return cls(
            folder_id=data["folder_id"],
            path=data["path"],
            collection=data["collection"],
            enabled=data.get("enabled", True),
            file_types=data.get("file_types"),
            recursive=data.get("recursive", True),
            category=data.get("category", "uploads"),
            tags=data.get("tags", []),
        )


class KBFolderChangeHandler(FileSystemEventHandler):
    """Handles file system events for watched KB folders."""

    def __init__(self, watcher: "KBFolderWatcherService", config: WatchFolderConfig) -> None:
        self.watcher = watcher
        self.config = config
        self._last_event_time: Dict[str, float] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._handle_change(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        # Only process modifications for existing files we're tracking
        if event.src_path in self._last_event_time:
            self._handle_change(event.src_path, "modified")

    def _handle_change(self, file_path: str, change_type: str) -> None:
        """Process a file change event with debouncing."""
        path = Path(file_path)

        # Check if file extension is supported
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return

        # Check if file type is enabled for this folder
        file_ext = path.suffix.lower().lstrip(".")
        if file_ext not in self.config.file_types:
            return

        # Debounce rapid changes
        now = time.time()
        if file_path in self._last_event_time:
            if now - self._last_event_time[file_path] < DEBOUNCE_SECONDS:
                return

        self._last_event_time[file_path] = now

        # Queue the change for processing
        asyncio.create_task(self.watcher.queue_change(self.config.folder_id, path, change_type))


class KBFolderWatcherService:
    """
    Service for monitoring user-configured folders and auto-ingesting files into KB.

    Issue #9000: Provides automatic document ingestion from watched directories.
    """

    def __init__(self) -> None:
        """Initialize the KB folder watcher service."""
        self._observers: Dict[str, Observer] = {}  # folder_id -> Observer
        self._handlers: Dict[str, KBFolderChangeHandler] = {}  # folder_id -> Handler
        self._configs: Dict[str, WatchFolderConfig] = {}  # folder_id -> Config
        self._is_running = False
        self._pending_changes: Dict[str, List[tuple]] = {}  # folder_id -> [(path, change_type)]
        self._change_lock = asyncio.Lock()
        self._processing_tasks: Dict[str, asyncio.Task] = {}
        self._stats: Dict[str, Dict[str, Any]] = {}  # folder_id -> stats

    async def initialize(self) -> bool:
        """
        Initialize the service by loading configurations from Redis.

        Returns:
            True if initialized successfully.
        """
        try:
            redis = await get_async_redis_client(database="main")

            # Load all watch folder IDs
            folder_ids = await redis.smembers(WATCH_FOLDERS_KEY)

            if not folder_ids:
                logger.info("No watch folders configured")
                return True

            # Load each watch folder config
            for folder_id in folder_ids:
                config_key = f"{WATCH_FOLDER_CONFIG_PREFIX}{folder_id}"
                config_data = await redis.get(config_key)

                if config_data:
                    try:
                        config_dict = json.loads(config_data)
                        config = WatchFolderConfig.from_dict(config_dict)
                        self._configs[folder_id] = config

                        # Initialize stats
                        self._stats[folder_id] = {
                            "files_ingested": 0,
                            "last_change": None,
                            "errors": 0,
                        }

                        logger.info("Loaded watch folder config: %s (%s)", folder_id, config.path)
                    except Exception as e:
                        logger.error("Failed to load watch folder %s: %s", folder_id, e)

            self._is_running = True
            logger.info("KB Folder Watcher initialized with %d folders", len(self._configs))
            return True

        except Exception as e:
            logger.error("Failed to initialize KB Folder Watcher: %s", e)
            return False

    async def add_watch_folder(self, config: WatchFolderConfig) -> bool:
        """
        Add a new watch folder.

        Args:
            config: Watch folder configuration

        Returns:
            True if added successfully.
        """
        try:
            # Validate path exists
            path = Path(config.path)
            if not path.exists():
                logger.warning("Watch folder path does not exist: %s", config.path)
                return False

            if not path.is_dir():
                logger.warning("Watch folder path is not a directory: %s", config.path)
                return False

            # Save to Redis
            redis = await get_async_redis_client(database="main")
            config_key = f"{WATCH_FOLDER_CONFIG_PREFIX}{config.folder_id}"
            await redis.set(config_key, json.dumps(config.to_dict()))
            await redis.sadd(WATCH_FOLDERS_KEY, config.folder_id)

            # Add to local configs
            self._configs[config.folder_id] = config
            self._stats[config.folder_id] = {
                "files_ingested": 0,
                "last_change": None,
                "errors": 0,
            }

            # Start watching if enabled
            if config.enabled:
                await self._start_watching_folder(config)

            logger.info("Added watch folder: %s (%s)", config.folder_id, config.path)
            return True

        except Exception as e:
            logger.error("Failed to add watch folder %s: %s", config.folder_id, e)
            return False

    async def remove_watch_folder(self, folder_id: str) -> bool:
        """
        Remove a watch folder.

        Args:
            folder_id: ID of the folder to remove

        Returns:
            True if removed successfully.
        """
        try:
            # Stop watching
            await self._stop_watching_folder(folder_id)

            # Remove from Redis
            redis = await get_async_redis_client(database="main")
            config_key = f"{WATCH_FOLDER_CONFIG_PREFIX}{folder_id}"
            await redis.delete(config_key)
            await redis.srem(WATCH_FOLDERS_KEY, folder_id)

            # Remove from local state
            self._configs.pop(folder_id, None)
            self._stats.pop(folder_id, None)

            logger.info("Removed watch folder: %s", folder_id)
            return True

        except Exception as e:
            logger.error("Failed to remove watch folder %s: %s", folder_id, e)
            return False

    async def update_watch_folder(self, folder_id: str, enabled: bool) -> bool:
        """
        Enable or disable a watch folder.

        Args:
            folder_id: ID of the folder
            enabled: Whether to enable or disable

        Returns:
            True if updated successfully.
        """
        try:
            if folder_id not in self._configs:
                logger.warning("Watch folder not found: %s", folder_id)
                return False

            config = self._configs[folder_id]
            config.enabled = enabled

            # Update Redis
            redis = await get_async_redis_client(database="main")
            config_key = f"{WATCH_FOLDER_CONFIG_PREFIX}{folder_id}"
            await redis.set(config_key, json.dumps(config.to_dict()))

            # Start or stop watching
            if enabled:
                await self._start_watching_folder(config)
            else:
                await self._stop_watching_folder(folder_id)

            logger.info("Updated watch folder %s: enabled=%s", folder_id, enabled)
            return True

        except Exception as e:
            logger.error("Failed to update watch folder %s: %s", folder_id, e)
            return False

    async def _start_watching_folder(self, config: WatchFolderConfig) -> bool:
        """Start watching a specific folder."""
        try:
            if config.folder_id in self._observers:
                logger.info("Already watching folder: %s", config.folder_id)
                return True

            path = Path(config.path)
            if not path.exists():
                logger.warning("Watch folder path does not exist: %s", config.path)
                return False

            # Create observer and handler
            handler = KBFolderChangeHandler(self, config)
            observer = Observer()
            observer.schedule(handler, str(path), recursive=config.recursive)

            # Start observer
            observer.start()

            self._observers[config.folder_id] = observer
            self._handlers[config.folder_id] = handler

            logger.info("Started watching folder: %s (%s)", config.folder_id, config.path)
            return True

        except Exception as e:
            logger.error("Failed to start watching folder %s: %s", config.folder_id, e)
            if config.folder_id in self._stats:
                self._stats[config.folder_id]["errors"] += 1
            return False

    async def _stop_watching_folder(self, folder_id: str) -> None:
        """Stop watching a specific folder."""
        try:
            if folder_id in self._observers:
                observer = self._observers[folder_id]
                observer.stop()
                observer.join(timeout=5.0)
                del self._observers[folder_id]
                del self._handlers[folder_id]
                logger.info("Stopped watching folder: %s", folder_id)

            # Cancel processing task if running
            if folder_id in self._processing_tasks:
                task = self._processing_tasks[folder_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                del self._processing_tasks[folder_id]

        except Exception as e:
            logger.error("Error stopping watch folder %s: %s", folder_id, e)

    async def queue_change(self, folder_id: str, file_path: Path, change_type: str) -> None:
        """
        Queue a file change for processing.

        Args:
            folder_id: ID of the watch folder
            file_path: Path to the changed file
            change_type: Type of change (created, modified)
        """
        async with self._change_lock:
            if folder_id not in self._pending_changes:
                self._pending_changes[folder_id] = []
            self._pending_changes[folder_id].append((file_path, change_type))

        # Start batch processing if not already running
        if folder_id not in self._processing_tasks or self._processing_tasks[folder_id].done():
            self._processing_tasks[folder_id] = asyncio.create_task(self._process_pending_changes(folder_id))

    async def _process_pending_changes(self, folder_id: str) -> None:
        """Process pending file changes for a folder after batch window."""
        await asyncio.sleep(BATCH_WINDOW_SECONDS)

        async with self._change_lock:
            if folder_id not in self._pending_changes or not self._pending_changes[folder_id]:
                return

            changes = list(self._pending_changes[folder_id])
            self._pending_changes[folder_id] = []

        # Process each change
        for file_path, change_type in changes:
            await self._process_single_change(folder_id, file_path, change_type)

    async def _process_single_change(self, folder_id: str, file_path: Path, change_type: str) -> None:
        """Process a single file change by ingesting into KB."""
        try:
            config = self._configs[folder_id]
            logger.info(
                "Processing KB file change: %s (%s) for folder %s",
                file_path.name,
                change_type,
                folder_id,
            )

            # Read file content
            if not file_path.exists():
                logger.warning("File no longer exists: %s", file_path)
                return

            # Import the KB upload logic
            from api.knowledge import _extract_text_content, _validate_file_upload

            # Read file
            file_content = file_path.read_bytes()

            # Validate
            _validate_file_upload(file_path.name, len(file_content))

            # Extract text
            content = _extract_text_content(file_content, file_path.name)

            if not content:
                logger.warning("No content extracted from file: %s", file_path)
                return

            # Ingest into KB
            from knowledge_base import get_knowledge_base

            kb = get_knowledge_base()
            await kb.add_fact(
                content=content,
                category=config.category,
                tags=config.tags + [f"watch_folder:{folder_id}"],
                metadata={
                    "source": "watch_folder",
                    "folder_id": folder_id,
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "collection": config.collection,
                },
            )

            # Update stats
            if folder_id in self._stats:
                self._stats[folder_id]["files_ingested"] += 1
                self._stats[folder_id]["last_change"] = datetime.now(timezone.utc).isoformat()

            logger.info("Successfully ingested file: %s into collection %s", file_path.name, config.collection)

        except Exception as e:
            logger.error("Error processing file change %s: %s", file_path, e)
            if folder_id in self._stats:
                self._stats[folder_id]["errors"] += 1

    async def start_all(self) -> bool:
        """Start watching all enabled folders."""
        if not self._is_running:
            await self.initialize()

        success_count = 0
        for config in self._configs.values():
            if config.enabled:
                if await self._start_watching_folder(config):
                    success_count += 1

        logger.info("Started watching %d/%d folders", success_count, len(self._configs))
        return success_count > 0

    async def stop_all(self) -> None:
        """Stop watching all folders."""
        folder_ids = list(self._observers.keys())
        for folder_id in folder_ids:
            await self._stop_watching_folder(folder_id)

        self._is_running = False
        logger.info("Stopped all watch folders")

    def get_watch_folders(self) -> List[Dict[str, Any]]:
        """Get all watch folder configurations with stats."""
        result = []
        for folder_id, config in self._configs.items():
            stats = self._stats.get(folder_id, {})
            result.append(
                {
                    **config.to_dict(),
                    "is_watching": folder_id in self._observers,
                    "stats": stats,
                }
            )
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get overall watcher statistics."""
        total_folders = len(self._configs)
        active_folders = len(self._observers)
        total_ingested = sum(s.get("files_ingested", 0) for s in self._stats.values())
        total_errors = sum(s.get("errors", 0) for s in self._stats.values())

        return {
            "is_running": self._is_running,
            "total_folders": total_folders,
            "active_folders": active_folders,
            "total_files_ingested": total_ingested,
            "total_errors": total_errors,
            "folders": self.get_watch_folders(),
        }


# Singleton instance
get_kb_folder_watcher = lazy_singleton(KBFolderWatcherService)
"""Get the KB folder watcher singleton instance."""


async def start_kb_folder_watcher() -> bool:
    """Start the KB folder watcher service."""
    watcher = get_kb_folder_watcher()
    return await watcher.start_all()


async def stop_kb_folder_watcher() -> None:
    """Stop the KB folder watcher service."""
    watcher = get_kb_folder_watcher()
    await watcher.stop_all()
