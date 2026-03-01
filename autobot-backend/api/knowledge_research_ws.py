# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Knowledge Research WebSocket API.

Streams live research progress events from the LibrarianAssistant to the
frontend KnowledgeResearchPanel while the agent browses the web on .25.

WebSocket endpoint: /api/ws/knowledge/research

Client sends:
    {"action": "start", "query": "..."}

Server streams:
    {"event": "research:started",          "query": "..."}
    {"event": "research:searching",        "engine": "...", "query": "..."}
    {"event": "research:result_found",     "url": "...", "title": "...", "snippet": "..."}
    {"event": "research:content_extracted","url": "...", "content_preview": "..."}
    {"event": "research:quality_assessed", "url": "...", "score": 0.85, "domain": "..."}
    {"event": "research:stored",           "url": "...", "status": "verified|pending_review"}
    {"event": "research:completed",        "total_found": 5, "stored": 3}
    {"event": "research:error",            "message": "..."}
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)
router = APIRouter()


async def _send_event(websocket: WebSocket, event: Dict[str, Any]) -> bool:
    """Send a JSON event to the WebSocket client.

    Returns True on success, False if the connection is closed. Issue #1256.
    """
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_text(json.dumps(event))
        return True
    except Exception as exc:
        logger.warning("Failed to send WS event %s: %s", event.get("event"), exc)
        return False


def _make_callback(
    websocket: WebSocket,
) -> Callable[[Dict[str, Any]], Any]:
    """Return an async progress callback for LibrarianAssistant._emit.

    LibrarianAssistant._emit calls ``await callback(event)``, so this must
    return a coroutine function. Issue #1256.
    """

    async def callback(event: Dict[str, Any]) -> None:
        await _send_event(websocket, event)

    return callback


async def _run_research(
    websocket: WebSocket,
    query: str,
    store_quality: bool,
) -> None:
    """Execute research query and stream events back to client. Issue #1256."""
    progress_callback = _make_callback(websocket)

    await _send_event(websocket, {"event": "research:started", "query": query})

    try:
        from agents.librarian_assistant import get_librarian_assistant

        librarian = get_librarian_assistant()
        results = await librarian.research_query(
            query=query,
            store_quality_content=store_quality,
            progress_callback=progress_callback,
        )

        total_found = len(results.get("search_results", []))
        stored_count = len(results.get("stored_in_kb", []))

        await _send_event(
            websocket,
            {
                "event": "research:completed",
                "total_found": total_found,
                "stored": stored_count,
                "summary": results.get("summary", ""),
            },
        )
    except Exception as exc:
        logger.error("Research WS error for query %r: %s", query, exc)
        await _send_event(
            websocket,
            {"event": "research:error", "message": str(exc)},
        )


def _parse_client_message(raw: str) -> Optional[Dict[str, Any]]:
    """Parse and validate a client message. Returns None on error. Issue #1256."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from research WS client: %s", exc)
        return None


@router.websocket("/ws/knowledge/research")
async def knowledge_research_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint that streams live research progress.

    Protocol:
        1. Client connects.
        2. Client sends {"action": "start", "query": "...", "store": true}.
        3. Server streams research:* events as research progresses.
        4. Server sends research:completed or research:error to finish.
        5. Either side may close the connection.

    Issue #1256: Observable Research Panel.
    """
    await websocket.accept()
    logger.info("Knowledge research WS connected from %s", websocket.client)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = _parse_client_message(raw)
            if msg is None:
                await _send_event(
                    websocket,
                    {"event": "research:error", "message": "Invalid JSON message"},
                )
                continue

            action = msg.get("action")
            if action != "start":
                await _send_event(
                    websocket,
                    {
                        "event": "research:error",
                        "message": f"Unknown action: {action!r}",
                    },
                )
                continue

            query = (msg.get("query") or "").strip()
            if not query:
                await _send_event(
                    websocket,
                    {"event": "research:error", "message": "Query must not be empty"},
                )
                continue

            store_quality = bool(msg.get("store", True))
            await _run_research(websocket, query, store_quality)

    except WebSocketDisconnect:
        logger.info("Knowledge research WS client disconnected")
    except Exception as exc:
        logger.error("Unexpected knowledge research WS error: %s", exc)
        await _send_event(
            websocket,
            {"event": "research:error", "message": "Internal server error"},
        )
