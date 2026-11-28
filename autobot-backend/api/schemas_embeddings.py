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


class EmbeddingSwitchRequest(BaseModel):
    """Start an embedding-model switch (#19379): the model to rebuild the knowledge base with."""

    model: str = Field(min_length=1)


class EmbeddingSwitchData(BaseModel):
    """The current or last switch.

    ``state``: idle, building, settling, completed, completed_with_warnings, failed, cancelled, or
    stale (an active build whose heartbeat stopped). ``lock_unknown``: the claim registry could not
    be read, so an active state may be a build that has stopped. ``previous_vectors`` is the active collection's
    count when the build started; the rebuild writes one vector per fact.
    """

    state: str
    model: str | None = None
    collection: str | None = None
    done: int = 0
    total: int = 0
    failed: int = 0
    failed_ids: List[str] = Field(default_factory=list)
    previous_vectors: int | None = None
    reason: str | None = None
    started: str | None = None
    heartbeat: str | None = None
    finished: str | None = None
    lock_unknown: bool = False
