# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Watchdog event handling for KB watch folders (#17546, #17547).

Split out of ``kb_folder_watcher.py`` when that file crossed the 600-line ceiling
adding delete and move handling. The seam is real rather than arbitrary: everything
here runs on the watchdog Observer thread and decides *whether* an event is worth
dispatching, while the service it hands to owns the event loop and the ingestion.

``WatchFolderConfig`` is imported only for typing -- this module reads attributes off
the config it is given and never constructs one, so importing it at runtime would
make the split a circular import for no benefit.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from services.kb_folder_watcher import KBFolderWatcherService, WatchFolderConfig

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 2.0  # Wait for file to stabilize before ingesting

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".html", ".htm"}


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
        # #17547: this used to require `event.src_path in self._last_event_time`,
        # described as "files we're tracking". That set is written only by
        # `_handle_change`, which `on_modified` reached only AFTER passing this
        # gate -- so a modification could never add its own file, and `on_created`
        # was the only thing that ever could. A file that predates this process
        # therefore never got an entry and every edit to it was dropped for ever,
        # on this process and on every later one, since each starts with an empty
        # dict. "Files we are tracking" was standing in for "files the KB has
        # ingested", and those sets were never the same.
        #
        # Nothing replaces the gate: the debounce in `_handle_change` already
        # covers the burst it plausibly guarded against, and does so without
        # needing to have seen the file before.
        self._handle_change(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events (#17546)."""
        if event.is_directory:
            return
        self._handle_change(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle a rename or move (#17546).

        Watchdog reports one event carrying both paths. It is dispatched as a
        delete of the old path and a create of the new one rather than a single
        "moved": the KB addresses a document by its `file_path` metadata, so a
        rename is exactly those two operations to everything downstream.

        The destination may be outside the watched folder, in which case the
        create half is filtered by `_handle_change`'s extension and file-type
        checks -- the delete still lands, which is the correct outcome.
        """
        if event.is_directory:
            return
        self._handle_change(event.src_path, "deleted")
        dest = getattr(event, "dest_path", None)
        if dest:
            self._handle_change(dest, "created")

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
        last_seen = self._last_event_time.get(file_path)
        if last_seen is not None and now - last_seen < DEBOUNCE_SECONDS:
            return

        # #15636: this runs on the watchdog Observer thread, which has no running
        # event loop, so ``asyncio.create_task`` raised RuntimeError on every
        # event and nothing was ever queued. The debounce stamp used to be
        # written before that failing call, which made the handler look alive;
        # it is now written only after the cross-thread hand-off succeeded.
        if self.watcher.dispatch_change(self.config.folder_id, path, change_type) is None:
            return

        self._last_event_time[file_path] = now
