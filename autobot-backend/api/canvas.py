"""
Live Canvas REST API (MVA-359).

Endpoints (frozen contract — breaking changes require a new ADR):
  GET    /api/canvas/{id}           — fetch canvas + ordered cells + undo cursor
  PUT    /api/canvas/{id}           — autosave (debounced, optimistic)
  POST   /api/canvas/{id}/cells     — add user-owned cell
  PATCH  /api/canvas/{id}/cells/{cellId} — accept | edit | discard (state transition)
  POST   /api/canvas/{id}/export    — generate md/json/html/pdf export

Per-user authz on every endpoint: canvas.user_id == JWT subject (403 otherwise).
Trust contract enforced server-side: agent cells never reach 'committed' without
an explicit user action.

Observability: OTel spans + structlog metrics via autobot_shared.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_canvas import (
    CanvasExportRequest,
    CanvasGetResponse,
    CanvasOut,
    CanvasPutRequest,
    CanvasPutResponse,
    CellCreateRequest,
    CellOut,
    CellTransitionRequest,
    CellTransitionResponse,
)
from auth_middleware import get_current_user
from autobot_shared.tracing import get_tracer
from canvas.models import Canvas, CanvasCell, CellState
from user_management.database import get_async_session

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)

router = APIRouter(prefix="/canvas", tags=["canvas"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    CellState.queued: {CellState.skeleton},
    CellState.skeleton: {CellState.streaming, CellState.error, CellState.cancelled},
    CellState.streaming: {CellState.complete, CellState.error, CellState.cancelled},
    CellState.complete: {CellState.committed, CellState.error, CellState.cancelled},
    CellState.committed: set(),
    CellState.error: set(),
    CellState.cancelled: set(),
}

_ACTION_TO_TARGET_STATE: dict[str, str] = {
    "accept": CellState.committed,
    "edit": CellState.committed,
    "discard": CellState.cancelled,
}

_EXPORT_CONTENT_TYPES: dict[str, str] = {
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
}


def _user_id(current_user: dict) -> str:
    """Extract stable user identifier from JWT dict."""
    return current_user.get("user_id") or current_user.get("id") or current_user.get("username", "")


def _log_metric(event: str, **kw) -> None:
    logger.info(event, **kw)


async def _get_canvas_owned(
    canvas_id: uuid.UUID,
    user_id: str,
    session: AsyncSession,
) -> Canvas:
    """Fetch canvas and verify ownership. Raises 404/403 as appropriate."""
    result = await session.execute(select(Canvas).where(Canvas.id == canvas_id))
    canvas = result.scalar_one_or_none()
    if canvas is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canvas not found")
    if canvas.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return canvas


async def _get_cell_owned(
    cell_id: uuid.UUID,
    canvas_id: uuid.UUID,
    user_id: str,
    session: AsyncSession,
) -> CanvasCell:
    result = await session.execute(
        select(CanvasCell).where(CanvasCell.id == cell_id, CanvasCell.canvas_id == canvas_id)
    )
    cell = result.scalar_one_or_none()
    if cell is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    if cell.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return cell


# ---------------------------------------------------------------------------
# GET /api/canvas/{id}
# ---------------------------------------------------------------------------


@router.get("/{canvas_id}", response_model=CanvasGetResponse)
async def get_canvas(
    canvas_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CanvasGetResponse:
    """Return canvas + ordered cells + undo cursor."""
    with tracer.start_as_current_span("canvas.get") as span:
        uid = _user_id(current_user)
        span.set_attribute("canvas_id", str(canvas_id))
        span.set_attribute("user_id", uid)

        canvas = await _get_canvas_owned(canvas_id, uid, session)

        cells_result = await session.execute(
            select(CanvasCell).where(CanvasCell.canvas_id == canvas_id).order_by(CanvasCell.position)
        )
        cells = cells_result.scalars().all()

        return CanvasGetResponse(
            canvas=CanvasOut.model_validate(canvas),
            cells=[CellOut.model_validate(c) for c in cells],
        )


# ---------------------------------------------------------------------------
# PUT /api/canvas/{id} — autosave
# ---------------------------------------------------------------------------


@router.put("/{canvas_id}", response_model=CanvasPutResponse)
async def put_canvas(
    canvas_id: uuid.UUID,
    body: CanvasPutRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CanvasPutResponse:
    """Autosave canvas state. Returns new save_token + timestamp."""
    with tracer.start_as_current_span("canvas.put") as span:
        uid = _user_id(current_user)
        span.set_attribute("canvas_id", str(canvas_id))
        span.set_attribute("user_id", uid)

        try:
            canvas = await _get_canvas_owned(canvas_id, uid, session)

            new_token = uuid.uuid4()
            now = datetime.now(tz=timezone.utc)

            if body.title is not None:
                canvas.title = body.title
            canvas.save_token = new_token
            canvas.updated_at = now

            # Upsert provided cells (position/content/type only — state unchanged)
            for item in body.cells:
                cell_result = await session.execute(
                    select(CanvasCell).where(
                        CanvasCell.id == item.id,
                        CanvasCell.canvas_id == canvas_id,
                    )
                )
                cell = cell_result.scalar_one_or_none()
                if cell and cell.user_id == uid:
                    cell.position = item.position
                    cell.content = item.content
                    cell.type = item.type
                    cell.updated_at = now

            await session.commit()
            _log_metric("canvas.autosave.success", canvas_id=str(canvas_id))

            return CanvasPutResponse(save_token=new_token, saved_at=now)

        except HTTPException:
            _log_metric("canvas.autosave.failure", canvas_id=str(canvas_id))
            raise
        except Exception:
            _log_metric("canvas.autosave.failure", canvas_id=str(canvas_id))
            raise


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/cells — add user-owned cell
# ---------------------------------------------------------------------------


@router.post("/{canvas_id}/cells", response_model=CellOut, status_code=201)
async def add_cell(
    canvas_id: uuid.UUID,
    body: CellCreateRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CellOut:
    """Add a user-owned cell to the canvas. Cell starts in 'committed' state."""
    with tracer.start_as_current_span("canvas.cell.add") as span:
        uid = _user_id(current_user)
        span.set_attribute("canvas_id", str(canvas_id))

        await _get_canvas_owned(canvas_id, uid, session)

        cell = CanvasCell(
            id=uuid.uuid4(),
            canvas_id=canvas_id,
            user_id=uid,
            position=body.position,
            type=body.type,
            content=body.content,
            state=CellState.committed,
            owner="user",
            version=1,
            locked_by=None,
        )
        session.add(cell)
        await session.commit()
        await session.refresh(cell)

        return CellOut.model_validate(cell)


# ---------------------------------------------------------------------------
# PATCH /api/canvas/{id}/cells/{cellId} — state transition
# ---------------------------------------------------------------------------


@router.patch("/{canvas_id}/cells/{cell_id}", response_model=CellTransitionResponse)
async def transition_cell(
    canvas_id: uuid.UUID,
    cell_id: uuid.UUID,
    body: CellTransitionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> CellTransitionResponse:
    """
    State transition: accept | edit | discard.

    Trust contract (server-side): agent cells NEVER reach 'committed' without
    an explicit user action with action='accept' or action='edit'.
    """
    with tracer.start_as_current_span("canvas.cell.transition") as span:
        uid = _user_id(current_user)
        span.set_attribute("canvas_id", str(canvas_id))
        span.set_attribute("cell_id", str(cell_id))
        span.set_attribute("action", body.action)

        if body.action not in _ACTION_TO_TARGET_STATE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid action '{body.action}'. Must be accept, edit, or discard.",
            )

        if body.action == "edit" and body.content is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="content is required when action=edit",
            )

        await _get_canvas_owned(canvas_id, uid, session)
        cell = await _get_cell_owned(cell_id, canvas_id, uid, session)

        # State machine: complete → committed or cancelled only
        if cell.state not in (CellState.complete, CellState.committed):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cell in state '{cell.state}' cannot be accepted/edited/discarded.",
            )

        target_state = _ACTION_TO_TARGET_STATE[body.action]
        now = datetime.now(tz=timezone.utc)

        cell.state = target_state
        cell.version = cell.version + 1
        cell.updated_at = now
        if body.action == "edit" and body.content is not None:
            cell.content = body.content

        await session.commit()
        await session.refresh(cell)

        metric_key = "canvas.draft.accepted" if body.action in ("accept", "edit") else "canvas.draft.discarded"
        _log_metric(metric_key, canvas_id=str(canvas_id), cell_id=str(cell_id))

        return CellTransitionResponse(
            id=cell.id,
            state=cell.state,
            version=cell.version,
            content=cell.content,
            updated_at=cell.updated_at,
        )


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/export
# ---------------------------------------------------------------------------


@router.post("/{canvas_id}/export")
async def export_canvas(
    canvas_id: uuid.UUID,
    body: CanvasExportRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    """Generate export in the requested format with include-toggle filtering."""
    with tracer.start_as_current_span("canvas.export") as span:
        uid = _user_id(current_user)
        span.set_attribute("canvas_id", str(canvas_id))
        span.set_attribute("format", body.format)

        if body.format not in _EXPORT_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid format '{body.format}'. Must be md, pdf, html, or json.",
            )

        t_start = datetime.now(tz=timezone.utc)

        canvas = await _get_canvas_owned(canvas_id, uid, session)
        cells_result = await session.execute(
            select(CanvasCell).where(CanvasCell.canvas_id == canvas_id).order_by(CanvasCell.position)
        )
        all_cells = cells_result.scalars().all()

        # Apply include filters
        filtered = [
            c
            for c in all_cells
            if (c.owner == "agent" and body.include.agent) or (c.owner == "user" and body.include.user)
        ]

        content_type = _EXPORT_CONTENT_TYPES[body.format]

        try:
            if body.format == "md":
                data = _export_md(canvas, filtered)
                payload = data.encode("utf-8")
            elif body.format == "json":
                data = _export_json(canvas, filtered)
                payload = data.encode("utf-8")
            elif body.format == "html":
                data = _export_html(canvas, filtered)
                payload = data.encode("utf-8")
            elif body.format == "pdf":
                payload = _export_pdf(canvas, filtered)
        except Exception as exc:
            _log_metric("canvas.autosave.failure", canvas_id=str(canvas_id), format=body.format, error=str(exc))
            raise HTTPException(status_code=500, detail="Export generation failed") from exc

        latency = int((datetime.now(tz=timezone.utc) - t_start).total_seconds() * 1000)
        _log_metric(
            "canvas.export.success",
            canvas_id=str(canvas_id),
            format=body.format,
            latency_ms=latency,
            bytes=len(payload),
        )

        return Response(content=payload, media_type=content_type)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _export_md(canvas: Canvas, cells: list[CanvasCell]) -> str:
    lines = [f"# {canvas.title}", ""]
    for cell in cells:
        if cell.type == "code":
            lines += [f"```\n{cell.content}\n```", ""]
        else:
            lines += [cell.content, ""]
    return "\n".join(lines)


def _export_json(canvas: Canvas, cells: list[CanvasCell]) -> str:
    return json.dumps(
        {
            "canvas": {
                "id": str(canvas.id),
                "title": canvas.title,
                "created_at": canvas.created_at.isoformat(),
                "updated_at": canvas.updated_at.isoformat(),
            },
            "cells": [
                {
                    "id": str(c.id),
                    "position": c.position,
                    "type": c.type,
                    "content": c.content,
                    "state": c.state,
                    "owner": c.owner,
                    "version": c.version,
                }
                for c in cells
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _export_html(canvas: Canvas, cells: list[CanvasCell]) -> str:
    """Sanitize each cell's content before embedding in HTML (XSS/injection surface)."""
    try:
        import bleach

        def _sanitize(text: str) -> str:
            return bleach.clean(text, tags=[], strip=True)

    except ImportError:
        # Fallback: basic escaping without bleach
        import html as html_lib

        def _sanitize(text: str) -> str:  # type: ignore[misc]
            return html_lib.escape(text)

    title_safe = _sanitize(canvas.title)
    rows = []
    for cell in cells:
        content_safe = _sanitize(cell.content)
        rows.append(
            f'<div class="canvas-cell" data-state="{cell.state}" data-owner="{cell.owner}">'
            f"<pre>{content_safe}</pre>"
            f"</div>"
        )

    cells_html = "\n".join(rows)
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{title_safe}</title>"
        "</head>"
        f"<body><h1>{title_safe}</h1>{cells_html}</body>"
        "</html>"
    )


def _export_pdf(canvas: Canvas, cells: list[CanvasCell]) -> bytes:
    """Render sanitized HTML to PDF. Requires weasyprint."""
    html_content = _export_html(canvas, cells)
    try:
        from weasyprint import HTML

        return HTML(string=html_content).write_pdf()
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF export requires weasyprint. Install it to enable PDF generation.",
        ) from exc
