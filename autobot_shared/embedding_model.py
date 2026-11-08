# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one resolver for the active embedding model (#18143).

The generator (`services.npu_client`) and every embedding-cache key must name the same
model, or a vector made by model A is served under model B's key. Both ask this function,
so a change to ``AUTOBOT_EMBEDDING_MODEL`` moves them together.

#19377: the user can switch the embedding model at runtime (owner, 2026-10-23: "user can
switch llm providers at any moment"). The switch is a user OVERRIDE held in Redis, so every
process -- backend workers, celery, the vectorizer -- sees the same answer; the SSOT value
(``AUTOBOT_EMBEDDING_MODEL``) is the default under it. Only an embedding model can be an
override. It is set by the rebuild-and-cutover flow (#19379), never by a bare write, because
changing the model without re-indexing strands every stored vector.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

# Must import under a fully mocked config: autobot_shared/import_under_mocked_config_19288_test.py.
logger = get_logger(__name__)

EMBEDDING_OVERRIDE_KEY = "autobot:kb:embedding_model"
EMBEDDING_OVERRIDE_CACHE_S = env_float_clamped("AUTOBOT_EMBEDDING_OVERRIDE_CACHE_SECONDS", 5.0, 0.0, 300.0)

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
_NAMESPACE_CHARS = re.compile(r"[\w.\-]+")


def is_embedding_model_id(value: str) -> bool:
    """True when ``value`` is a bare (optionally ``org/``-namespaced) known embedding-model id."""
    name = value.strip().lower()
    head, sep, rest = name.partition("/")  # linear: no backtracking over uncontrolled input
    if sep and _NAMESPACE_CHARS.fullmatch(head):
        name = rest
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


@dataclass(frozen=True)
class EmbeddingSpace:
    """The override record: the model AND the KB collection that holds its vectors (#19379).

    One record, so a reader can never pair the new model with the old collection: queries
    embedded by model B against vectors made by model A answer garbage, or fail on dimension.
    ``collection`` is None for a legacy record (a bare model string), which keeps the KB's
    configured collection. ``generation`` grows on every switch; a process that sees a
    generation newer than the one it bound rebinds its KB.
    """

    model: str
    collection: str | None = None
    generation: int = 0


# (monotonic time read, record or None). Short-lived, so a switch reaches every reader
# within EMBEDDING_OVERRIDE_CACHE_S without each call costing a Redis round trip.
_override_cache: tuple[float, EmbeddingSpace | None] | None = None


def _redis():
    from autobot_shared.redis_client import get_redis_client

    return get_redis_client(database="knowledge")


def _parse_record(raw: str) -> EmbeddingSpace | None:
    """A JSON record, or a bare model id (the #19377 form, still read)."""
    if not raw.lstrip().startswith("{"):
        return EmbeddingSpace(model=raw)
    data = json.loads(raw)
    return EmbeddingSpace(str(data["model"]), data.get("collection") or None, int(data.get("generation", 0)))


def _read_override() -> EmbeddingSpace | None:
    """The user's override record, or None. An unreadable store or an invalid value falls back
    to the SSOT default, loudly: the model must never become something that cannot embed."""
    global _override_cache
    now = time.monotonic()
    if _override_cache is not None and now - _override_cache[0] < EMBEDDING_OVERRIDE_CACHE_S:
        return _override_cache[1]
    record: EmbeddingSpace | None = None
    try:
        client = _redis()
        raw = client.get(EMBEDDING_OVERRIDE_KEY) if client is not None else None
        raw = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        record = _parse_record(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 - the store is optional; the default still works
        logger.warning("embedding-model override unreadable (%s); using the configured default", exc)
    if record is not None and not is_embedding_model_id(record.model):
        logger.error("embedding-model override %r is not an embedding model; ignored (#19377)", record.model)
        record = None
    _override_cache = (now, record)
    return record


def set_embedding_model_override(model: str, collection: str) -> EmbeddingSpace:
    """Make *model* and *collection* the active embedding space for every process (#19377).

    For the rebuild-and-cutover flow (#19379) only, once the new collection is complete and
    verified; a guard pins that single caller. Model and collection are one write, so no
    reader sees one without the other. Raises ValueError for a model that is not an embedding
    model and RuntimeError when the store cannot be written -- a switch that silently did not
    happen is worse than one that failed visibly.
    """
    global _override_cache
    if not is_embedding_model_id(model):
        raise ValueError(f"{model!r} is not an embedding model")
    if not collection:
        raise ValueError("a switch names the collection that holds the new model's vectors")
    _override_cache = None
    current = _read_override()
    record = EmbeddingSpace(model, collection, (current.generation if current else 0) + 1)
    payload = json.dumps({"model": record.model, "collection": record.collection, "generation": record.generation})
    client = _redis()
    if client is None or not client.set(EMBEDDING_OVERRIDE_KEY, payload):
        raise RuntimeError("the embedding-model override could not be written")
    _override_cache = None
    return record


def active_embedding_space() -> EmbeddingSpace | None:
    """The override record (model, collection, generation), or None while the SSOT default rules."""
    return _read_override()


def active_embedding_model() -> str:
    """The embedding model in use: the user's override (#19377), else the configured default."""
    override = _read_override()
    if override:
        return override.model
    from autobot_shared.ssot_config import config

    return config.llm.embedding_model


def active_npu_worker_model() -> str:
    """The active embedding model in the bare form the NPU worker loads it (#18143)."""
    return npu_worker_model_name(active_embedding_model())
