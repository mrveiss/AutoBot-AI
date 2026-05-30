# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KB Folder Watcher Service — auto-ingest new files from monitored directories.

GH#9000 / MVA-1813: Watches configured local directories and auto-ingests
new or modified files into the knowledge base via the standard KB pipeline.

Config (env vars):
    AUTOBOT_KB_WATCH_PATHS      — comma-separated list of absolute paths to watch
    AUTOBOT_KB_WATCH_DEBOUNCE   — debounce seconds before ingest (default: 5)
    AUTOBOT_KB_WATCH_EXTENSIONS — comma-separated extensions to watch (default: .txt,.md,.pdf,.docx,.json,.csv,.html)
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)

# --- Config resolved from env vars with logged-fallback defaults (Issue #6743 pattern) ---
_raw_watch_paths = os.environ.get("AUTOBOT_KB_WATCH_PATHS", "")
_WATCH_PATHS: List[str] = [p.strip() for p in _raw_watch_paths.split(",") if p.strip()] if _raw_watch_paths else []

_raw_debounce = os.environ.get("AUTOBOT_KB_WATCH_DEBOUNCE", "")
try:
    _DEBOUNCE_SECONDS: float = float(_raw_debounce) if _raw_debounce else 5.0
except ValueError:
    logger.warning("Invalid AUTOBOT_KB_WATCH_DEBOUNCE=%r — using default 5.0s", _raw_debounce)
    _DEBOUNCE_SECONDS = 5.0

_raw_extensions = os.environ.get("AUTOBOT_KB_WATCH_EXTENSIONS", "")
_DEFAULT_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".json", ".csv", ".html"}
_WATCH_EXTENSIONS: Set[str] = (
    {e.strip().lower() for e in _raw_extensions.split(",") if e.strip()}
    if _raw_extensions
    else _DEFAULT_EXTENSIONS
)

logger.debug(
    "KB folder watcher config: paths=%r debounce=%.1fs extensions=%r",
    _WATCH_PATHS,
    _DEBOUNCE_SECONDS,
    _WATCH_EXTENSIONS,
)

# Batch window: collect events within this window before processing
_BATCH_WINDOW_SECONDS = 2.0


class _KBFolderChangeHandler(FileSystemEventHandler):
    """Watchdog event handler for KB folder watcher."""

    def __init__(self, watcher: "KBFolderWatcherService") -> None:
        self._watcher = watcher
        self._last_event_time: Dict[str, float] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def _handle(self, file_path: str, change_type: str) -> None:
        path = Path(file_path)
        if path.suffix.lower() not in self._watcher.extensions:
            return

        now = time.time()
        last = self._last_event_time.get(file_path, 0.0)
        if now - last < self._watcher.debounce_seconds:
            return
        self._last_event_time[file_path] = now

        try:
            asyncio.get_event_loop().create_task(self._watcher.queue_file(path, change_type))
        except RuntimeError:
            # No running event loop in watchdog thread — schedule via run_coroutine_threadsafe
            loop = self._watcher._loop
            if loop is not None:
                asyncio.run_coroutine_threadsafe(self._watcher.queue_file(path, change_type), loop)


class KBFolderWatcherService:
    """
    Monitors one or more directories and auto-ingests new/modified files into the KB.

    GH#9000: Runtime-configurable watch paths; uses the same debounce + batch
    window pattern as DocumentationWatcherService.
    """

    def __init__(self) -> None:
        self._observer: Optional[Observer] = None
        self._handlers: Dict[str, _KBFolderChangeHandler] = {}
        self._is_running = False
        self._watch_paths: List[str] = list(_WATCH_PATHS)
        self._debounce_seconds: float = _DEBOUNCE_SECONDS
        self._extensions: Set[str] = set(_WATCH_EXTENSIONS)

        self._pending: Dict[str, str] = {}  # file_path -> change_type
        self._pending_lock = asyncio.Lock()
        self._processing_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._stats: Dict[str, Any] = {
            "files_ingested": 0,
            "errors": 0,
            "last_ingest": None,
            "skipped": 0,
        }

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def debounce_seconds(self) -> float:
        return self._debounce_seconds

    @property
    def extensions(self) -> Set[str]:
        return self._extensions

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Start the watcher. Returns True on success."""
        if self._is_running:
            return True

        try:
            self._loop = asyncio.get_event_loop()
            self._observer = Observer()
            self._handlers = {}

            valid_paths = []
            for raw_path in self._watch_paths:
                p = Path(raw_path).resolve()
                if not p.exists():
                    logger.warning("KB watch path does not exist, skipping: %s", p)
                    continue
                if not p.is_dir():
                    logger.warning("KB watch path is not a directory, skipping: %s", p)
                    continue
                handler = _KBFolderChangeHandler(self)
                self._observer.schedule(handler, str(p), recursive=True)
                self._handlers[str(p)] = handler
                valid_paths.append(str(p))

            if not valid_paths:
                logger.info("KB folder watcher: no valid watch paths configured — not starting")
                return False

            self._observer.start()
            self._is_running = True
            logger.info("KB folder watcher started — monitoring: %s", valid_paths)
            return True

        except Exception as exc:
            logger.error("Failed to start KB folder watcher: %s", exc)
            self._stats["errors"] += 1
            return False

    async def stop(self) -> None:
        """Stop the watcher."""
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

            self._handlers = {}
            self._is_running = False
            logger.info("KB folder watcher stopped")
        except Exception as exc:
            logger.error("Error stopping KB folder watcher: %s", exc)

    # ------------------------------------------------------------------
    # Path management (runtime add/remove)
    # ------------------------------------------------------------------

    def add_watch_path(self, path: str) -> bool:
        """
        Add a directory to the watch list.

        If the watcher is running, schedules the new path immediately.
        Returns True if the path was added (False if already watched or invalid).
        """
        resolved = str(Path(path).resolve())
        if resolved in self._watch_paths:
            logger.debug("KB folder watcher: path already watched: %s", resolved)
            return False

        p = Path(resolved)
        if not p.exists() or not p.is_dir():
            logger.warning("KB folder watcher: invalid path (not an existing directory): %s", resolved)
            return False

        self._watch_paths.append(resolved)

        if self._is_running and self._observer:
            handler = _KBFolderChangeHandler(self)
            self._observer.schedule(handler, resolved, recursive=True)
            self._handlers[resolved] = handler
            logger.info("KB folder watcher: added path at runtime: %s", resolved)

        return True

    def remove_watch_path(self, path: str) -> bool:
        """
        Remove a directory from the watch list.

        Returns True if the path was found and removed.
        """
        resolved = str(Path(path).resolve())
        if resolved not in self._watch_paths:
            return False

        self._watch_paths.remove(resolved)

        if self._is_running and self._observer and resolved in self._handlers:
            try:
                self._observer.unschedule(self._handlers.pop(resolved))
            except Exception as exc:
                logger.warning("Error unscheduling KB watch path %s: %s", resolved, exc)

        logger.info("KB folder watcher: removed path: %s", resolved)
        return True

    # ------------------------------------------------------------------
    # Ingest queue
    # ------------------------------------------------------------------

    async def queue_file(self, file_path: Path, change_type: str) -> None:
        """Queue a file change for deferred processing."""
        async with self._pending_lock:
            self._pending[str(file_path)] = change_type

        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._process_batch())

    async def _process_batch(self) -> None:
        """Wait for the batch window, then ingest all queued files."""
        await asyncio.sleep(_BATCH_WINDOW_SECONDS)

        async with self._pending_lock:
            if not self._pending:
                return
            batch = dict(self._pending)
            self._pending.clear()

        for file_path_str, change_type in batch.items():
            await self._ingest_file(Path(file_path_str), change_type)

    async def _ingest_file(self, file_path: Path, change_type: str) -> None:
        """Ingest a single file into the knowledge base."""
        try:
            if not file_path.exists():
                logger.debug("KB folder watcher: file no longer exists, skipping: %s", file_path)
                self._stats["skipped"] += 1
                return

            if file_path.stat().st_size == 0:
                logger.debug("KB folder watcher: empty file, skipping: %s", file_path)
                self._stats["skipped"] += 1
                return

            logger.info("KB folder watcher: ingesting %s (%s)", file_path.name, change_type)

            file_content = file_path.read_bytes()
            content = _extract_content(file_path.name, file_content)

            if not content.strip():
                logger.warning("KB folder watcher: no text content extracted from %s", file_path.name)
                self._stats["skipped"] += 1
                return

            from knowledge_factory import get_knowledge_base_async
            from knowledge.query_sanitizer import sanitize_document

            kb = await get_knowledge_base_async()
            if kb is None:
                logger.error("KB folder watcher: KB not available, cannot ingest %s", file_path.name)
                self._stats["errors"] += 1
                return

            sanitized = sanitize_document(content, source="folder_watch").sanitized_text

            metadata = {
                "title": file_path.stem,
                "source": str(file_path),
                "category": "folder_watch",
                "tags": ["auto-ingested"],
                "type": "file",
                "filename": file_path.name,
                "watch_source": "kb_folder_watcher",
            }

            if hasattr(kb, "store_fact"):
                result = await kb.store_fact(content=sanitized, metadata=metadata)
            else:
                result = await kb.store_fact(text=sanitized, metadata=metadata)

            fact_id = result.get("fact_id") if isinstance(result, dict) else str(result)
            logger.info(
                "KB folder watcher: ingested %s → fact_id=%s", file_path.name, fact_id
            )
            self._stats["files_ingested"] += 1
            self._stats["last_ingest"] = datetime.now(tz=timezone.utc).isoformat()

        except Exception as exc:
            logger.error("KB folder watcher: error ingesting %s: %s", file_path, exc)
            self._stats["errors"] += 1

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "is_running": self._is_running,
            "watch_paths": list(self._watch_paths),
            "extensions": sorted(self._extensions),
            "debounce_seconds": self._debounce_seconds,
            "pending_files": len(self._pending),
        }


# ------------------------------------------------------------------
# Content extraction (mirrors api/knowledge.py helpers, no HTTP deps)
# ------------------------------------------------------------------

def _extract_content(filename: str, file_content: bytes) -> str:
    """Extract plain text from a file based on extension."""
    ext = os.path.splitext(filename.lower())[1]

    if ext in {".txt", ".md", ".csv"}:
        return file_content.decode("utf-8", errors="replace")

    if ext == ".json":
        import json
        try:
            data = json.loads(file_content.decode("utf-8"))
            return json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            return file_content.decode("utf-8", errors="replace")

    if ext == ".html":
        from html.parser import HTMLParser

        class _Stripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: list = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag.lower() in {"script", "style"}:
                    self._skip = True

            def handle_endtag(self, tag):
                if tag.lower() in {"script", "style"}:
                    self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    self._parts.append(data)

        stripper = _Stripper()
        stripper.feed(file_content.decode("utf-8", errors="replace"))
        return " ".join(stripper._parts)

    if ext == ".pdf":
        try:
            import io
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return file_content.decode("utf-8", errors="replace")

    if ext == ".docx":
        try:
            import io
            import docx
            doc = docx.Document(io.BytesIO(file_content))
            return "\n".join(para.text for para in doc.paragraphs)
        except Exception:
            return file_content.decode("utf-8", errors="replace")

    return file_content.decode("utf-8", errors="replace")


# ------------------------------------------------------------------
# Module-level singleton + convenience functions
# ------------------------------------------------------------------

get_kb_folder_watcher = lazy_singleton(KBFolderWatcherService)
"""Singleton accessor for the KB folder watcher."""


async def start_kb_folder_watcher() -> bool:
    """Start the KB folder watcher service."""
    return await get_kb_folder_watcher().start()


async def stop_kb_folder_watcher() -> None:
    """Stop the KB folder watcher service."""
    await get_kb_folder_watcher().stop()
