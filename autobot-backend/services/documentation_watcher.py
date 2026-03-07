# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Watcher Service - Real-time sync for documentation changes.

Issue #165: Watches the docs/ directory for changes and triggers incremental
reindexing of modified documentation files.

Features:
- File system monitoring using watchdog
- Debounced change detection (avoids rapid reindexing)
- Incremental reindexing (only changed files)
- WebSocket notifications for frontend updates
- Background processing to avoid blocking
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

# Debounce settings
DEBOUNCE_SECONDS = 2.0  # Wait for file to stabilize before reindexing
BATCH_WINDOW_SECONDS = 5.0  # Batch multiple changes within this window


class DocumentationChangeHandler(FileSystemEventHandler):
    """Handles file system events for documentation files."""

    def __init__(self, watcher: "DocumentationWatcherService"):
        """Initialize handler with reference to watcher service."""
        self.watcher = watcher
        self._last_event_time: Dict[str, float] = {}

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        self._handle_change(event.src_path, "modified")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._handle_change(event.src_path, "created")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return
        self._handle_change(event.src_path, "deleted")

    def _handle_change(self, file_path: str, change_type: str) -> None:
        """Process a file change event with debouncing."""
        path = Path(file_path)

        # Only process markdown files
        if path.suffix.lower() not in (".md", ".markdown"):
            return

        # Skip archive directories
        if "archive" in str(path).lower():
            return

        # Debounce rapid changes
        now = time.time()
        if file_path in self._last_event_time:
            if now - self._last_event_time[file_path] < DEBOUNCE_SECONDS:
                return

        self._last_event_time[file_path] = now

        # Queue the change for processing
        asyncio.create_task(self.watcher.queue_change(path, change_type))


class DocumentationWatcherService:
    """
    Service for monitoring documentation changes and triggering reindexing.

    Issue #165: Provides real-time sync between docs/ changes and the knowledge base.
    """

    _instance: Optional["DocumentationWatcherService"] = None

    def __init__(self):
        """Initialize the documentation watcher service."""
        self._observer: Optional[Observer] = None
        self._handler: Optional[DocumentationChangeHandler] = None
        self._is_running = False
        self._pending_changes: Dict[Path, str] = {}  # path -> change_type
        self._change_lock = asyncio.Lock()
        self._processing_task: Optional[asyncio.Task] = None
        self._last_batch_time = 0.0
        self._event_callbacks: Set[Callable] = set()
        self._stats = {
            "files_indexed": 0,
            "last_change": None,
            "errors": 0,
        }

    @classmethod
    def get_instance(cls) -> "DocumentationWatcherService":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self) -> bool:
        """
        Start watching the documentation directory.

        Returns:
            True if started successfully, False otherwise.
        """
        if self._is_running:
            logger.info("Documentation watcher already running")
            return True

        try:
            # Ensure docs directory exists
            if not DOCS_DIR.exists():
                logger.warning("Documentation directory does not exist: %s", DOCS_DIR)
                return False

            # Create observer and handler
            self._handler = DocumentationChangeHandler(self)
            self._observer = Observer()
            self._observer.schedule(self._handler, str(DOCS_DIR), recursive=True)

            # Start observer in background thread
            self._observer.start()
            self._is_running = True

            logger.info("Documentation watcher started - monitoring: %s", DOCS_DIR)
            return True

        except Exception as e:
            logger.error("Failed to start documentation watcher: %s", e)
            self._stats["errors"] += 1
            return False

    async def stop(self) -> None:
        """Stop watching the documentation directory."""
        if not self._is_running:
            return

        try:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5.0)
                self._observer = None

            if self._processing_task and not self._processing_task.done():
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass

            self._handler = None
            self._is_running = False
            self._pending_changes.clear()

            logger.info("Documentation watcher stopped")

        except Exception as e:
            logger.error("Error stopping documentation watcher: %s", e)

    async def queue_change(self, file_path: Path, change_type: str) -> None:
        """
        Queue a file change for processing.

        Args:
            file_path: Path to the changed file
            change_type: Type of change (created, modified, deleted)
        """
        async with self._change_lock:
            self._pending_changes[file_path] = change_type
            self._last_batch_time = time.time()

        # Start batch processing if not already running
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_pending_changes())

    async def _process_pending_changes(self) -> None:
        """Process pending file changes after batch window."""
        # Wait for batch window to complete
        await asyncio.sleep(BATCH_WINDOW_SECONDS)

        async with self._change_lock:
            if not self._pending_changes:
                return

            changes = dict(self._pending_changes)
            self._pending_changes.clear()

        # Process each change
        for file_path, change_type in changes.items():
            await self._process_single_change(file_path, change_type)

    async def _process_single_change(self, file_path: Path, change_type: str) -> None:
        """
        Process a single file change.

        Args:
            file_path: Path to the changed file
            change_type: Type of change
        """
        try:
            logger.info(
                "Processing documentation change: %s (%s)", file_path.name, change_type
            )

            if change_type == "deleted":
                await self._handle_deletion(file_path)
            else:
                await self._handle_update(file_path)

            self._stats["last_change"] = datetime.now().isoformat()
            self._stats["files_indexed"] += 1

            # Notify callbacks
            await self._notify_change(file_path, change_type)

        except Exception as e:
            logger.error("Error processing documentation change %s: %s", file_path, e)
            self._stats["errors"] += 1

    async def _handle_update(self, file_path: Path) -> None:
        """
        Handle a file creation or modification via DocIndexerService.

        Issue #1385: Uses ChromaDB-based DocIndexerService instead of Redis KB.

        Args:
            file_path: Path to the updated file
        """
        try:
            from services.knowledge.doc_indexer import get_doc_indexer_service

            indexer = get_doc_indexer_service()
            if not await indexer.initialize():
                logger.error("DocIndexerService not available for reindexing")
                return

            # force=True to re-index even if hash matches (file watcher
            # already debounced, so we trust it actually changed)
            result = await indexer.index_file(file_path, force=True)

            if result.success > 0:
                logger.info("Reindexed documentation: %s", file_path.name)
            elif result.skipped > 0:
                logger.debug("File unchanged, skipped: %s", file_path.name)
            else:
                logger.warning(
                    "Failed to reindex %s: %s",
                    file_path.name,
                    result.errors,
                )

        except Exception as e:
            logger.error("Error updating documentation %s: %s", file_path, e)
            raise

    async def _handle_deletion(self, file_path: Path) -> None:
        """
        Handle a file deletion by removing its chunks from ChromaDB.

        Issue #1385: Deletes chunks from autobot_docs collection by file_path
        metadata filter instead of scanning Redis facts.

        Args:
            file_path: Path to the deleted file
        """
        try:
            from services.knowledge.doc_indexer import get_doc_indexer_service

            indexer = get_doc_indexer_service()
            if not await indexer.initialize():
                logger.error("DocIndexerService not available for deletion")
                return

            relative_path = str(file_path.relative_to(PROJECT_ROOT))

            # Delete all chunks with this file_path from ChromaDB
            if indexer._collection:
                try:
                    indexer._collection.delete(where={"file_path": relative_path})
                    logger.info("Removed chunks for deleted file: %s", file_path.name)
                except Exception as del_err:
                    logger.warning(
                        "Could not delete chunks for %s: %s",
                        file_path.name,
                        del_err,
                    )

        except Exception as e:
            logger.error("Error handling deletion %s: %s", file_path, e)
            raise

    async def _notify_change(self, file_path: Path, change_type: str) -> None:
        """
        Notify registered callbacks about a documentation change.

        Args:
            file_path: Path to the changed file
            change_type: Type of change
        """
        event_data = {
            "type": "documentation_change",
            "file_path": str(file_path.relative_to(PROJECT_ROOT)),
            "change_type": change_type,
            "timestamp": datetime.now().isoformat(),
        }

        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_data)
                else:
                    callback(event_data)
            except Exception as e:
                logger.warning("Error in documentation change callback: %s", e)

    def register_callback(self, callback: Callable) -> None:
        """
        Register a callback for documentation changes.

        Args:
            callback: Function to call on changes
        """
        self._event_callbacks.add(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """
        Unregister a callback.

        Args:
            callback: Function to remove
        """
        self._event_callbacks.discard(callback)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get watcher statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            **self._stats,
            "is_running": self._is_running,
            "pending_changes": len(self._pending_changes),
            "docs_directory": str(DOCS_DIR),
        }

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._is_running


# Convenience functions
def get_documentation_watcher() -> DocumentationWatcherService:
    """Get the documentation watcher singleton instance."""
    return DocumentationWatcherService.get_instance()


async def start_documentation_watcher() -> bool:
    """Start the documentation watcher service."""
    watcher = get_documentation_watcher()
    return await watcher.start()


async def stop_documentation_watcher() -> None:
    """Stop the documentation watcher service."""
    watcher = get_documentation_watcher()
    await watcher.stop()
