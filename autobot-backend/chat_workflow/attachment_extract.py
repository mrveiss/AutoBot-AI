# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where attachment text is extracted, and how often (#20195).

* ``extract_executor`` is a dedicated, BOUNDED pool. A thread cannot be killed, so one that outlives the turn's
  deadline keeps its slot until it really finishes (the slot is released by the future's done-callback, not by
  the turn giving up). With every slot taken, ``submit`` refuses (``ExtractorBusy``) instead of queueing, so
  abandoned extractions cannot pile up in the shared default executor.
* The extracted text is kept for a short time in THIS process (never in the graph checkpoint), so the LLM
  iterations of one turn read a file once. The key carries the file's size and mtime; the caller still looks
  the file up (session-scoped) on every use, so a deleted file or a changed verdict is never served from here.

Only ids, sizes and counts are ever logged; never file text.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from chat_workflow import limits


class ExtractorBusy(RuntimeError):
    """Every extraction slot is taken (some by threads past their deadline); the file is refused, not queued."""


class BoundedExecutor(ThreadPoolExecutor):
    """A thread pool whose ``submit`` refuses when all *workers* slots are in use."""

    def __init__(self, workers: int):
        super().__init__(max_workers=workers, thread_name_prefix="attachment-extract")
        self._slots = threading.BoundedSemaphore(workers)

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
        if not self._slots.acquire(blocking=False):
            raise ExtractorBusy("no free attachment extraction slot")
        try:
            future = super().submit(fn, *args, **kwargs)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _f: self._slots.release())  # when the THREAD ends, not when the turn gave up
        return future


_executor: BoundedExecutor | None = None
_executor_lock = threading.Lock()


def extract_executor() -> BoundedExecutor:
    """The process-wide extraction pool, created on first use with ``limits.ATTACHMENT_EXTRACT_WORKERS`` slots."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = BoundedExecutor(max(1, limits.ATTACHMENT_EXTRACT_WORKERS))
        return _executor


_cache: "OrderedDict[tuple, tuple[float, str]]" = OrderedDict()
_cache_lock = threading.Lock()


def cache_key(session_id: str, file_id: str, path: Path) -> tuple | None:
    """Identity of this file's bytes for the cache, or None when it cannot be stat-ed. Blocking: use a thread."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (session_id, file_id, str(path), stat.st_size, stat.st_mtime_ns)


def cached_text(key: tuple | None) -> str | None:
    """The text remembered for *key* if it is still fresh, else None."""
    if key is None:
        return None
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if entry[0] < time.monotonic():
            del _cache[key]
            return None
        return entry[1]


def remember_text(key: tuple | None, text: str) -> None:
    """Keep *text* (cut to what the prompt could ever use, plus one char so a cut is still detected)."""
    if key is None:
        return
    kept = text[: limits.ATTACHMENT_MAX_CHARS_PER_FILE + 1]
    with _cache_lock:
        _cache[key] = (time.monotonic() + limits.ATTACHMENT_TEXT_CACHE_SECONDS, kept)
        _cache.move_to_end(key)
        while len(_cache) > max(1, limits.ATTACHMENT_TEXT_CACHE_MAX_ENTRIES):
            _cache.popitem(last=False)


def cached_skip(key: tuple | None) -> str | None:
    """The notice code remembered for a file whose extraction failed (timeout, unreadable, binary), if fresh."""
    return None if key is None else cached_text((*key, "skip"))


def remember_skip(key: tuple | None, code: str) -> None:
    """Keep the failure *code* for *key* for as long as a text would be kept, so a bad file is read once."""
    if key is not None:
        remember_text((*key, "skip"), code)


def clear_text_cache() -> None:
    """Forget every remembered text (tests, and a deliberate flush)."""
    with _cache_lock:
        _cache.clear()
