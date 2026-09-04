# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15636: watchdog callbacks run on the Observer thread, which has no loop.

Three ``FileSystemEventHandler`` implementations used to call
``asyncio.create_task`` straight out of their callbacks. A watchdog ``Observer``
dispatches those callbacks on its own background thread, where there is no
running event loop, so the call raised ``RuntimeError`` on EVERY file event and
the work was never scheduled at all — documentation changes, knowledge-base
folder changes and hot reloads all silently did nothing.

The tests below raise the events from a real non-loop thread, because that is
the only place the bug exists. A test that asserted ``create_task`` had been
called would have passed against the broken code: the call was made, it just
raised. What has to be proven is that the coroutine RAN.

Each handler also recorded its debounce timestamp BEFORE the failing call, so
the handler looked alive while doing nothing and the next event inside the
debounce window was discarded as a duplicate. ``test_a_failed_dispatch_...``
pins the corrected order.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, List

import pytest

from services.documentation_watcher import DocumentationChangeHandler, DocumentationWatcherService
from services.kb_folder_watcher import KBFolderChangeHandler, KBFolderWatcherService, WatchFolderConfig
from utils.hot_reload_manager import HotReloadManager, ModuleReloadHandler


class _Event:
    """The two attributes every handler under test reads off a watchdog event."""

    def __init__(self, src_path: str) -> None:
        self.src_path = src_path
        self.is_directory = False


def _raise_on_observer_thread(callback: Any, event: _Event) -> List[BaseException]:
    """Run *callback* on a thread that is NOT running the event loop.

    Returns whatever the thread raised. The old code raised ``RuntimeError: no
    running event loop`` here, which is why the failure was invisible: watchdog
    logs the callback's exception and carries on.
    """
    raised: List[BaseException] = []

    def worker() -> None:
        try:
            callback(event)
        except BaseException as exc:  # noqa: BLE001 - the thread's raise is the finding
            raised.append(exc)

    thread = threading.Thread(target=worker, name="fake-watchdog-observer")
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "the observer thread never returned"
    return raised


async def _drain(predicate: Any, timeout: float = 2.0) -> bool:
    """Give the loop a chance to run whatever the other thread handed it."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
        if predicate():
            return True
    return False


class TestDocumentationWatcher:
    async def test_an_event_raised_off_the_loop_thread_reaches_the_queue(self) -> None:
        service = DocumentationWatcherService()
        service._loop = asyncio.get_running_loop()
        # queue_change kicks off the real batch indexer; the queue is the seam
        # under test, so the batch pass is replaced with a no-op.
        service._process_pending_changes = _noop_batch_pass  # type: ignore[method-assign]
        handler = DocumentationChangeHandler(service)

        raised = _raise_on_observer_thread(handler.on_modified, _Event("/docs/guide.md"))
        assert raised == [], f"the observer thread raised instead of scheduling: {raised!r}"

        assert await _drain(lambda: bool(service._pending_changes)), (
            "the file change never reached the queue — the coroutine was not scheduled from "
            "the observer thread"
        )
        assert service._pending_changes == {Path("/docs/guide.md"): "modified"}

    async def test_a_failed_dispatch_does_not_stamp_the_debounce_record(self) -> None:
        """A dropped event must not be suppressed as a duplicate next time."""
        service = DocumentationWatcherService()
        service._loop = None  # start() never ran, so there is no loop to hand off to
        handler = DocumentationChangeHandler(service)

        _raise_on_observer_thread(handler.on_modified, _Event("/docs/guide.md"))

        assert handler._last_event_time == {}, (
            "the debounce timestamp was recorded for an event that was never scheduled — the "
            "next event for this file would be discarded as a duplicate"
        )
        assert service._pending_changes == {}


class TestKBFolderWatcher:
    async def test_an_event_raised_off_the_loop_thread_reaches_the_queue(self) -> None:
        service = KBFolderWatcherService()
        service._loop = asyncio.get_running_loop()
        service._process_pending_changes = _noop_batch_pass  # type: ignore[method-assign]
        config = WatchFolderConfig(folder_id="f1", path="/kb", collection="docs")
        handler = KBFolderChangeHandler(service, config)

        raised = _raise_on_observer_thread(handler.on_created, _Event("/kb/report.md"))
        assert raised == [], f"the observer thread raised instead of scheduling: {raised!r}"

        assert await _drain(lambda: bool(service._pending_changes)), (
            "the file change never reached the queue — the coroutine was not scheduled from "
            "the observer thread"
        )
        assert service._pending_changes["f1"] == [(Path("/kb/report.md"), "created")]

    async def test_a_failed_dispatch_does_not_stamp_the_debounce_record(self) -> None:
        service = KBFolderWatcherService()
        service._loop = None
        config = WatchFolderConfig(folder_id="f1", path="/kb", collection="docs")
        handler = KBFolderChangeHandler(service, config)

        _raise_on_observer_thread(handler.on_created, _Event("/kb/report.md"))

        assert handler._last_event_time == {}, (
            "the debounce timestamp was recorded for an event that was never scheduled"
        )
        assert service._pending_changes == {}


class TestHotReloadManager:
    async def test_an_event_raised_off_the_loop_thread_reaches_the_handler(self) -> None:
        manager = HotReloadManager()
        manager._loop = asyncio.get_running_loop()
        seen: List[Path] = []

        async def record(file_path: Path) -> None:
            seen.append(file_path)

        manager._handle_file_change = record  # type: ignore[method-assign]
        handler = ModuleReloadHandler(manager)

        raised = _raise_on_observer_thread(handler.on_modified, _Event("/backend/api/agent.py"))
        assert raised == [], f"the observer thread raised instead of scheduling: {raised!r}"

        assert await _drain(lambda: bool(seen)), (
            "the .py modification never reached the reload path — the hot-reload coroutine was "
            "not scheduled from the observer thread"
        )
        assert seen == [Path("/backend/api/agent.py")]

    async def test_a_failed_dispatch_does_not_stamp_the_debounce_record(self) -> None:
        manager = HotReloadManager()
        manager._loop = None
        handler = ModuleReloadHandler(manager)

        _raise_on_observer_thread(handler.on_modified, _Event("/backend/api/agent.py"))

        assert handler.last_reload_time == {}, (
            "the debounce timestamp was recorded for an event that was never scheduled"
        )


async def _noop_batch_pass(*_args: Any, **_kwargs: Any) -> None:
    """Stand-in for the batch pass each watcher starts after queueing."""
    await asyncio.sleep(0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
