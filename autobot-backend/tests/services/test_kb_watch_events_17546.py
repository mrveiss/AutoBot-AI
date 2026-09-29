# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/tests/services/test_kb_watch_events_17546.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The watch folder notices deletes and renames, and stops ignoring edits (#17546, #17547).

Two defects that were invisible for opposite reasons.

#17547: ``on_modified`` required the path to be in ``_last_event_time``, a dict written
only by ``_handle_change`` *after* a successful dispatch — which ``on_modified`` reached
only by passing that gate first. ``on_created`` was the only thing that could populate
it, so a file predating the process never got an entry and every edit to it was dropped
for ever. The gate looked like a sensible "only files we know about" guard and was
self-perpetuating.

#17546: there was no ``on_deleted`` and no ``on_moved``, and ``change_type`` reached
``_process_single_change`` only to appear in a log string — a declared vocabulary with no
consumer (#17693). The tests that matter here are the ones that fail if the handlers stop
dispatching or the processor stops branching, because a deleted file leaves no signal of
its own.
"""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import kb_folder_events
from services.kb_folder_events import KBFolderChangeHandler

CONFIG = SimpleNamespace(folder_id="f1", file_types=["txt", "md"], category="uploads", tags=[], collection="notes")


class _Watcher:
    """Records what the handler hands across the thread boundary."""

    def __init__(self, accept=True):
        self.dispatched = []
        self._accept = accept

    def dispatch_change(self, folder_id, path, change_type):
        self.dispatched.append((folder_id, str(path), change_type))
        # #15636: None means nothing was scheduled, and the handler must then not
        # record the event as handled.
        return object() if self._accept else None


def _event(path, is_dir=False, dest=None):
    ev = SimpleNamespace(src_path=str(path), is_directory=is_dir)
    if dest is not None:
        ev.dest_path = str(dest)
    return ev


def _handler(accept=True):
    watcher = _Watcher(accept=accept)
    return watcher, KBFolderChangeHandler(watcher, CONFIG)


# ---------------------------------------------------------------------------
# #17547 — the gate
# ---------------------------------------------------------------------------


def test_a_modification_to_a_file_never_seen_before_is_dispatched():
    """The regression. This is the whole defect: an established watch folder's files
    all predate the process, so under the old gate none of their edits ever dispatched,
    and no later event could change that because only ``on_created`` populated the dict.
    """
    watcher, handler = _handler()

    handler.on_modified(_event("/watched/pre-existing.txt"))

    assert watcher.dispatched == [("f1", "/watched/pre-existing.txt", "modified")]


def test_the_debounce_still_suppresses_a_rapid_second_edit():
    """The gate is gone; the thing it plausibly protected against is not.

    Asserted because removing a guard and removing the protection are different
    changes, and only one of them was intended.
    """
    watcher, handler = _handler()

    handler.on_modified(_event("/watched/a.txt"))
    handler.on_modified(_event("/watched/a.txt"))

    assert len(watcher.dispatched) == 1


def test_a_debounced_path_dispatches_again_once_the_window_passes(monkeypatch):
    monkeypatch.setattr(kb_folder_events, "DEBOUNCE_SECONDS", 0.0)
    watcher, handler = _handler()

    handler.on_modified(_event("/watched/a.txt"))
    time.sleep(0.01)
    handler.on_modified(_event("/watched/a.txt"))

    assert len(watcher.dispatched) == 2


def test_a_failed_handoff_is_not_recorded_as_handled():
    """#15636's rule, re-asserted because #17547 moved the code around it.

    ``dispatch_change`` returning None means nothing was scheduled. Stamping the
    debounce anyway would make the next edit look like a rapid repeat and drop it too.
    """
    watcher, handler = _handler(accept=False)

    handler.on_modified(_event("/watched/a.txt"))
    handler.on_modified(_event("/watched/a.txt"))

    assert len(watcher.dispatched) == 2, "a rejected hand-off must not debounce the retry"


# ---------------------------------------------------------------------------
# #17546 — deletes and renames
# ---------------------------------------------------------------------------


def test_a_deleted_file_is_dispatched_as_deleted():
    watcher, handler = _handler()

    handler.on_deleted(_event("/watched/gone.txt"))

    assert watcher.dispatched == [("f1", "/watched/gone.txt", "deleted")]


def test_a_rename_is_dispatched_as_a_delete_of_the_old_path_and_a_create_of_the_new():
    """A rename is those two operations to everything downstream, because the KB
    addresses a document by its ``file_path`` metadata."""
    watcher, handler = _handler()

    handler.on_moved(_event("/watched/old.txt", dest="/watched/new.txt"))

    assert watcher.dispatched == [
        ("f1", "/watched/old.txt", "deleted"),
        ("f1", "/watched/new.txt", "created"),
    ]


def test_a_rename_out_of_the_watched_types_still_deletes_the_old_document():
    """Renaming report.txt to report.bak must not leave the old document behind.

    The create half is correctly filtered — .bak is not a watched type — and the
    delete half must still land. A filter that dropped both would silently orphan
    the document.
    """
    watcher, handler = _handler()

    handler.on_moved(_event("/watched/report.txt", dest="/watched/report.bak"))

    assert watcher.dispatched == [("f1", "/watched/report.txt", "deleted")]


def test_directory_events_are_ignored_for_every_handler():
    watcher, handler = _handler()

    handler.on_created(_event("/watched/sub", is_dir=True))
    handler.on_modified(_event("/watched/sub", is_dir=True))
    handler.on_deleted(_event("/watched/sub", is_dir=True))
    handler.on_moved(_event("/watched/sub", is_dir=True, dest="/watched/sub2"))

    assert watcher.dispatched == []


def test_an_unsupported_extension_is_dropped_on_delete_too():
    """The extension filter applies to every change type, not only ingestion."""
    watcher, handler = _handler()

    handler.on_deleted(_event("/watched/notes.xyz"))

    assert watcher.dispatched == []


# ---------------------------------------------------------------------------
# #17546 — the removal helper, and the three outcomes an empty list cannot carry
# ---------------------------------------------------------------------------


class _KB:
    """Only the two methods the removal path uses, with the real return shapes."""

    def __init__(self, search_result, delete_raises=None):
        self._search = search_result
        self._delete_raises = delete_raises
        self.searched = []
        self.deleted = []

    async def search_by_metadata(self, field_name, value, operator="eq", limit=50):
        self.searched.append((field_name, value, limit))
        return self._search

    async def delete_fact(self, fact_id):
        if self._delete_raises:
            raise self._delete_raises
        self.deleted.append(fact_id)


@pytest.fixture
def remove(monkeypatch):
    from services import kb_watch_ingest

    def _run(kb):
        import knowledge

        monkeypatch.setattr(knowledge, "get_knowledge_base", lambda: _coro(kb), raising=False)
        return kb_watch_ingest.remove_watched_file

    async def _coro(value):
        return value

    return _run


@pytest.mark.asyncio
async def test_removing_a_file_deletes_every_document_recording_that_path(remove):
    kb = _KB({"status": "success", "fact_ids": ["a", "b"], "count": 2})
    result = await remove(kb)(Path("/watched/gone.txt"))

    assert result["status"] == "removed"
    assert result["removed"] == 2
    assert kb.deleted == ["a", "b"]
    assert kb.searched[0][0] == "file_path", "documents are addressed by the metadata the ingest records"


@pytest.mark.asyncio
async def test_a_clean_miss_reports_not_found_rather_than_success(remove):
    kb = _KB({"status": "success", "fact_ids": [], "count": 0})
    result = await remove(kb)(Path("/watched/never-ingested.txt"))

    assert result["status"] == "not_found"
    assert result["removed"] == 0


@pytest.mark.asyncio
async def test_a_failed_search_is_an_error_not_a_clean_miss(remove):
    """The one that matters most here.

    ``search_by_metadata`` returns ``fact_ids: []`` for BOTH a genuine miss and an
    internal failure, separating them only by ``status``. A caller reading the list
    would report "nothing to remove" for a lookup that never ran — a failed
    measurement wearing a real one's shape.
    """
    kb = _KB({"status": "error", "message": "Metadata operation failed", "fact_ids": []})
    result = await remove(kb)(Path("/watched/gone.txt"))

    assert result["status"] == "error"
    assert "Metadata operation failed" in result["message"]
    assert kb.deleted == []


@pytest.mark.asyncio
async def test_a_delete_that_raises_reports_error_and_says_how_far_it_got(remove):
    kb = _KB({"status": "success", "fact_ids": ["a"], "count": 1}, delete_raises=RuntimeError("redis down"))
    result = await remove(kb)(Path("/watched/gone.txt"))

    assert result["status"] == "error"
    assert "RuntimeError" in result["message"] and "redis down" in result["message"]
    assert result["removed"] == 0


# ---------------------------------------------------------------------------
# #17546 — the processor must BRANCH on change_type, not just receive it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_processor_routes_a_delete_to_removal_and_never_reads_the_file(monkeypatch):
    """Without this, every other test here passes while `_process_single_change`
    ingests as before — the handlers dispatch "deleted" and the processor logs it.

    That was the defect: `change_type` reached this method and appeared in one log
    string. It also has to run BEFORE the `file_path.exists()` guard, because a
    deleted file does not exist by definition and that guard would discard every
    delete with a warning that reads like a race.
    """
    from services.kb_folder_watcher import KBFolderWatcherService

    service = KBFolderWatcherService.__new__(KBFolderWatcherService)
    service._configs = {"f1": CONFIG}
    service._stats = {"f1": {"files_ingested": 0, "errors": 0}}

    removed = []

    async def _fake_remove(folder_id, file_path):
        removed.append((folder_id, str(file_path)))

    monkeypatch.setattr(service, "_remove_ingested_file", _fake_remove)

    await service._process_single_change("f1", Path("/watched/gone.txt"), "deleted")

    assert removed == [("f1", "/watched/gone.txt")], "a delete must reach the removal path"


@pytest.mark.asyncio
async def test_a_removal_that_cannot_find_the_document_is_recorded_not_swallowed(monkeypatch):
    """`search_by_metadata` scans a bounded prefix of fact keys, so "no document
    records this path" and "the document is past the scan" are the same empty list.
    The second is a document nothing can now remove, and it must not look like a
    file that was never ingested."""
    from services import kb_watch_ingest
    from services.kb_folder_watcher import KBFolderWatcherService

    service = KBFolderWatcherService.__new__(KBFolderWatcherService)
    service._stats = {"f1": {"files_ingested": 0, "errors": 0}}

    async def _not_found(file_path):
        return {"status": "not_found", "message": "searched the first 500 fact keys", "removed": 0}

    monkeypatch.setattr(kb_watch_ingest, "remove_watched_file", _not_found)

    await service._remove_ingested_file("f1", Path("/watched/gone.txt"))

    assert service._stats["f1"]["errors"] == 1
    assert "500" in service._stats["f1"]["last_error"]
