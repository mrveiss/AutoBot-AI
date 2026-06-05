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

import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
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
from canvas.vega_validation import validate_vegalite_spec
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

# CSP for the canvas page (MVA-486 §2.3/§3.1).
# Allows Vega SVG inline styles + data-URI images; blocks scripts, eval,
# and all external network fetches (preventing data.url exfiltration at browser level).
_CANVAS_PAGE_CSP = "default-src 'none'; " "style-src 'unsafe-inline'; " "img-src data:; " "font-src data:"


def _user_id(current_user: dict) -> str:
    """Extract stable user identifier from JWT dict."""
    return current_user.get("user_id") or current_user.get("id") or current_user.get("username", "")


def _validate_and_sanitize_rich_payload(rich_payload: dict | None, cell_type: str) -> dict | None:
    """
    Validate and sanitize a rich payload.  Returns the sanitized payload or None.

    Rules (Phase 2):
    - chart cells: richPayload must have payloadType='vega-lite', specVersion='5',
      and spec that passes Vega-Lite v5 validation.
    - code cells: richPayload must have payloadType='code'; executable must be false.
    - executable: true is always rejected.
    """
    if rich_payload is None:
        return None
    if not isinstance(rich_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="richPayload must be a JSON object or null.",
        )

    payload_type = rich_payload.get("payloadType")

    # executable: true is forbidden in Phase 2
    if rich_payload.get("executable") is True:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="executable: true is not supported until Phase 3.",
        )

    if cell_type == "chart":
        if payload_type != "vega-lite":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="chart cells require richPayload.payloadType='vega-lite'.",
            )
        if rich_payload.get("specVersion") != "5":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="chart cells require richPayload.specVersion='5' (Vega-Lite v5).",
            )
        try:
            sanitized_spec = validate_vegalite_spec(rich_payload.get("spec"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Internal server error",
            ) from exc
        return {**rich_payload, "spec": sanitized_spec, "executable": False}

    if cell_type == "code":
        if payload_type != "code":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="code cells require richPayload.payloadType='code'.",
            )
        # Force executable: false
        return {**rich_payload, "executable": False}

    # For text/image cells, richPayload is ignored (Phase 1 compatibility)
    return None


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
    response: Response,
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

        response.headers["Content-Security-Policy"] = _CANVAS_PAGE_CSP

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

            if 'title' in body.model_fields_set:
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

        rich_payload = _validate_and_sanitize_rich_payload(body.rich_payload, body.type)

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
            rich_payload=rich_payload,
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

        target_state = _ACTION_TO_TARGET_STATE[body.action]

        # Enforce the state machine: committed is terminal, only complete allows transitions
        if target_state not in _VALID_TRANSITIONS.get(cell.state, set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition cell from state '{cell.state}' with action '{body.action}'.",
            )
        now = datetime.now(tz=timezone.utc)

        cell.state = target_state
        cell.version = cell.version + 1
        cell.updated_at = now
        if body.action == "edit" and body.content is not None:
            cell.content = body.content
        # Phase 2: allow rich_payload update on edit/accept
        if body.rich_payload is not None and body.action in ("edit", "accept"):
            cell.rich_payload = _validate_and_sanitize_rich_payload(body.rich_payload, cell.type)

        await session.commit()
        await session.refresh(cell)

        metric_key = "canvas.draft.accepted" if body.action in ("accept", "edit") else "canvas.draft.discarded"
        _log_metric(metric_key, canvas_id=str(canvas_id), cell_id=str(cell_id))

        return CellTransitionResponse(
            id=cell.id,
            state=cell.state,
            version=cell.version,
            content=cell.content,
            rich_payload=cell.rich_payload,
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
            elif body.format in ("html", "pdf"):
                # Pre-render chart cells to SVG for server-side embed
                chart_svgs = await _render_chart_svgs(filtered)
                data = _export_html(canvas, filtered, chart_svgs=chart_svgs)
                if body.format == "html":
                    payload = data.encode("utf-8")
                else:
                    payload = _export_pdf_from_html(data)
        except HTTPException:
            raise
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
        if cell.type == "chart" and cell.rich_payload:
            spec = cell.rich_payload.get("spec", {})
            description = spec.get("description", "Chart")
            lines += [f"**{description}**", ""]
            # Emit data as a Markdown table if values are simple dicts
            data_values = spec.get("data", {}).get("values", [])
            if data_values and isinstance(data_values[0], dict):
                headers = list(data_values[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for row in data_values:
                    lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
                lines.append("")
        elif cell.type == "code":
            if cell.rich_payload:
                lang = cell.rich_payload.get("language") or ""
                code = cell.rich_payload.get("content", cell.content)
            else:
                lang, code = "", cell.content
            lines += [f"```{lang}\n{code}\n```", ""]
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
                    "rich_payload": c.rich_payload,
                }
                for c in cells
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _export_html(
    canvas: Canvas,
    cells: list[CanvasCell],
    chart_svgs: dict[str, str] | None = None,
) -> str:
    """Sanitize each cell's content before embedding in HTML (XSS/injection surface).

    chart_svgs: optional map of cell id → pre-rendered SVG string for chart cells.
    """
    try:
        import bleach

        def _sanitize(text: str) -> str:
            return bleach.clean(text, tags=[], strip=True)

    except ImportError:
        # Fallback: basic escaping without bleach
        import html as html_lib

        def _sanitize(text: str) -> str:  # type: ignore[misc]
            return html_lib.escape(text)

    chart_svgs = chart_svgs or {}
    title_safe = _sanitize(canvas.title)
    rows = []
    for cell in cells:
        if cell.type == "chart":
            svg = chart_svgs.get(str(cell.id))
            if svg:
                # SVG is server-rendered; no user-controlled HTML injected
                rows.append(
                    f'<div class="canvas-cell canvas-cell--chart" data-state="{cell.state}" data-owner="{cell.owner}">'
                    f"{svg}"
                    f"</div>"
                )
            else:
                spec = (cell.rich_payload or {}).get("spec", {})
                desc = _sanitize(spec.get("description", "Chart unavailable"))
                rows.append(
                    f'<div class="canvas-cell canvas-cell--chart" data-state="{cell.state}" data-owner="{cell.owner}">'
                    f"<p><em>{desc}</em></p>"
                    f"</div>"
                )
        elif cell.type == "code":
            if cell.rich_payload:
                lang = _sanitize(cell.rich_payload.get("language") or "")
                code_safe = _sanitize(cell.rich_payload.get("content", cell.content))
            else:
                lang, code_safe = "", _sanitize(cell.content)
            rows.append(
                f'<div class="canvas-cell canvas-cell--code" data-state="{cell.state}" data-owner="{cell.owner}">'
                f'<pre><code class="language-{lang}">{code_safe}</code></pre>'
                f"</div>"
            )
        else:
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
        f'<meta http-equiv="Content-Security-Policy" content="{_CANVAS_PAGE_CSP}">'
        f"<title>{title_safe}</title>"
        "</head>"
        f"<body><h1>{title_safe}</h1>{cells_html}</body>"
        "</html>"
    )


async def _render_chart_svgs(cells: list[CanvasCell]) -> dict[str, str]:
    """Render all chart cells to SVG concurrently. Returns cell-id → SVG map."""
    from canvas.vega_render import VegaRenderError, render_vegalite_to_svg

    chart_cells = [c for c in cells if c.type == "chart" and c.rich_payload]
    if not chart_cells:
        return {}

    async def _render_one(cell: CanvasCell) -> tuple[str, str | None]:
        spec = cell.rich_payload.get("spec", {})
        try:
            svg = await render_vegalite_to_svg(spec)
            return str(cell.id), svg
        except VegaRenderError as exc:
            logger.warning("canvas.export.chart_render_failed", cell_id=str(cell.id), error=str(exc))
            return str(cell.id), None

    results = await asyncio.gather(*(_render_one(c) for c in chart_cells))
    return {cid: svg for cid, svg in results if svg is not None}


def _export_pdf_from_html(html_content: str) -> bytes:
    """Render HTML (with embedded SVGs) to PDF. Requires weasyprint."""
    try:
        from weasyprint import HTML

        return HTML(string=html_content).write_pdf()
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF export requires weasyprint. Install it to enable PDF generation.",
        ) from exc
