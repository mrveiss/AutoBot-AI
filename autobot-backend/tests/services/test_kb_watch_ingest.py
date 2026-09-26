# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/tests/services/test_kb_watch_ingest.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Watch-folder ingest actually reaches the Knowledge Base (#17022, #13551).

``kb_folder_watcher`` called ``kb.add_fact(content=..., category=..., tags=...)``.
There is no ``add_fact`` on the KnowledgeBase, and ``category``/``tags`` are not
parameters of the method that does exist. #13551 removed a missing ``await`` in
front of ``get_knowledge_base()``, which changed ``AttributeError: 'coroutine'
object has no attribute 'add_fact'`` into ``AttributeError: 'KnowledgeBase' object
has no attribute 'add_fact'`` -- same exception, same attribute name, same error
counter -- so the fix was indistinguishable in the logs from the bug, and the
watcher had no test at all to tell the difference.
"""

import inspect
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.kb_watch_ingest import STORED_STATUSES, build_watch_metadata, ingest_stored, ingest_watched_file

CONFIG = SimpleNamespace(category="uploads", tags=["manual"], collection="notes")
FILE = Path("/watched/folder/report.txt")


class StrictKnowledgeBase:
    """A double with only the write method the KnowledgeBase really defines.

    ``add_fact`` and ``add_documents`` raise AttributeError here exactly as they do
    on the real object, so a call to either fails this test instead of passing.
    """

    def __init__(self, result=None):
        self.calls = []
        self._result = result or {"status": "success", "fact_id": "fact-1"}

    async def add_document(self, content, metadata=None, doc_id=None):
        self.calls.append({"content": content, "metadata": metadata, "doc_id": doc_id})
        return self._result


def _knowledge_stub(kb):
    """A stand-in ``knowledge`` module, so the ingest is tested without chromadb."""

    async def get_knowledge_base():
        return kb

    stub = types.ModuleType("knowledge")
    stub.get_knowledge_base = get_knowledge_base
    return stub


def test_category_and_tags_travel_inside_the_metadata():
    """They are metadata keys, not parameters: add_document takes neither."""
    metadata = build_watch_metadata("f1", CONFIG, FILE)

    assert metadata["category"] == "uploads"
    assert metadata["tags"] == ["manual", "watch_folder:f1"]
    assert metadata["source"] == "watch_folder"
    assert metadata["filename"] == "report.txt"
    assert metadata["collection"] == "notes"


def test_the_folder_tag_does_not_mutate_the_configured_tags():
    build_watch_metadata("f1", CONFIG, FILE)

    assert CONFIG.tags == ["manual"]


@pytest.mark.asyncio
async def test_the_ingest_calls_add_document_on_an_awaited_knowledge_base():
    kb = StrictKnowledgeBase()
    stub = _knowledge_stub(kb)
    # A sync factory could not tell whether the caller awaited it, which is the
    # property #13551 was about.
    assert inspect.iscoroutinefunction(stub.get_knowledge_base)

    with patch.dict(sys.modules, {"knowledge": stub}):
        result = await ingest_watched_file("f1", CONFIG, FILE, "the report body")

    assert result == {"status": "success", "fact_id": "fact-1"}
    assert kb.calls[0]["content"] == "the report body"
    assert kb.calls[0]["metadata"]["folder_id"] == "f1"


@pytest.mark.asyncio
async def test_a_dropped_await_leaves_a_coroutine_with_no_write_method():
    """What every watch-folder ingest was holding before #13551, and why it failed."""
    stub = _knowledge_stub(StrictKnowledgeBase())
    coroutine = stub.get_knowledge_base()
    try:
        with pytest.raises(AttributeError):
            coroutine.add_document
    finally:
        coroutine.close()


@pytest.mark.parametrize("status", STORED_STATUSES)
def test_a_stored_result_counts_as_ingested(status):
    assert ingest_stored({"status": status, "fact_id": "fact-1"}) is True


@pytest.mark.parametrize("result", [{"status": "error", "message": "no"}, {"status": "timeout"}, {}])
def test_a_rejected_result_is_not_an_ingest(result):
    """add_document reports rejection in its return value, so the counter must read it."""
    assert ingest_stored(result) is False


def test_the_knowledge_base_defines_add_document_and_not_add_fact():
    """The contract check that no mock can satisfy on the module's behalf."""
    from knowledge.documents import DocumentsMixin
    from knowledge.facts import FactsMixin

    assert callable(DocumentsMixin.add_document)
    # The name the watcher called for months, on the mixin that would own it.
    assert not hasattr(FactsMixin, "add_fact")
    assert not hasattr(DocumentsMixin, "add_fact")
    assert callable(FactsMixin.store_fact)
