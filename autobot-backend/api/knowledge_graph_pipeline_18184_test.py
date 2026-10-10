# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""run_pipeline processes the document's text, never its id (#18184)."""

import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api import knowledge_graph_routes as routes
from api.schemas_knowledge import PipelineRunRequest

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
USER = {"user_id": "alice", "role": "user"}


def _kb(fact, allowed=True):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value=fact)
    kb.ownership_manager.check_access = AsyncMock(return_value=allowed)
    return kb


def _runner():
    runner = MagicMock()
    result = MagicMock(
        entities_count=1,
        relationships_count=0,
        events_count=0,
        summaries_count=0,
        chunks_count=1,
        stages_completed=["extract"],
        errors=[],
    )
    runner.run = AsyncMock(return_value=result)
    return runner


async def _call(kb, doc_id, user=USER):
    runner = _runner()
    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch("knowledge.pipeline.runner.PipelineRunner", return_value=runner),
    ):
        resp = await routes.run_pipeline(PipelineRunRequest(document_id=doc_id), MagicMock(), user)
    return resp, runner


@pytest.mark.asyncio
async def test_pipeline_receives_document_text_not_id():
    doc_id = str(uuid4())
    kb = _kb({"fact_id": doc_id, "content": "Alice met Bob in Riga.", "metadata": {"owner_id": "alice"}})
    resp, runner = await _call(kb, doc_id)
    input_data, context = runner.run.await_args.args
    assert input_data == "Alice met Bob in Riga."
    assert str(context.document_id) == doc_id
    assert context.metadata["document_id"] == doc_id
    assert resp.document_id == doc_id
    kb.get_fact.assert_called_once_with(doc_id)


@pytest.mark.asyncio
async def test_input_data_is_never_a_bare_uuid_string():
    doc_id = str(uuid4())
    kb = _kb({"fact_id": doc_id, "content": "some text", "metadata": {}})
    _, runner = await _call(kb, doc_id)
    assert not UUID_RE.match(runner.run.await_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("fact", [None, {"fact_id": "x", "content": "  ", "metadata": {}}])
async def test_missing_or_empty_document_is_404_and_pipeline_not_run(fact):
    runner = _runner()
    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=_kb(fact))),
        patch("knowledge.pipeline.runner.PipelineRunner", return_value=runner),
        pytest.raises(HTTPException) as exc,
    ):
        await routes.run_pipeline(PipelineRunRequest(document_id=str(uuid4())), MagicMock(), USER)
    assert exc.value.status_code == 404
    runner.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_caller_gets_403_and_pipeline_not_run():
    doc_id = str(uuid4())
    kb = _kb({"fact_id": doc_id, "content": "secret", "metadata": {"owner_id": "bob"}}, allowed=False)
    runner = _runner()
    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch("knowledge.pipeline.runner.PipelineRunner", return_value=runner),
        pytest.raises(HTTPException) as exc,
    ):
        await routes.run_pipeline(PipelineRunRequest(document_id=doc_id), MagicMock(), USER)
    assert exc.value.status_code == 403
    runner.run.assert_not_awaited()
    assert kb.ownership_manager.check_access.await_args.kwargs["user_id"] == "alice"


@pytest.mark.asyncio
async def test_non_uuid_document_id_is_422():
    with pytest.raises(HTTPException) as exc:
        await routes.run_pipeline(PipelineRunRequest(document_id="not-a-uuid"), MagicMock(), USER)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_real_runner_hands_the_chunk_text_extractor_the_stored_text():
    """AC3 through a real PipelineRunner: only the chunk_text extractor runs, and it is spied on."""
    from knowledge.pipeline.extractors.semantic_chunker import SemanticChunker

    doc_id = str(uuid4())
    text = "Alice met Bob in Riga."
    kb = _kb({"fact_id": doc_id, "content": text, "metadata": {"owner_id": "alice"}})
    only_chunking = {"name": "chunk-only", "extract": [{"task": "chunk_text", "params": {}}], "cognify": [], "load": []}
    seen = []
    original = SemanticChunker.process

    async def spy(self, input_data, context):
        seen.append(input_data)
        async for item in original(self, input_data, context):
            yield item

    with (
        patch.object(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(SemanticChunker, "process", spy),
    ):
        resp = await routes.run_pipeline(
            PipelineRunRequest(document_id=doc_id, config=only_chunking), MagicMock(), USER
        )
    assert len(seen) == 1
    assert isinstance(seen[0], str) and text in seen[0]
    assert seen[0] != doc_id and not UUID_RE.match(seen[0])
    assert resp.errors == []
    assert resp.chunks_count >= 1


@pytest.mark.asyncio
async def test_upper_case_document_id_resolves_the_same_fact_as_lower_case():
    doc_id = str(uuid4())
    kb = _kb({"fact_id": doc_id, "content": "Alice met Bob in Riga.", "metadata": {"owner_id": "alice"}})
    resp, runner = await _call(kb, doc_id.upper())
    kb.get_fact.assert_called_once_with(doc_id)  # the helper receives the canonical lower-case form
    assert resp.document_id == doc_id
    assert runner.run.await_args.args[1].metadata["document_id"] == doc_id
