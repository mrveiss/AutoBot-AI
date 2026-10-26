# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Response schemas for the embedding-model options (``GET /api/embeddings/models``, #19378)."""

from typing import List

from pydantic import BaseModel, Field


class EmbeddingModelOption(BaseModel):
    """One embedding model the user can switch to."""

    name: str
    provider: str | None = None
    available: bool
    active: bool
    # Unknown until the model has embedded once; the switch flow (#19379) learns it.
    dimension: int | None = None


class EmbeddingModelsData(BaseModel):
    """The embedding-model choices, with the active one marked and listed even when no provider reports it."""

    active: str
    models: List[EmbeddingModelOption]
    total_count: int
    providers_errored: List[str] = Field(default_factory=list)
