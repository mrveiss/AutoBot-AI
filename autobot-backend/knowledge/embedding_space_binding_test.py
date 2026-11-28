# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A KB process follows a switch made anywhere, rebinding every collection-bound object (#19379)."""

from __future__ import annotations

import pytest

from autobot_shared.embedding_model import EmbeddingSpace
from knowledge import embedding_space_binding as binding

pytestmark = pytest.mark.asyncio


class _Buffer:
    def __init__(self, kb, name):
        self.kb, self.name = kb, name

    async def stop(self):
        # taken after the swap: the KB must already pair the new model with the new store
        self.kb.log.append(("stop", self.name, binding.snapshot(self.kb)))

    async def start(self):
        self.kb.log.append(("start", self.name))


class _KB:
    def __init__(self):
        self.log = []
        self.chromadb_path = "/tmp/chroma"
        self.chromadb_collection = "autobot_memory"
        self.vector_store = "store:autobot_memory"
        self._write_buffer = _Buffer(self, "autobot_memory")
        self.vector_index = object()
        self.embedding_model_name = "nomic-embed-text:latest"
        self._bound_generation = 0
        self._space_checked_at = 0.0

    def _build_hnsw_metadata(self):
        return {"hnsw:space": "cosine"}

    def _configure_embedding_provider(self, provider, model, endpoint, cfg):
        self.log.append(("embed", model))
        return 1024


@pytest.fixture
def kb(monkeypatch):
    monkeypatch.setattr(binding, "SPACE_CHECK_INTERVAL_S", 0.0)
    import knowledge.backends as backends

    monkeypatch.setattr(backends, "get_default_client", lambda **kw: object())

    async def _build(kb, client, collection, meta):
        # taken while building off to the side: the KB must still be wholly on the old space
        kb.log.append(("build", collection, binding.snapshot(kb)))
        return f"abc:{collection}", f"store:{collection}", _Buffer(kb, collection)

    monkeypatch.setattr(binding, "build_binding", _build)
    return _KB()


def _space(monkeypatch, space):
    monkeypatch.setattr(binding, "active_embedding_space", lambda: space)


async def test_a_rebind_builds_aside_swaps_once_then_drains_the_old_buffer(monkeypatch, kb):
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))
    assert await binding.ensure_current_space(kb) is True
    steps = [entry[0] for entry in kb.log]
    assert steps == ["build", "start", "embed", "stop"], kb.log
    during_build, after_swap = kb.log[0][2], kb.log[3][2]
    assert (during_build.model, during_build.vector_store) == ("nomic-embed-text:latest", "store:autobot_memory")
    assert (after_swap.model, after_swap.vector_store) == ("bge-m3:latest", "store:kb_bge")
    assert kb.log[3][1] == "autobot_memory", "the OLD buffer is drained, into the store it was made for"
    assert (kb.chromadb_collection, kb.vector_index, kb._bound_generation) == ("kb_bge", None, 1)
    assert kb.embedding_dimensions == 1024


async def test_a_failed_rebind_keeps_serving_from_the_bound_space(monkeypatch, kb):
    """code review on PR #19641: a rebind error must not make the KB accessors return None."""
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))

    async def _broken(kb, client, collection, meta):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(binding, "build_binding", _broken)
    assert await binding.ensure_current_space(kb) is False
    assert (kb.chromadb_collection, kb._bound_generation) == ("autobot_memory", 0)


async def test_a_swap_that_raises_stops_the_new_buffer_and_keeps_the_old_binding(monkeypatch, kb):
    """code review on PR #19641: an orphaned flush task per retry otherwise."""

    def _unsupported(provider, model, endpoint, cfg):
        raise ValueError("unsupported provider")

    kb._configure_embedding_provider = _unsupported
    with pytest.raises(ValueError):
        await binding.rebind(kb, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))
    stops = [entry[1] for entry in kb.log if entry[0] == "stop"]
    assert stops == ["kb_bge"], "the new buffer is stopped; the old one keeps serving"
    assert (kb.chromadb_collection, kb.vector_store, kb._bound_generation) == (
        "autobot_memory",
        "store:autobot_memory",
        0,
    )


async def test_the_bound_generation_does_not_rebind_again(monkeypatch, kb):
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))
    await binding.ensure_current_space(kb)
    kb.log.clear()
    assert await binding.ensure_current_space(kb) is False
    assert kb.log == []


async def test_an_operation_snapshot_is_the_bound_model_not_the_record(monkeypatch, kb):
    """#19379 review: the record can name a new model before this KB has rebound."""
    monkeypatch.setattr(binding, "SPACE_CHECK_INTERVAL_S", 60.0)
    kb._space_checked_at = binding.time.monotonic()
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))
    monkeypatch.setattr(binding, "active_embedding_model", lambda: "bge-m3:latest")
    space = await binding.current_space(kb)
    assert (space.model, space.vector_store) == ("nomic-embed-text:latest", "store:autobot_memory")


@pytest.mark.parametrize("space", [None, EmbeddingSpace("bge-m3:latest", None, 0)])
async def test_no_switch_or_a_legacy_record_leaves_the_kb_alone(monkeypatch, kb, space):
    _space(monkeypatch, space)
    assert await binding.ensure_current_space(kb) is False
    assert kb.log == [] and kb.chromadb_collection == "autobot_memory"


async def test_the_check_is_rate_limited(monkeypatch, kb):
    monkeypatch.setattr(binding, "SPACE_CHECK_INTERVAL_S", 60.0)
    kb._space_checked_at = binding.time.monotonic()
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 1))
    assert await binding.ensure_current_space(kb) is False


def test_init_binds_a_switched_collection(monkeypatch, kb):
    _space(monkeypatch, EmbeddingSpace("bge-m3:latest", "kb_bge", 4))
    assert binding.initial_collection(kb, "autobot_memory") == "kb_bge"
    assert kb._bound_generation == 4


def test_init_without_a_switch_keeps_the_configured_collection(monkeypatch, kb):
    _space(monkeypatch, None)
    assert binding.initial_collection(kb, "autobot_memory") == "autobot_memory"
    assert kb._bound_generation == 0
