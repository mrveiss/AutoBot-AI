"""Pydantic request/response schemas for the Live Canvas API (MVA-359)."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
    locked_by: Optional[str] = None
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
    type: str = "text"


class CanvasPutRequest(BaseModel):
    title: Optional[str] = None
    cells: list[CellAutosaveItem] = Field(default_factory=list)


class CanvasPutResponse(BaseModel):
    save_token: uuid.UUID
    saved_at: datetime


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/cells
# ---------------------------------------------------------------------------


class CellCreateRequest(BaseModel):
    type: str = "text"
    content: str = ""
    position: int = 0


# CellOut serves as the 201 response for cell creation.


# ---------------------------------------------------------------------------
# PATCH /api/canvas/{id}/cells/{cellId}
# ---------------------------------------------------------------------------


class CellTransitionRequest(BaseModel):
    action: str  # accept | edit | discard
    content: Optional[str] = None  # required when action=edit


class CellTransitionResponse(BaseModel):
    id: uuid.UUID
    state: str
    version: int
    content: str
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
