# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Live Events WebSocket API (#1408)

Scoped real-time event streaming with entity-level channel subscriptions.

Protocol:
  Connect:     wss://host/ws/live?token=<jwt>
  Subscribe:   {"action": "subscribe",   "channel": "task:abc123"}
  Unsubscribe: {"action": "unsubscribe", "channel": "task:abc123"}
  Ping:        {"action": "ping"}
  Server ack:  {"type": "subscribed",   "channel": "..."}
               {"type": "unsubscribed", "channel": "..."}
               {"type": "pong"}
               {"type": "error",        "message": "..."}
  Live event:  {"type": "live_event", "channel": "...", "event_type": "...",
                "event_id": <int>, "payload": {...}}
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from live_event_manager import live_event_manager
from starlette.websockets import WebSocketState

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter()

_PING_INTERVAL = 30  # seconds between server-side pings


def _verify_token(token: str) -> dict | None:
    """Verify JWT token; returns payload dict or None if invalid."""
    if not token:
        return None
    try:
        from auth_middleware import auth_middleware

        return auth_middleware.verify_jwt_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        return None


def _auth_required() -> bool:
    """Return True when JWT auth is enabled in app config."""
    try:
        from auth_middleware import auth_middleware

        return auth_middleware.enable_auth
    except Exception:
        return True


async def _send_error(ws: WebSocket, message: str) -> None:
    """Send an error frame to the client."""
    try:
        await ws.send_json({"type": "error", "message": message})
    except Exception:
        pass


async def _handle_subscribe(
    ws: WebSocket, channel: str, user_payload: dict | None
) -> None:
    """Process a subscribe action from the client."""
    if user_payload and channel.startswith("agent:"):
        claimed_id = channel.split(":", 1)[1]
        user_id = str(user_payload.get("user_id", ""))
        username = user_payload.get("username", "")
        is_admin = "admin" in user_payload.get("roles", [])
        if not is_admin and claimed_id not in (user_id, username):
            await _send_error(ws, f"Not authorized to subscribe to {channel}")
            return
    ok = await live_event_manager.subscribe(ws, channel)
    if ok:
        await ws.send_json({"type": "subscribed", "channel": channel})
    else:
        await _send_error(ws, f"Invalid channel: {channel}")


async def _handle_unsubscribe(ws: WebSocket, channel: str) -> None:
    """Process an unsubscribe action from the client."""
    await live_event_manager.unsubscribe(ws, channel)
    await ws.send_json({"type": "unsubscribed", "channel": channel})


async def _handle_message(ws: WebSocket, raw: str, user_payload: dict | None) -> None:
    """Parse and dispatch one incoming message."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await _send_error(ws, "Invalid JSON")
        return
    action = data.get("action")
    if action == "subscribe":
        await _handle_subscribe(ws, data.get("channel", ""), user_payload)
    elif action == "unsubscribe":
        await _handle_unsubscribe(ws, data.get("channel", ""))
    elif action == "ping":
        await ws.send_json({"type": "pong"})
    else:
        logger.debug("Unknown live-events action: %s", action)


async def _keepalive_loop(ws: WebSocket, stop_event: asyncio.Event) -> None:
    """Send periodic pings; terminate when stop_event is set."""
    while not stop_event.is_set():
        await asyncio.sleep(_PING_INTERVAL)
        if stop_event.is_set() or ws.client_state != WebSocketState.CONNECTED:
            break
        try:
            await ws.send_json({"type": "ping"})
        except Exception as exc:
            logger.debug("Keepalive send failed: %s", exc)
            break


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="live_events_websocket",
    error_code_prefix="LIVE_EVENTS",
)
@router.websocket("/ws/live")
async def live_events_endpoint(websocket: WebSocket):
    """WebSocket endpoint for scoped real-time event streaming (#1408)."""
    token = websocket.query_params.get("token", "")
    user_payload: dict | None = None
    if _auth_required():
        user_payload = _verify_token(token)
        if user_payload is None:
            await websocket.close(code=4001, reason="Unauthorized")
            logger.info("Live events WebSocket rejected: invalid token")
            return
    await websocket.accept()
    logger.info(
        "Live events WebSocket connected: %s (user=%s)",
        websocket.client,
        user_payload.get("username") if user_payload else "anon",
    )
    await websocket.send_json(
        {
            "type": "connection_established",
            "message": "Connected. Send subscribe actions to receive events.",
        }
    )
    stop_event = asyncio.Event()
    keepalive_task = asyncio.create_task(_keepalive_loop(websocket, stop_event))
    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("Live events WebSocket disconnected cleanly")
                break
            except Exception as exc:
                msg = str(exc).lower()
                if "connection" in msg or "closed" in msg or "disconnect" in msg:
                    logger.info("Live events WebSocket connection lost: %s", exc)
                else:
                    logger.error("Live events WebSocket receive error: %s", exc)
                break
            await _handle_message(websocket, raw, user_payload)
    finally:
        stop_event.set()
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        await live_event_manager.remove_client(websocket)
        logger.info("Live events WebSocket connection cleaned up")
