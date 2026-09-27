# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_kb_push.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the transcriber's Knowledge Base push (#17022).

``push_to_kb`` used to call ``DocIndexerService.add_documents(documents,
collection_id=...)``, a method that class has never had, and the test covering it
patched the factory that produced the indexer -- so an ``AsyncMock`` answered
``add_documents`` happily and the suite stayed green over code that could not
execute at all. The doubles here expose exactly the methods the real
``KnowledgeBase`` has, so a call to a name it does not define fails the test the
same way it fails in production.
"""

import inspect
import sys
import types
from unittest.mock import patch

import pytest

from transcriber.knowledge.kb_push import build_segment_documents, push_to_kb

SEGMENTS = [
    {"start": 0.0, "end": 1.5, "speaker_name": "Alice", "text": "Hello world", "notes": []},
    {"start": 1.5, "end": 3.0, "speaker_name": "Bob", "text": "Goodbye", "notes": []},
]


class StrictKnowledgeBase:
    """A double carrying only the KnowledgeBase methods this push may use.

    Every other attribute -- ``add_documents``, ``add_fact`` -- raises
    AttributeError, which is what the real object does and what the previous
    ``AsyncMock`` double concealed.
    """

    def __init__(self, statuses=None, collection_result=None):
        self._statuses = list(statuses or [])
        self._collection_result = collection_result
        self.documents = []
        self.collection_calls = []

    async def add_document(self, content, metadata=None, doc_id=None):
        self.documents.append({"content": content, "metadata": metadata})
        status = self._statuses.pop(0) if self._statuses else "success"
        if status not in ("success", "duplicate"):
            return {"status": status, "message": "rejected by the knowledge base"}
        return {"status": status, "fact_id": f"fact-{len(self.documents)}"}

    async def add_facts_to_collection(self, collection_id, fact_ids):
        self.collection_calls.append((collection_id, list(fact_ids)))
        if self._collection_result is not None:
            return self._collection_result
        return {
            "success": True,
            "added_count": len(fact_ids),
            "already_in_collection": 0,
            "not_found": [],
        }


def _async_factory(kb):
    """An async factory, shaped like the real ``get_knowledge_base``.

    It has to be a coroutine function or the suite cannot tell whether the caller
    awaited it -- a sync double answers attribute lookups either way, which is how
    a missing ``await`` survived in the watch folder for months (#13551).
    """

    async def get_knowledge_base():
        return kb

    return get_knowledge_base


def _knowledge_stub(kb):
    """A stand-in ``knowledge`` module carrying only the factory.

    Standing the module in rather than patching an attribute on the real one keeps
    the heavy KnowledgeBase dependency chain (redis, chromadb, llama_index, reached
    through ``knowledge/_composed.py``) out of a transcriber unit test.
    """
    stub = types.ModuleType("knowledge")
    stub.get_knowledge_base = _async_factory(kb)
    return stub


async def _push(kb, collection_id="col-1", segments=None):
    stub = _knowledge_stub(kb)
    assert inspect.iscoroutinefunction(stub.get_knowledge_base), "a sync factory cannot detect a dropped await"
    with patch.dict(sys.modules, {"knowledge": stub}):
        return await push_to_kb(
            recording_id=7,
            recording_filename="meeting.wav",
            segments=SEGMENTS if segments is None else segments,
            collection_id=collection_id,
            pushed_by="u1",
        )


def test_each_segment_becomes_one_document_attributable_to_its_recording():
    documents = build_segment_documents(7, "meeting.wav", SEGMENTS, "u1")

    assert len(documents) == 2
    assert documents[0]["content"] == "[Alice, 00:00:00] Hello world"
    # #17527: the stored segment has to say which recording it was spoken in.
    assert documents[0]["metadata"]["recording_id"] == 7
    assert documents[0]["metadata"]["source"] == "recording:7"
    assert documents[0]["metadata"]["source_type"] == "transcript"
    assert documents[0]["metadata"]["speaker"] == "Alice"
    assert documents[0]["metadata"]["pushed_by"] == "u1"


def test_a_blank_segment_is_not_stored():
    segments = SEGMENTS + [{"start": 3.0, "end": 3.1, "speaker_name": "Alice", "text": "   ", "notes": []}]

    assert len(build_segment_documents(7, "meeting.wav", segments, "u1")) == 2


@pytest.mark.asyncio
async def test_the_factory_is_awaited_so_a_dropped_await_cannot_pass():
    """What the caller would be holding if the ``await`` were ever dropped."""
    factory = _async_factory(StrictKnowledgeBase())
    coroutine = factory()
    try:
        with pytest.raises(AttributeError):
            coroutine.add_document
    finally:
        coroutine.close()


@pytest.mark.asyncio
async def test_push_stores_every_segment_through_add_document():
    kb = StrictKnowledgeBase()

    result = await _push(kb)

    assert [document["content"] for document in kb.documents] == [
        "[Alice, 00:00:00] Hello world",
        "[Bob, 00:00:01] Goodbye",
    ]
    assert result["indexed"] == 2
    assert result["failed"] == 0
    assert result["segments"] == 2
    assert result["fact_ids"] == ["fact-1", "fact-2"]


@pytest.mark.asyncio
async def test_the_stored_facts_are_joined_to_the_requested_collection():
    kb = StrictKnowledgeBase()

    result = await _push(kb)

    # add_document takes no collection parameter, so the collection the caller
    # asked for is only honoured by this second call.
    assert kb.collection_calls == [("col-1", ["fact-1", "fact-2"])]
    assert result["collection"] == {"added": 2, "already_present": 0, "missing": 0}


@pytest.mark.asyncio
async def test_a_rejected_segment_counts_as_failed_not_indexed():
    kb = StrictKnowledgeBase(statuses=["success", "error"])

    result = await _push(kb)

    assert (result["indexed"], result["duplicate"], result["failed"]) == (1, 0, 1)
    assert result["fact_ids"] == ["fact-1"]
    assert kb.collection_calls == [("col-1", ["fact-1"])]


@pytest.mark.asyncio
async def test_a_duplicate_segment_still_reaches_the_collection():
    """Re-pushing a recording must not route fewer segments than the first push did."""
    kb = StrictKnowledgeBase(statuses=["duplicate", "success"])

    result = await _push(kb)

    assert (result["indexed"], result["duplicate"], result["failed"]) == (1, 1, 0)
    assert kb.collection_calls == [("col-1", ["fact-1", "fact-2"])]


@pytest.mark.asyncio
async def test_a_collection_that_does_not_exist_is_reported_not_swallowed():
    kb = StrictKnowledgeBase(collection_result={"success": False, "message": "Collection not found: default"})

    result = await _push(kb, collection_id="default")

    # The segments are in the Knowledge Base and retrievable; the collection is not.
    assert result["indexed"] == 2
    assert result["collection"] == {"added": 0, "already_present": 0, "missing": 2}


@pytest.mark.asyncio
async def test_no_collection_means_no_second_call():
    kb = StrictKnowledgeBase()

    result = await _push(kb, collection_id="")

    assert kb.collection_calls == []
    assert result["indexed"] == 2
    assert result["collection"] == {"added": 0, "already_present": 0, "missing": 0}


def test_the_knowledge_base_really_defines_the_methods_this_module_calls():
    """The check none of the previous tests could make, being mocked at the seam."""
    import knowledge.documents as documents_module
    from knowledge.collections import CollectionsMixin
    from knowledge.documents import DocumentsMixin

    assert callable(DocumentsMixin.add_document)
    assert callable(CollectionsMixin.add_facts_to_collection)
    # The three names the dead push path used, at the homes it looked for them in.
    assert not hasattr(documents_module, "DocIndexerService")
    assert not hasattr(DocumentsMixin, "add_documents")
    assert not hasattr(DocumentsMixin, "add_fact")


def test_the_write_path_still_runs_through_the_redaction_chokepoint():
    """#17022 asked for this to be confirmed at fix time; #16770 owns the chokepoint.

    Every other Knowledge Base write reaches ``sanitize_fact_content``. A transcript
    carries whatever was spoken, credentials included, so the push must not reach a
    persistence sink by some route that skips it.
    """
    from knowledge.documents import DocumentsMixin
    from knowledge.facts import FactsMixin

    assert "self.store_fact(" in inspect.getsource(DocumentsMixin._add_document_internal)
    assert "sanitize_fact_content(" in inspect.getsource(FactsMixin.store_fact)
