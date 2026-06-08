# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""#6514: ChromaDB collection provenance — pin which embedding model wrote
each collection so silent cross-model contamination is detectable.

## Why

Two paths in the codebase write embeddings to ChromaDB collections using
different models with incompatible vector spaces:

  - ``autobot-backend/code_embedding_generator.py`` — `microsoft/codebert-base`
    (768-dim, transformer)
  - ``autobot-backend/background_vectorization.py`` — `DEFAULT_EMBEDDING_MODEL`
    (`nomic-embed-text` per memory; different dim and different vector space)

ChromaDB doesn't validate dim/model match across writes — it accepts any
vector and computes cosine distance regardless. So a query embedded with
model A against a collection contaminated with model-B writes returns
mathematically meaningless results, with no error or warning. RAG over
code is silently degraded.

## What this module provides

The minimum-viable defensive surface to fail-fast on mismatched writes:

1. ``EmbeddingProvenance`` dataclass — `(model_name, dim)` pair.
2. ``EmbeddingMismatchError`` — explicit error raised on mismatch.
3. ``provenance_to_metadata(provenance)`` — turn provenance into a
   ChromaDB-compatible ``metadata`` dict (only str/int/float values
   allowed by Chroma).
4. ``provenance_from_metadata(metadata)`` — extract provenance from an
   existing collection's metadata; returns ``None`` if the collection
   was created before tagging was wired up (preserves backwards compat
   for legacy collections).
5. ``validate_vectors_against_provenance(vectors, provenance)`` —
   guard at write time. Raises ``EmbeddingMismatchError`` if any vector's
   dim doesn't match the collection's recorded dim.

The helper is callable side; production wiring lives in the ChromaDB
client wrapper(s) — one chokepoint per collection.add() path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Sequence

__all__ = [
    "EmbeddingMismatchError",
    "EmbeddingProvenance",
    "provenance_to_metadata",
    "provenance_from_metadata",
    "validate_vectors_against_provenance",
    "PROVENANCE_METADATA_PREFIX",
]


# Metadata-key prefix so this module's keys don't collide with whatever
# else the caller has already written to ``collection.metadata`` (e.g.
# `hnsw:space` is a reserved Chroma key).
PROVENANCE_METADATA_PREFIX = "autobot.embedding_provenance"


class EmbeddingMismatchError(ValueError):
    """Raised when a vector's provenance doesn't match its collection's.

    Subclass of ``ValueError`` so existing ``try: ... except ValueError``
    blocks degrade gracefully (return 4xx instead of 500), but callers
    that want explicit handling can catch the more specific type.
    """


@dataclass(frozen=True)
class EmbeddingProvenance:
    """Identifies the embedding model used to populate a collection.

    Pinning is by ``(model_name, dim)`` — both are required because:

      - ``model_name`` alone misses cross-version drift (a new
        codebert-base release with the same name but different layer
        layout would silently break recall).
      - ``dim`` alone misses model swaps that happen to share dim
        (e.g. ``nomic-embed-text`` and ``all-MiniLM-L6-v2`` are both
        384-dim but live in different vector spaces).
    """

    model_name: str
    dim: int

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name:
            raise ValueError("EmbeddingProvenance.model_name must be a non-empty string")
        if not isinstance(self.dim, int) or self.dim <= 0:
            raise ValueError(f"EmbeddingProvenance.dim must be a positive int; got {self.dim!r}")


def provenance_to_metadata(provenance: EmbeddingProvenance) -> Dict[str, Any]:
    """Render provenance as a ChromaDB collection-metadata dict.

    ChromaDB's metadata only accepts str/int/float values — no nesting,
    no lists. Use a flat namespace prefix to avoid colliding with
    reserved keys like ``hnsw:space``.
    """
    return {
        f"{PROVENANCE_METADATA_PREFIX}.model_name": provenance.model_name,
        f"{PROVENANCE_METADATA_PREFIX}.dim": int(provenance.dim),
    }


def provenance_from_metadata(metadata: Dict[str, Any] | None) -> EmbeddingProvenance | None:
    """Recover provenance from a collection's metadata dict.

    Returns ``None`` if the metadata is missing both provenance keys —
    treat as untagged (legacy collection). Returns ``None`` if EITHER
    key is missing or malformed (defensive: don't half-validate).
    """
    if not metadata:
        return None
    model_key = f"{PROVENANCE_METADATA_PREFIX}.model_name"
    dim_key = f"{PROVENANCE_METADATA_PREFIX}.dim"
    if model_key not in metadata or dim_key not in metadata:
        return None
    model_name = metadata.get(model_key)
    dim_raw = metadata.get(dim_key)
    if not isinstance(model_name, str) or not model_name:
        return None
    try:
        dim = int(dim_raw)  # type: ignore[arg-type]  # GH#7105: dim_raw from metadata dict is Any at runtime
    except (TypeError, ValueError):
        return None
    if dim <= 0:
        return None
    return EmbeddingProvenance(model_name=model_name, dim=dim)


def validate_vectors_against_provenance(
    vectors: Sequence[Sequence[float]],
    provenance: EmbeddingProvenance,
) -> None:
    """Raise ``EmbeddingMismatchError`` if any vector's dim doesn't match.

    ``vectors`` may be any sized sequence (list, numpy array, etc.) —
    we only need ``len()``. Empty input is a no-op (no vectors to check).

    Note: we can't validate ``model_name`` from a vector alone (that's
    a metadata-only check the caller does at registration time). The
    runtime guard is dim-only — but that's enough to catch the common
    contamination case from the #6514 reproducer (768 vs 384-dim).
    """
    if not vectors:
        return
    expected_dim = provenance.dim
    for i, vec in enumerate(vectors):
        try:
            actual_dim = len(vec)
        except TypeError as exc:
            raise EmbeddingMismatchError(
                f"#6514: vector at index {i} is not a sequence (type {type(vec).__name__}) — "
                f"cannot validate against provenance {provenance!r}"
            ) from exc
        if actual_dim != expected_dim:
            raise EmbeddingMismatchError(
                f"#6514: vector at index {i} has dim {actual_dim} but collection "
                f"provenance expects dim {expected_dim} (model {provenance.model_name!r}). "
                f"Cross-model writes to a single ChromaDB collection produce mathematically "
                f"meaningless cosine distances at query time — re-embed with the registered "
                f"model or write to a separate collection."
            )


def _safe_iter_vectors(maybe_iterable: Any) -> Iterable[Sequence[float]]:
    """Best-effort coercion for callers that pass numpy arrays etc."""
    if maybe_iterable is None:
        return ()
    try:
        return list(maybe_iterable)
    except TypeError:
        return ()
