# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/tests/services/test_kb_watch_error_reporting.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The watcher's error count is not its error report (#17531).

Every watch-folder failure landed in one `errors` counter and one `logger.error`
with no traceback. Two different defects lived behind that count -- an un-awaited
`get_knowledge_base()` (#13551) and a method the KnowledgeBase does not define
(#17022) -- and both raised AttributeError about the same attribute name. The
count read identically for months while not one file was ingested, and
`get_stats()` reported only a total, so the surface an operator looks at could
say "4231 errors" and nothing about what any of them were.
"""

import pytest

from services.kb_folder_watcher import KBFolderWatcherService

FOLDER = "f1"


@pytest.fixture
def service() -> KBFolderWatcherService:
    watcher = KBFolderWatcherService()
    watcher._stats[FOLDER] = {"files_ingested": 0, "last_change": None, "errors": 0, "last_error": None}
    return watcher


def test_a_recorded_error_keeps_what_failed_beside_the_count(service: KBFolderWatcherService) -> None:
    service._record_error(FOLDER, "AttributeError: 'KnowledgeBase' object has no attribute 'add_fact'")

    assert service._stats[FOLDER]["errors"] == 1
    assert "add_fact" in service._stats[FOLDER]["last_error"]


def test_a_rejected_write_and_a_raised_one_do_not_read_the_same(service: KBFolderWatcherService) -> None:
    """The distinction the single counter could not make."""
    service._record_error(FOLDER, "knowledge base rejected the write: error: content too large")
    rejected = service._stats[FOLDER]["last_error"]

    service._record_error(FOLDER, "AttributeError: 'coroutine' object has no attribute 'add_document'")
    raised = service._stats[FOLDER]["last_error"]

    assert rejected != raised
    assert service._stats[FOLDER]["errors"] == 2


def test_an_exception_detail_carries_its_type_and_its_message() -> None:
    """Either half alone is ambiguous.

    The type alone made the two historical failures identical -- both
    AttributeError. The message alone would not say whether anything was raised
    at all, since a rejected write raises nothing.
    """
    error = AttributeError("'KnowledgeBase' object has no attribute 'add_fact'")
    detail = f"{type(error).__name__}: {error}"

    assert detail.startswith("AttributeError: ")
    assert "'KnowledgeBase'" in detail


def test_the_stats_surface_names_the_cause_not_only_the_total(service: KBFolderWatcherService) -> None:
    service._record_error(FOLDER, "AttributeError: 'KnowledgeBase' object has no attribute 'add_fact'")

    stats = service.get_stats()

    assert stats["total_errors"] == 1
    assert "add_fact" in stats["last_errors"][FOLDER]


def test_a_folder_that_has_not_failed_is_absent_from_the_report(service: KBFolderWatcherService) -> None:
    """Distinguishing nothing-found from did-not-look: no row means no failure."""
    assert service.get_stats()["last_errors"] == {}


def test_recording_against_an_unknown_folder_is_a_no_op(service: KBFolderWatcherService) -> None:
    service._record_error("not-a-folder", "AttributeError: boom")

    assert service.get_stats()["total_errors"] == 0
