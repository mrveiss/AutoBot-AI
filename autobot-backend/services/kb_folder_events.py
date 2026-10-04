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

    def _loggable(self, path: Path) -> str:
        """The event path relative to the watched root, for the drop logs.

        `path.name` alone cannot tell two files called `notes.txt` in different
        subfolders apart, which is exactly what a reader of a DROPPED line needs
        to know. The absolute path would put the host's filesystem layout into
        the log, which the project forbids, so only the part that varies inside
        the watched folder is kept. A path outside the root (a symlink target,
        say) has no meaningful relative form, so it degrades to the basename
        rather than leaking the root it actually sits under.
        """
        try:
            return str(path.relative_to(self.config.path))
        except ValueError:
            return path.name

    def _handle_change(self, file_path: str, change_type: str) -> None:
        """Process a file change event with debouncing.

        #17547 AC3: every ``return`` below drops a watch-folder event, and until
        this module logged, all of them were indistinguishable from "watchdog
        delivered no event at all". A user whose file silently fails to ingest had
        nothing to read. Each site now names the folder, the path, the change type
        and the reason, so the three causes are told apart in the log rather than
        guessed at.

        Levels follow ``kb_folder_watcher.py``, which this module was split out of:
        a routine, expected drop is ``debug`` (the watcher logs per-file progress at
        ``info`` and only genuine trouble above it), while a hand-off that failed is
        ``warning`` -- #15636 was exactly that failure running silently.
        """
        path = Path(file_path)
        folder_id = self.config.folder_id

        # Check if file extension is supported
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.debug(
                "Watch folder %s: ignoring %s of %s -- extension %r is not one the KB ingests (%s)",
                folder_id,
                change_type,
                self._loggable(path),
                path.suffix.lower(),
                ", ".join(sorted(SUPPORTED_EXTENSIONS)),
            )
            return

        # Check if file type is enabled for this folder
        file_ext = path.suffix.lower().lstrip(".")
        if file_ext not in self.config.file_types:
            logger.debug(
                "Watch folder %s: ignoring %s of %s -- file type %r is not enabled for this folder " "(enabled: %s)",
                folder_id,
                change_type,
                self._loggable(path),
                file_ext,
                ", ".join(sorted(self.config.file_types)) or "none",
            )
            return

        # Debounce rapid changes
        now = time.time()
        last_seen = self._last_event_time.get(file_path)
        if last_seen is not None and now - last_seen < DEBOUNCE_SECONDS:
            logger.debug(
                "Watch folder %s: coalescing %s of %s -- %.2fs since the last dispatch, " "under the %.1fs debounce",
                folder_id,
                change_type,
                self._loggable(path),
                now - last_seen,
                DEBOUNCE_SECONDS,
            )
            return

        # #15636: this runs on the watchdog Observer thread, which has no running
        # event loop, so ``asyncio.create_task`` raised RuntimeError on every
        # event and nothing was ever queued. The debounce stamp used to be
        # written before that failing call, which made the handler look alive;
        # it is now written only after the cross-thread hand-off succeeded.
        if self.watcher.dispatch_change(folder_id, path, change_type) is None:
            logger.warning(
                "Watch folder %s: DROPPED %s of %s -- the cross-thread hand-off to the service "
                "loop scheduled nothing, so this change will not be ingested (#15636). The "
                "debounce stamp is deliberately not written, so the next event for this file "
                "is retried rather than coalesced.",
                folder_id,
                change_type,
                self._loggable(path),
            )
            return

        self._last_event_time[file_path] = now
