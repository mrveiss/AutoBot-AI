# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The embedding space each searched index was built in, recorded as data (#18185, #18217).

Owner rule (#18185): a query is embedded with the model its index was built with, or the search
refuses. The space is read from this table, never inferred at query time. No index here stores the
model that built it, so every row comes from the index's known build path; a row whose build path
does not determine a reproducible space carries a refusal instead of a guess.

The knowledge base's own vector index is not a row: the knowledge base embeds its queries with the
model that built it, so no caller supplies a vector for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from autobot_shared.embedding_model import EmbeddingUnavailableError

HYBRID_FAISS_INDEX = "hybrid_faiss"
CODE_INDEX = "autobot_code_embeddings"
TEXT_ACCESSOR = "npu_client"  # services.npu_client: the NPU worker, else Ollama, same model name

_FAISS_UNRECORDED = (
    "nothing records which model built it: no code path writes to it, none loads a saved copy, and a saved "
    "copy holds ids only; its 384-d is a config default, not a recorded model (#18217)"
)
_UNIFIED_UNREPRODUCIBLE = (
    "written by accelerated_embedding_generation, whose output is the NPU worker's model or MiniLM through "
    "an untrained projection re-randomised at every process start, so no query can be put in its space (#18217)"
)
# The code-intelligence collections are written and queried by the same class with the text accessor, so
# the build path names the model: nomic-embed-text, 768-d (the hash fallback of the pattern analyzer is
# 768-d for the same reason). Their names are the rows; the model literal lives here and nowhere else (#18143).
PATTERN_MODEL = "nomic-embed-text"
PATTERN_DIM = 768
PATTERN_INDEXES = (
    "code_patterns",
    "cross_language_patterns",
    "code_analysis_vectors",
    "config_pattern_vectors",
    "duplicate_code_vectors",
    "bug_pattern_vectors",
    "code_review_patterns",
    "anti_pattern_vectors",
    "performance_analysis_vectors",
    "security_analysis_vectors",
)
ACCELERATOR_COLLECTIONS = (
    "autobot_text_embeddings",
    "autobot_image_embeddings",
    "autobot_audio_embeddings",
    "autobot_multimodal_fused",
)


@dataclass(frozen=True)
class IndexSpace:
    """The model and dimension an index was built with; ``refusal`` when that is not determinable."""

    model_id: str | None
    dim: int | None
    refusal: str | None = None
    accessor: str = TEXT_ACCESSOR

    @property
    def space_id(self) -> str:
        """Names the space a vector is in; embedding-cache keys use it (#18143)."""
        return f"{self.model_id}/{self.dim}"


@lru_cache(maxsize=1)
def index_spaces() -> dict[str, IndexSpace]:
    """index name -> the space that built it. Lazy: the code row reads the generator's constants."""
    from code_embedding_generator import CODEBERT_EMBEDDING_DIM, CODEBERT_MODEL_NAME

    spaces = {name: IndexSpace(None, None, _UNIFIED_UNREPRODUCIBLE) for name in ACCELERATOR_COLLECTIONS}
    spaces.update({name: IndexSpace(PATTERN_MODEL, PATTERN_DIM) for name in PATTERN_INDEXES})
    spaces[HYBRID_FAISS_INDEX] = IndexSpace(None, None, _FAISS_UNRECORDED)
    spaces[CODE_INDEX] = IndexSpace(CODEBERT_MODEL_NAME, CODEBERT_EMBEDDING_DIM, accessor="code_embedding_generator")
    return spaces


def index_embedding_space(index: str) -> IndexSpace:
    """The space ``index`` was built in; raises EmbeddingUnavailableError when it is not recorded."""
    space = index_spaces().get(index)
    if space is None:
        raise EmbeddingUnavailableError(f"index '{index}' has no recorded embedding space; search refused")
    if space.refusal:
        raise EmbeddingUnavailableError(f"index '{index}': search refused, {space.refusal}")
    return space


def require_query_dim(index: str, vector: object) -> None:
    """Refuse a query vector whose dimension is not the index's, before it is searched (#18217)."""
    space = index_embedding_space(index)
    got = int(np.asarray(vector).reshape(-1).shape[0])
    if got != space.dim:
        raise EmbeddingUnavailableError(f"query vector is {got}-d but index '{index}' is {space.dim}-d; refused")


async def embed_in_index_space(text: str, index: str) -> np.ndarray:
    """Embed ``text`` with the model ``index`` was built with, through the canonical accessor, or refuse."""
    from services.npu_client import generate_embedding_with_fallback

    space = index_embedding_space(index)
    if space.accessor != TEXT_ACCESSOR:
        raise ValueError(f"index '{index}' is embedded by {space.accessor}, not the text accessor")
    vector = await generate_embedding_with_fallback(text, model_name=space.model_id)
    if not vector:
        raise EmbeddingUnavailableError(f"model '{space.model_id}' of index '{index}' produced no vector; refused")
    require_query_dim(index, vector)
    return np.asarray(vector, dtype=np.float32)


class CollectionEmbeddingSpace:
    """Mixin for a class whose ``_collection_name`` is an index in the table: its model is the index's (#18143)."""

    _collection_name: str

    @property
    def _embedding_space(self) -> IndexSpace:
        return index_embedding_space(self._collection_name)
