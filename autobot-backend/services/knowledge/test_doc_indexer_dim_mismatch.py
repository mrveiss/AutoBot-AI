# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for embedding-dimension mismatch handling — Issue #10420.

A ChromaDB collection's vector dimension is fixed at creation. When the active
embedding model's dimension differs from the existing collection's recorded
dimension, ``get_or_create_collection`` returns the OLD collection and every
upsert is rejected, flooding the log with one warning per dropped chunk.

These tests cover ``DocIndexerService._resolve_collection``:
  * matching dim -> no recreate (no-op), idempotent on second resolve
  * mismatch + flag OFF -> single clear error, no per-chunk flood, no wipe
  * mismatch + flag ON -> collection deleted + recreated at new dim, re-index
    triggered (``needs_indexing()`` True)
  * provenance metadata written on (re)create
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing doc_indexer (mirrors test_doc_indexer)
# ---------------------------------------------------------------------------

_STUBS: dict = {}


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__package__ = name
    _STUBS[name] = mod
    sys.modules.setdefault(name, mod)
    return mod


_ssot = _make_stub("autobot_shared.ssot_config")
_ssot.get_ollama_url = lambda: "http://localhost:11434"  # type: ignore[attr-defined]  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

_constants = _make_stub("constants")
_path_constants = _make_stub("constants.path_constants")


class _FakePATH:
    DATA_DIR = Path("/tmp/test_autobot_data")  # nosec B108 - test/controlled code uses tmpdir intentionally
    PROJECT_ROOT = Path("/tmp/test_autobot_root")  # nosec B108 - test/controlled code uses tmpdir intentionally


_path_constants.PATH = _FakePATH()  # type: ignore[attr-defined]

_DOC_INDEXER_PATH = Path(__file__).parent / "doc_indexer.py"
_spec = importlib.util.spec_from_file_location("services.knowledge.doc_indexer", str(_DOC_INDEXER_PATH))
assert _spec and _spec.loader, "Could not load doc_indexer spec"
_doc_indexer_mod = importlib.util.module_from_spec(_spec)
sys.modules["services.knowledge.doc_indexer"] = _doc_indexer_mod
_spec.loader.exec_module(_doc_indexer_mod)  # type: ignore[union-attr]

if "services.knowledge" in sys.modules:
    sys.modules["services.knowledge"].doc_indexer = _doc_indexer_mod  # type: ignore[attr-defined]

from autobot_shared.embedding_provenance import (  # noqa: E402
    EmbeddingMismatchError,
    EmbeddingProvenance,
    provenance_from_metadata,
    provenance_to_metadata,
)
from services.knowledge.doc_indexer import (  # noqa: E402 — after sys.modules patch
    AUTO_REINDEX_ON_DIM_MISMATCH_ENV,
    DocIndexerService,
    _auto_reindex_on_dim_mismatch,
)

_MODULE = "services.knowledge.doc_indexer"
_COLLECTION = DocIndexerService.COLLECTION_NAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCollection:
    """Minimal stand-in for a BaseCollection carrying name + metadata."""

    def __init__(self, name: str, metadata: dict, vector_dim: int | None = None) -> None:
        self.name = name
        self.metadata = metadata
        self._count = 1 if vector_dim else 0
        self._vector_dim = vector_dim

    def count(self) -> int:
        return self._count

    def peek(self, limit: int = 1):
        if not self._vector_dim:
            return {"embeddings": []}
        return {"embeddings": [[0.0] * self._vector_dim]}


class _FakeClient:
    """In-memory fake of the BaseClient seam used by DocIndexerService."""

    def __init__(self, existing: _FakeCollection | None = None) -> None:
        self._collections: dict = {}
        if existing is not None:
            self._collections[existing.name] = existing
        self.deleted: list = []
        self.created: list = []

    def list_collections(self):
        return list(self._collections.values())

    def get_or_create_collection(self, name: str, metadata: dict | None = None):
        if name not in self._collections:
            col = _FakeCollection(name, dict(metadata or {}))
            self._collections[name] = col
            self.created.append((name, dict(metadata or {})))
        return self._collections[name]

    def get_collection(self, name: str):
        if name not in self._collections:
            raise ValueError(f"no such collection: {name}")
        return self._collections[name]

    def delete_collection(self, name: str) -> None:
        if name not in self._collections:
            raise ValueError(f"no such collection: {name}")
        self.deleted.append(name)
        del self._collections[name]


def _make_service(client: _FakeClient) -> DocIndexerService:
    svc = DocIndexerService.__new__(DocIndexerService)
    svc._client = client
    svc._collection = None
    svc._initialized = False
    svc._needs_reindex = False
    return svc


def _existing(model: str, dim: int) -> _FakeCollection:
    meta = {"hnsw:space": "cosine", **provenance_to_metadata(EmbeddingProvenance(model, dim))}
    return _FakeCollection(_COLLECTION, meta)


# ---------------------------------------------------------------------------
# Flag helper
# ---------------------------------------------------------------------------


class TestAutoReindexFlag:
    def test_defaults_to_false(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop(AUTO_REINDEX_ON_DIM_MISMATCH_ENV, None)
            assert _auto_reindex_on_dim_mismatch() is False

    @pytest.mark.parametrize("val", ["true", "1", "yes", "TRUE", "Yes"])
    def test_truthy_values_enable(self, val: str) -> None:
        with patch.dict("os.environ", {AUTO_REINDEX_ON_DIM_MISMATCH_ENV: val}):
            assert _auto_reindex_on_dim_mismatch() is True

    @pytest.mark.parametrize("val", ["false", "0", "no", "", "off"])
    def test_falsy_values_disable(self, val: str) -> None:
        with patch.dict("os.environ", {AUTO_REINDEX_ON_DIM_MISMATCH_ENV: val}):
            assert _auto_reindex_on_dim_mismatch() is False


# ---------------------------------------------------------------------------
# Matching dimension -> no-op
# ---------------------------------------------------------------------------


class TestMatchingDim:
    def test_matching_dim_no_recreate(self) -> None:
        """Active model dim == existing collection dim -> no delete, no recreate."""
        client = _FakeClient(_existing("nomic-embed-text", 768))
        svc = _make_service(client)

        col = svc._resolve_collection("nomic-embed-text")

        assert col.name == _COLLECTION
        assert client.deleted == []
        assert client.created == []  # collection already existed
        assert svc._needs_reindex is False

    def test_second_resolve_is_idempotent(self) -> None:
        """A second resolve with matching dims is a no-op (no wipe, no recreate)."""
        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        svc._resolve_collection("all-minilm")
        svc._resolve_collection("all-minilm")

        assert client.deleted == []
        assert client.created == []
        assert svc._needs_reindex is False

    def test_legacy_untagged_collection_not_recreated(self) -> None:
        """A collection with no provenance metadata is left untouched (legacy)."""
        client = _FakeClient(_FakeCollection(_COLLECTION, {"hnsw:space": "cosine"}))
        svc = _make_service(client)

        svc._resolve_collection("nomic-embed-text")

        assert client.deleted == []
        assert svc._needs_reindex is False


# ---------------------------------------------------------------------------
# Mismatch, flag OFF -> single clear error, no flood, no wipe
# ---------------------------------------------------------------------------


class TestMismatchFlagOff:
    def test_raises_single_clear_error(self) -> None:
        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=False):
            with pytest.raises(EmbeddingMismatchError) as exc:
                svc._resolve_collection("nomic-embed-text")

        msg = str(exc.value)
        assert "all-minilm" in msg and "nomic-embed-text" in msg
        assert "384" in msg and "768" in msg
        assert AUTO_REINDEX_ON_DIM_MISMATCH_ENV in msg

    def test_does_not_wipe_collection(self) -> None:
        """Flag OFF must never delete or recreate the collection."""
        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=False):
            with pytest.raises(EmbeddingMismatchError):
                svc._resolve_collection("nomic-embed-text")

        assert client.deleted == []
        assert client.created == []
        assert svc._needs_reindex is False

    def test_single_log_not_per_chunk_flood(self, caplog) -> None:
        """The mismatch is surfaced once (raise) — not one warning per chunk."""
        import logging

        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with caplog.at_level(logging.WARNING, logger=_MODULE):
            with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=False):
                with pytest.raises(EmbeddingMismatchError):
                    svc._resolve_collection("nomic-embed-text")

        # No per-chunk warning flood: the error is raised once, not logged repeatedly.
        flood = [r for r in caplog.records if "Dropping chunk" in r.getMessage()]
        assert flood == []


# ---------------------------------------------------------------------------
# Mismatch, flag ON -> recreate + re-index
# ---------------------------------------------------------------------------


class TestMismatchFlagOn:
    def test_collection_deleted_and_recreated_at_new_dim(self) -> None:
        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=True):
            col = svc._resolve_collection("nomic-embed-text")

        assert client.deleted == [_COLLECTION]
        assert len(client.created) == 1
        # New collection carries the new model's provenance (dim 768).
        _name, new_meta = client.created[0]
        prov = provenance_from_metadata(new_meta)
        assert prov is not None
        assert prov.model_name == "nomic-embed-text"
        assert prov.dim == 768
        assert col.metadata == new_meta

    def test_recreate_triggers_reindex(self) -> None:
        """After a destructive recreate, needs_indexing() must report True."""
        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=True):
            svc._resolve_collection("nomic-embed-text")

        svc._initialized = True  # needs_indexing requires initialized + collection
        assert svc._needs_reindex is True
        assert svc.needs_indexing() is True

    def test_recreate_logs_once(self, caplog) -> None:
        import logging

        client = _FakeClient(_existing("all-minilm", 384))
        svc = _make_service(client)

        with caplog.at_level(logging.WARNING, logger=_MODULE):
            with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=True):
                svc._resolve_collection("nomic-embed-text")

        mismatch_logs = [r for r in caplog.records if "embedding dimension changed" in r.getMessage()]
        assert len(mismatch_logs) == 1


# ---------------------------------------------------------------------------
# Provenance written on first create (no pre-existing collection)
# ---------------------------------------------------------------------------


class TestProvenanceOnCreate:
    def test_fresh_create_writes_provenance(self) -> None:
        client = _FakeClient(existing=None)
        svc = _make_service(client)

        col = svc._resolve_collection("nomic-embed-text")

        assert client.deleted == []
        assert len(client.created) == 1
        prov = provenance_from_metadata(col.metadata)
        assert prov is not None
        assert prov.model_name == "nomic-embed-text"
        assert prov.dim == 768
        assert svc._needs_reindex is False

    def test_unknown_model_creates_without_provenance(self) -> None:
        """An unknown model (no _KNOWN_DIMS entry) creates a collection sans dim provenance."""
        client = _FakeClient(existing=None)
        svc = _make_service(client)

        col = svc._resolve_collection("some-future-model")

        assert provenance_from_metadata(col.metadata) is None
        assert col.metadata.get("hnsw:space") == "cosine"


# ---------------------------------------------------------------------------
# Dimension resolution: config > _KNOWN_DIMS > live probe (#10420)
# ---------------------------------------------------------------------------


class TestResolveEmbedDim:
    def test_uses_configured_dim_first(self) -> None:
        svc = _make_service(_FakeClient())
        assert svc._resolve_embed_dim("anything", 1234) == 1234

    def test_falls_back_to_known_dims(self) -> None:
        svc = _make_service(_FakeClient())
        assert svc._resolve_embed_dim("nomic-embed-text", None) == 768

    def test_probes_unknown_model(self) -> None:
        """A model not in _KNOWN_DIMS is probed for its real dimension (e.g. 3072)."""
        svc = _make_service(_FakeClient())
        svc._embed_model = MagicMock()
        svc._embed_model.get_text_embedding.return_value = [0.0] * 3072
        assert svc._resolve_embed_dim("some-3072-model", None) == 3072

    def test_probe_failure_returns_none(self) -> None:
        svc = _make_service(_FakeClient())
        svc._embed_model = MagicMock()
        svc._embed_model.get_text_embedding.side_effect = RuntimeError("ollama down")
        assert svc._resolve_embed_dim("some-model", None) is None


# ---------------------------------------------------------------------------
# Legacy collection (no provenance) detected via peek (#10420)
# ---------------------------------------------------------------------------


class TestLegacyPeekMismatch:
    def test_legacy_collection_with_mismatched_vectors_detected(self) -> None:
        """The real box case: a legacy 768-dim collection (no provenance) + a 3072 model.

        Detected via peek and recreated when the opt-in flag is ON.
        """
        legacy = _FakeCollection(_COLLECTION, {"hnsw:space": "cosine"}, vector_dim=768)
        client = _FakeClient(legacy)
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=True):
            svc._resolve_collection("some-3072-model", embed_dim=3072)

        assert client.deleted == [_COLLECTION]
        assert svc._needs_reindex is True

    def test_legacy_mismatch_flag_off_raises_once(self) -> None:
        legacy = _FakeCollection(_COLLECTION, {"hnsw:space": "cosine"}, vector_dim=768)
        svc = _make_service(_FakeClient(legacy))

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=False):
            with pytest.raises(EmbeddingMismatchError) as exc:
                svc._resolve_collection("some-3072-model", embed_dim=3072)
        assert "768" in str(exc.value) and "3072" in str(exc.value)

    def test_empty_legacy_collection_untouched(self) -> None:
        """No vectors -> peek yields no dim -> no recreate (cannot infer a mismatch)."""
        legacy = _FakeCollection(_COLLECTION, {"hnsw:space": "cosine"})
        client = _FakeClient(legacy)
        svc = _make_service(client)

        svc._resolve_collection("some-3072-model", embed_dim=3072)
        assert client.deleted == []
        assert svc._needs_reindex is False


# ---------------------------------------------------------------------------
# Provenance-tagged collection + probed unknown model (#10420)
# ---------------------------------------------------------------------------


class TestProvenanceWithProbedDim:
    def test_stored_768_vs_probed_3072_detected(self) -> None:
        client = _FakeClient(_existing("nomic-embed-text", 768))
        svc = _make_service(client)

        with patch(f"{_MODULE}._auto_reindex_on_dim_mismatch", return_value=True):
            svc._resolve_collection("some-3072-model", embed_dim=3072)
        assert client.deleted == [_COLLECTION]
        assert svc._needs_reindex is True
