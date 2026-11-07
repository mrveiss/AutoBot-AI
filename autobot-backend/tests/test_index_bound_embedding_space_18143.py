# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Index-bound pipelines embed in their index's recorded space; fresh ones follow the active model (#18143)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.npu_client as npu_client_module
from autobot_shared.embedding_model import EmbeddingUnavailableError
from knowledge.index_embedding_space import PATTERN_INDEXES, index_embedding_space

ACTIVE = "some-other-model:latest"


@pytest.fixture
def active_changed():
    with patch("autobot_shared.embedding_model.active_embedding_model", return_value=ACTIVE):
        yield


@pytest.mark.parametrize("index", PATTERN_INDEXES)
def test_every_pattern_index_has_a_recorded_space(index: str) -> None:
    space = index_embedding_space(index)
    assert (space.model_id, space.dim, space.space_id) == ("nomic-embed-text", 768, "nomic-embed-text/768")


def test_an_unrecorded_collection_is_refused() -> None:
    with pytest.raises(EmbeddingUnavailableError):
        index_embedding_space("bug_pattern_vectors_test")


async def test_the_analytics_mixin_keys_and_generates_in_the_collection_space(active_changed) -> None:
    from code_intelligence.analytics_infrastructure import AnalyticsInfrastructureMixin

    class Probe(AnalyticsInfrastructureMixin):
        pass

    probe = Probe()
    probe._init_infrastructure(collection_name="security_analysis_vectors")
    cache = MagicMock(get=AsyncMock(return_value=None), put=AsyncMock())
    probe._get_embedding_cache = AsyncMock(return_value=cache)
    with patch.object(npu_client_module, "generate_embedding_with_fallback", new=AsyncMock(return_value=[0.1])) as gen:
        await probe._get_embedding("code")

    gen.assert_awaited_once_with("code", model_name="nomic-embed-text")
    cache.get.assert_awaited_once_with("code", model="nomic-embed-text/768")
    cache.put.assert_awaited_once_with("code", [0.1], model="nomic-embed-text/768")


async def test_the_analytics_mixin_refuses_a_collection_with_no_recorded_space() -> None:
    from code_intelligence.analytics_infrastructure import AnalyticsInfrastructureMixin

    class Probe(AnalyticsInfrastructureMixin):
        pass

    probe = Probe()
    probe._init_infrastructure(collection_name="unrecorded_vectors")
    probe._get_embedding_cache = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=None)))
    with pytest.raises(EmbeddingUnavailableError):
        await probe._get_embedding("code")


def test_fresh_embedders_follow_the_active_model(active_changed) -> None:
    from autobot_memory_graph.core import config as graph_config
    from autobot_shared.embedding_model import active_npu_worker_model

    assert active_npu_worker_model() == "some-other-model"  # the worker form drops the tag
    assert graph_config.embedding_model == ACTIVE


def _searcher(metadata):
    from services.knowledge.doc_searcher import DocumentationSearcher

    searcher = DocumentationSearcher()
    searcher._collection = MagicMock(metadata=metadata)
    return searcher


def test_the_doc_searcher_takes_the_space_the_collection_records(active_changed) -> None:
    from autobot_shared.embedding_provenance import EmbeddingProvenance, provenance_to_metadata

    space = _searcher(provenance_to_metadata(EmbeddingProvenance("mxbai-embed-large", 1024)))._recorded_space()
    assert (space.model_name, space.dim) == ("mxbai-embed-large", 1024)


def _unrecorded(stored_dim: int | None, probe_dim: int):
    """A searcher whose collection records no space, stores ``stored_dim``-d vectors, active model gives probe_dim."""
    import sys
    import types

    from services.knowledge import doc_searcher

    searcher = _searcher({"hnsw:space": "cosine"})
    embs = None if stored_dim is None else [[0.0] * stored_dim]
    searcher._collection.peek.return_value = {"embeddings": embs}
    fake = types.ModuleType("llama_index.embeddings.ollama")
    fake.OllamaEmbedding = lambda **kw: MagicMock(get_text_embedding=lambda t: [0.0] * probe_dim)
    doc_searcher._WARNED.clear()
    return searcher, patch.dict(sys.modules, {"llama_index.embeddings.ollama": fake})


def test_an_unrecorded_collection_with_a_matching_dimension_is_searched_warns_and_proposes(caplog) -> None:
    searcher, modules = _unrecorded(768, 768)
    with modules, patch("services.knowledge.collection_space_proposal.schedule_stamp_proposal") as propose:
        space = searcher._recorded_space()
        searcher._recorded_space()  # a second init in the same process does not warn or propose again
    assert space.dim == 768 and space.model_name
    propose.assert_called_once_with("autobot_docs", space.model_name, 768)
    assert caplog.text.count("unrecorded space, dimension-matched") == 1


def test_an_unrecorded_collection_with_a_different_dimension_or_empty_is_refused() -> None:
    for stored, probe in ((384, 768), (None, 768)):
        searcher, modules = _unrecorded(stored, probe)
        with modules, patch("services.knowledge.collection_space_proposal.schedule_stamp_proposal") as propose:
            assert searcher._recorded_space() is None
        propose.assert_not_called()


async def test_the_stamp_proposal_is_reused_when_one_is_pending_and_never_writes_the_collection() -> None:
    from services.knowledge import collection_space_proposal as csp

    existing = MagicMock(context={"collection": "autobot_docs"})
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [existing]))))
    factory = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock()))
    with (
        patch.object(csp, "get_async_session_factory", return_value=factory),
        patch.object(csp, "ApprovalGateService") as service,
    ):
        assert await csp.propose_stamp("autobot_docs", "m", 768) is True
    service.return_value.create_approval.assert_not_called()


def test_the_cognition_seeder_refuses_a_collection_recorded_in_another_space() -> None:
    from autobot_shared.embedding_provenance import EmbeddingMismatchError, EmbeddingProvenance, provenance_to_metadata
    from services.knowledge.cognition_seeder import CognitionSeeder

    seeder = CognitionSeeder()
    seeder._model_name, seeder._embed_dim = "new-model", 512
    old = provenance_to_metadata(EmbeddingProvenance("nomic-embed-text", 768))
    seeder._client = MagicMock()
    seeder._client.get_or_create_collection.return_value = MagicMock(metadata=old)
    with pytest.raises(EmbeddingMismatchError):
        seeder._get_or_create_collection("cognition_store")
    new = provenance_to_metadata(EmbeddingProvenance("new-model", 512))
    seeder._client.get_or_create_collection.return_value = MagicMock(metadata=new)
    assert seeder._get_or_create_collection("cognition_store") is not None
    assert seeder._client.get_or_create_collection.call_args.kwargs["metadata"]["hnsw:space"] == "cosine"


# -- the executor of the stamp proposal --------------------------------------------------------------


def _real_collection(tmp_path, dim: int, **meta):
    """An in-memory backend client (conftest stubs chromadb); ChromaDBCollection.modify_metadata was checked
    against a real PersistentClient separately."""
    from knowledge.backends.memory_adapter import InMemoryClient

    client = InMemoryClient()
    col = client.get_or_create_collection("autobot_docs", metadata={"hnsw:space": "cosine", "keep": "me", **meta})
    col.add(ids=["1"], embeddings=[[0.1] * dim])
    return client


def _approval(dim: int = 768):
    ctx = {"action": "stamp_collection_embedding_space", "collection": "autobot_docs", "model": "m", "dim": dim}
    return MagicMock(id="a1", context=ctx, decided_by_user="owner")


async def _run(tmp_path, client, approval):
    from services.knowledge import collection_space_stamp_action as act

    session = MagicMock(commit=AsyncMock())
    with (
        patch.object(act, "_open_collection", lambda name: client.get_collection(name)),
        patch.object(act, "audit_log", new=AsyncMock()) as audit,
    ):
        await act.execute_stamp(approval, session)
    return session, audit


async def test_an_approved_stamp_records_the_space_keeps_existing_metadata_and_the_searcher_then_uses_it(
    tmp_path,
) -> None:
    client = _real_collection(tmp_path, 768)
    session, audit = await _run(tmp_path, client, _approval(768))

    meta = client.get_collection("autobot_docs").metadata
    assert meta["keep"] == "me"
    assert "hnsw:space" not in meta  # as on real ChromaDB: a modify cannot carry it ...
    from knowledge.backends.hnsw_params import hnsw_params

    assert (
        hnsw_params(client.get_collection("autobot_docs"))["space"] == "cosine"
    )  # ... and the space is still reported  # merged, not replaced
    searcher = _searcher(meta)
    space = searcher._recorded_space()  # the recorded path: no probe, no warning
    assert (space.model_name, space.dim) == ("m", 768)
    assert "Recorded embedding space" in session.add.call_args.args[0].body
    assert audit.call_args.kwargs["result"] == "success"


async def test_a_dimension_that_changed_since_the_proposal_is_refused_and_nothing_is_written(tmp_path) -> None:
    client = _real_collection(tmp_path, 384)
    before = dict(client.get_collection("autobot_docs").metadata)
    session, audit = await _run(tmp_path, client, _approval(768))

    assert dict(client.get_collection("autobot_docs").metadata) == before
    assert "REFUSED" in session.add.call_args.args[0].body
    assert audit.call_args.kwargs["result"] == "refused"


def test_the_stamp_action_is_registered_with_its_proposer() -> None:
    from services.approval_execution import is_registered_action, registered_action_proposers
    from services.knowledge.collection_space_stamp_action import ACTION, PROPOSED_BY, register_stamp_action

    register_stamp_action()
    assert is_registered_action(ACTION)
    assert registered_action_proposers()[ACTION] == PROPOSED_BY


def test_hnsw_params_reads_the_configuration_before_the_metadata() -> None:
    from knowledge.backends.hnsw_params import hnsw_params

    chroma_like = MagicMock(
        metadata={"keep": "me"},
        configuration={"hnsw": {"space": "cosine", "ef_construction": 200, "max_neighbors": 16}},
    )
    assert hnsw_params(chroma_like) == {"space": "cosine", "construction_ef": 200, "search_ef": "default", "M": 16}
    legacy = MagicMock(metadata={"hnsw:space": "l2"}, configuration=None, spec=["metadata", "configuration"])
    assert hnsw_params(legacy)["space"] == "l2"
    assert (
        hnsw_params(MagicMock(metadata={}, configuration=None, spec=["metadata", "configuration"]))["space"]
        == "unknown"
    )
