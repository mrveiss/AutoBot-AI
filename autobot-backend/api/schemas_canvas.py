# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Pydantic request/response schemas for the Live Canvas API (MVA-359)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from canvas.models import CellType

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class CellOut(BaseModel):
    id: uuid.UUID
    position: int
    type: str
    content: str
    state: str
    owner: str
    version: int
    locked_by: str | None = None
    # Phase 2: null for Phase 1 / markdown / image cells (additive, non-breaking)
    rich_payload: Any | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CanvasOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    save_token: uuid.UUID
    undo_cursor: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GET /api/canvas/{id}
# ---------------------------------------------------------------------------


class CanvasGetResponse(BaseModel):
    canvas: CanvasOut
    cells: list[CellOut]


# ---------------------------------------------------------------------------
# PUT /api/canvas/{id}  — autosave
# ---------------------------------------------------------------------------


class CellAutosaveItem(BaseModel):
    id: uuid.UUID
    position: int
    content: str
    type: CellType = CellType.text


class CanvasPutRequest(BaseModel):
    title: str | None = None
    cells: list[CellAutosaveItem] = Field(default_factory=list)


class CanvasPutResponse(BaseModel):
    save_token: uuid.UUID
    saved_at: datetime


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/cells
# ---------------------------------------------------------------------------


class CellCreateRequest(BaseModel):
    type: CellType = CellType.text
    content: str = ""
    position: int = 0
    # Phase 2: optional rich payload for chart/code cells
    rich_payload: Any | None = None


# CellOut serves as the 201 response for cell creation.


# ---------------------------------------------------------------------------
# PATCH /api/canvas/{id}/cells/{cellId}
# ---------------------------------------------------------------------------


class CellTransitionRequest(BaseModel):
    action: str  # accept | edit | discard
    content: str | None = None  # required when action=edit
    # Phase 2: optional rich payload update during transition
    rich_payload: Any | None = None


class CellTransitionResponse(BaseModel):
    id: uuid.UUID
    state: str
    version: int
    content: str
    rich_payload: Any | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/export
# ---------------------------------------------------------------------------


class ExportInclude(BaseModel):
    agent: bool = True
    user: bool = True
    chat: bool = False


class CanvasExportRequest(BaseModel):
    format: str  # md | pdf | html | json
    include: ExportInclude = Field(default_factory=ExportInclude)
