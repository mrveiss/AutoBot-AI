# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one resolver for the active embedding model (#18143).

The generator (`services.npu_client`) and every embedding-cache key must name the same
model, or a vector made by model A is served under model B's key. Both ask this function,
so a change to ``AUTOBOT_EMBEDDING_MODEL`` moves them together.
"""

from __future__ import annotations

import re

# Lower-case name prefixes of known embedding-model families, matched after an optional
# ``org/`` namespace. The one list: ``is_embedding_model_id`` and the literal guard
# (repo_tests/embedding_model_literal_guard_18143_test.py) both read it (#18328).
KNOWN_EMBEDDING_MODEL_PREFIXES: tuple[str, ...] = (
    "nomic-embed",
    "mxbai-embed",
    "snowflake-arctic-embed",
    "all-minilm",
    "all-mpnet",
    "paraphrase-",
    "multi-qa-",
    "bge-",
    "e5-",
    "multilingual-e5-",
    "gte-",
    "jina-embeddings",
    "text-embedding",
    "codebert",
)
_MODEL_ID_TAIL = re.compile(r"[\w.\-]*(:[\w.\-]+)?")
_NAMESPACE = re.compile(r"[\w.\-]+/")


def is_embedding_model_id(value: str) -> bool:
    """True when ``value`` is a bare (optionally ``org/``-namespaced) known embedding-model id."""
    name = value.strip().lower()
    namespace = _NAMESPACE.match(name)
    if namespace:
        name = name[namespace.end() :]
    if not name.startswith(KNOWN_EMBEDDING_MODEL_PREFIXES) or "rerank" in name:
        return False  # a cross-encoder reranker (bge-reranker-*) shares the family prefix, not the role
    return _MODEL_ID_TAIL.fullmatch(name) is not None


class EmbeddingUnavailableError(RuntimeError):
    """The active embedding model could not produce a vector.

    Raised instead of embedding with a different model: vectors from another model are not
    comparable with the stored ones (#18185).
    """


def raise_if_embedding_refused(metrics: object) -> None:
    """Raise EmbeddingUnavailableError if a search's metrics record an embedding refusal (#18185).

    A refused search returns ``([], metrics)`` with ``metrics.error`` set; a caller that only
    reads the results would report an outage as "no matches".
    """
    reason = getattr(metrics, "error", None)
    if reason:
        raise EmbeddingUnavailableError(reason)


def npu_worker_model_name(model: str) -> str:
    """The name the NPU worker loads for ``model``: an Ollama-style ``:tag`` is not part of it.

    The worker keys its sessions on the bare name (``nomic-embed-text``) and answers an unknown
    name with a mock vector, so the worker boundary - and only it - sends this form (#18143).
    """
    return model.split(":", 1)[0]


def active_embedding_model() -> str:
    """Return the configured embedding model, read at call time (never cached)."""
    from autobot_shared.ssot_config import config

    return config.llm.embedding_model


def active_npu_worker_model() -> str:
    """The active embedding model in the bare form the NPU worker loads it (#18143)."""
    return npu_worker_model_name(active_embedding_model())
