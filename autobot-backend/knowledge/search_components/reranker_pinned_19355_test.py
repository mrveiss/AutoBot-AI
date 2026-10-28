# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The reranker loads ``ResultReranker.MODEL_NAME`` at its pinned revision, verified (#19355).

Owner decision (2026-10-24): the KB helper models are code-pinned and their config keys are
removed. ``RAGConfig.reranking_model`` and ``knowledge.rag.reranking_model`` were never read by
the loader, so they are retired, and the one source is the constant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared import pinned_model_registry
from knowledge.search_components import reranking
from knowledge.search_components.reranking import ResultReranker, get_cross_encoder
from services.rag_config import RAGConfig

_COMPLETE_YAML = Path(__file__).resolve().parents[3] / "autobot-infrastructure/shared/config/complete.yaml"


@pytest.fixture
def fresh_loader(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """A cold loader whose CrossEncoder records ``(name, revision)`` instead of downloading."""
    import sentence_transformers

    loaded: list[tuple[str, str]] = []
    monkeypatch.setattr(reranking, "_cross_encoder_model", None)
    monkeypatch.setattr(reranking, "_reranking_active", True)
    monkeypatch.setattr(
        sentence_transformers, "CrossEncoder", lambda name, revision: loaded.append((name, revision)) or object()
    )
    return loaded


def test_the_loaded_model_is_the_constant_at_its_pinned_revision(fresh_loader, monkeypatch) -> None:
    verified: list[str] = []
    monkeypatch.setattr(pinned_model_registry, "verify_cached_model", lambda repo_id, **_: verified.append(repo_id))
    assert get_cross_encoder() is not None
    name = ResultReranker.MODEL_NAME
    assert fresh_loader == [(name, pinned_model_registry.get_pinned_revision(name))]
    assert verified == [name]


def test_a_digest_mismatch_leaves_no_model(fresh_loader, monkeypatch) -> None:
    def mismatch(repo_id: str, **_: object) -> None:
        raise pinned_model_registry.ModelIntegrityError(f"{repo_id}: sha256 mismatch")

    monkeypatch.setattr(pinned_model_registry, "verify_cached_model", mismatch)
    assert get_cross_encoder() is None
    assert reranking._cross_encoder_model is reranking._LOAD_FAILED
    assert not reranking.is_reranking_active()


def test_a_local_directory_named_like_the_model_is_refused(fresh_loader, monkeypatch, tmp_path) -> None:
    """A same-named directory in the working directory would load unverified weights (#19355 review)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ResultReranker.MODEL_NAME).mkdir(parents=True)
    assert get_cross_encoder() is None
    assert fresh_loader == []  # refused before CrossEncoder was ever called


def test_the_inert_config_field_and_yaml_key_are_retired() -> None:
    assert "reranking_model" not in RAGConfig.__dataclass_fields__
    assert "reranking_model" not in RAGConfig().to_dict()
    assert "reranking_model:" not in _COMPLETE_YAML.read_text(encoding="utf-8")


def test_a_stored_config_carrying_the_old_key_still_loads() -> None:
    """Saved RAG configs written before #19355 still hold the key; from_dict drops unknown keys."""
    assert RAGConfig.from_dict({"reranking_model": "anything", "enable_reranking": False}).enable_reranking is False
