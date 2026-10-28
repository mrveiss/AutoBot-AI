# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The user's embedding-model override, over the SSOT default (#19377)."""

from __future__ import annotations

import pytest

import autobot_shared.embedding_model as em


class _FakeRedis:
    def __init__(self, value=None, fail=False):
        self.value, self.fail, self.writes = value, fail, []

    def get(self, key):
        if self.fail:
            raise ConnectionError("down")
        assert key == em.EMBEDDING_OVERRIDE_KEY
        return self.value

    def set(self, key, value):
        self.writes.append((key, value))
        self.value = value.encode()
        return True


@pytest.fixture
def store(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(em, "_redis", lambda: fake)
    monkeypatch.setattr(em, "_override_cache", None)
    monkeypatch.setattr(em, "EMBEDDING_OVERRIDE_CACHE_S", 0.0)
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.llm, "embedding_model", "nomic-embed-text:latest")
    return fake


def test_without_an_override_the_configured_default_is_used(store):
    assert em.active_embedding_model() == "nomic-embed-text:latest"


def test_an_override_wins_without_a_restart(store):
    em.set_embedding_model_override("mxbai-embed-large:latest", "kb_mxbai")
    assert em.active_embedding_model() == "mxbai-embed-large:latest"
    assert [k for k, _ in store.writes] == [em.EMBEDDING_OVERRIDE_KEY]


def test_a_chat_model_cannot_be_set_as_the_override(store):
    with pytest.raises(ValueError, match="not an embedding model"):
        em.set_embedding_model_override("phi3:mini", "kb_phi3")
    assert store.writes == []


def test_an_invalid_value_found_in_the_store_is_ignored(store, caplog):
    """A hand-written or stale chat-model value must never become the active model."""
    store.value = b"phi3:mini"
    assert em.active_embedding_model() == "nomic-embed-text:latest"
    assert "not an embedding model; ignored" in caplog.text


def test_an_unreadable_store_falls_back_to_the_default_loudly(monkeypatch, store, caplog):
    monkeypatch.setattr(em, "_redis", lambda: _FakeRedis(fail=True))
    assert em.active_embedding_model() == "nomic-embed-text:latest"
    assert "override unreadable" in caplog.text


def test_a_failed_write_raises_rather_than_switching_silently(monkeypatch, store):
    monkeypatch.setattr(em, "_redis", lambda: None)
    with pytest.raises(RuntimeError, match="could not be written"):
        em.set_embedding_model_override("nomic-embed-text:latest", "kb_nomic")


def test_the_override_is_cached_for_the_window(monkeypatch, store):
    monkeypatch.setattr(em, "EMBEDDING_OVERRIDE_CACHE_S", 60.0)
    store.value = b"mxbai-embed-large:latest"
    assert em.active_embedding_model() == "mxbai-embed-large:latest"
    store.value = b"bge-m3:latest"
    assert em.active_embedding_model() == "mxbai-embed-large:latest", "served from the cache"


def test_a_switch_in_this_process_is_seen_at_once_despite_the_cache(monkeypatch, store):
    """The cache window delays OTHER processes; the writer drops its own cache, so it sees the switch."""
    monkeypatch.setattr(em, "EMBEDDING_OVERRIDE_CACHE_S", 60.0)
    store.value = b"mxbai-embed-large:latest"
    assert em.active_embedding_model() == "mxbai-embed-large:latest", "the old value is now cached"

    em.set_embedding_model_override("bge-m3:latest", "kb_bge")

    assert em.active_embedding_model() == "bge-m3:latest"


# --- #19379: the override is one record, model AND collection ---------------------------------


def test_a_switch_writes_model_and_collection_as_one_record(store):
    record = em.set_embedding_model_override("mxbai-embed-large:latest", "kb_mxbai")
    assert em.active_embedding_space() == record == em.EmbeddingSpace("mxbai-embed-large:latest", "kb_mxbai", 1)
    assert len(store.writes) == 1, "one write, so no reader sees the model without its collection"


def test_each_switch_raises_the_generation(store):
    em.set_embedding_model_override("mxbai-embed-large:latest", "kb_mxbai")
    assert em.set_embedding_model_override("bge-m3:latest", "kb_bge").generation == 2


def test_a_switch_without_a_collection_is_refused(store):
    with pytest.raises(ValueError, match="names the collection"):
        em.set_embedding_model_override("bge-m3:latest", "")
    assert store.writes == []


def test_a_legacy_bare_model_value_still_reads_with_no_collection(store):
    """A value written by #19377 (a bare model id) keeps the KB on its configured collection."""
    store.value = b"mxbai-embed-large:latest"
    assert em.active_embedding_space() == em.EmbeddingSpace("mxbai-embed-large:latest", None, 0)
    assert em.active_embedding_model() == "mxbai-embed-large:latest"


def test_a_record_naming_a_chat_model_is_ignored(store, caplog):
    store.value = b'{"model": "phi3:mini", "collection": "kb_phi3", "generation": 3}'
    assert em.active_embedding_space() is None
    assert em.active_embedding_model() == "nomic-embed-text:latest"
