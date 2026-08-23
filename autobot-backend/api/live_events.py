# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Live Events WebSocket API (#1408)

Scoped real-time event streaming with entity-level channel subscriptions.

Protocol:
  Connect:     wss://host/ws/live?token=<jwt>
  Subscribe:   {"action": "subscribe",   "channel": "task:abc123"}
               {"action": "subscribe",   "channel": "chat:c1", "last_event_id": 42}
  Unsubscribe: {"action": "unsubscribe", "channel": "task:abc123"}
  Command:     {"action": "command", "channel": "operation:x", "command": "pause",
                "payload": {...}}
  Ping:        {"action": "ping"}
  Server ack:  {"type": "subscribed",   "channel": "...", "replayed": <int>}
               {"type": "unsubscribed", "channel": "..."}
               {"type": "resync",       "channel": "...", "reason": "..."}
               {"type": "command_result","channel": "...", "command": "...", "result": {...}}
               {"type": "pong"}
               {"type": "error",        "message": "..."}
  Live event:  {"type": "live_event", "channel": "...", "event_type": "...",
                "event_id": <int>, "payload": {...}}

Reconnect with replay (#14818): a client that tracks the highest ``event_id``
it has seen per channel may pass it back as ``last_event_id`` on subscribe.
The server replays what was missed before resuming live delivery.  When it
cannot produce a *complete* history — the marker has aged out of the retention
window, or the durable stream is unavailable — it sends ``resync`` instead of a
partial replay.  A partial history delivered as if it were whole is precisely
the silent data loss this protocol addition exists to prevent.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from api.ws_security import enforce_ws_origin
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from events.bus import get_event_bus
from events.channel_commands import CommandRefused, dispatch_command
from events.channel_stream import get_channel_event_stream
from services.workflow_permission_service import WorkflowPermissionService

logger = get_logger(__name__)
router = APIRouter()

_PING_INTERVAL = 30  # seconds between server-side pings


def _auth_required() -> bool:
    """Return True when JWT auth is enabled in app config."""
    try:
        from auth_middleware import get_auth_middleware

        return get_auth_middleware().enable_auth
    except Exception:
        return True


def _coerce_last_event_id(raw: object) -> int:
    """Return a usable ``last_event_id``, or 0 when absent or unusable.

    #14818: an unparseable marker must mean "replay nothing and start fresh",
    never a crash and never a silently trusted partial value.
    """
    if raw is None:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.debug("Ignoring non-integer last_event_id: %r", raw)
        return 0
    return value if value > 0 else 0


async def _authorize_conversation_channel(channel: str, user_payload: dict) -> bool:
    """Authorize ``session:``/``chat:`` subscriptions (#14819).

    Conversation channels carry a user's own messages, so this fails closed:
    admins bypass, the owner is allowed, everyone else is denied.  Ownership is
    resolved through the chat history manager, which is the store that knows
    which user a session belongs to.
    """
    if "admin" in user_payload.get("roles", []):
        return True
    # ``get_session_owner`` returns the *username* it stored in session
    # metadata, but a JWT may identify the caller by either field — compare
    # against both rather than guessing which one this deployment uses.
    identities = {str(value) for value in (user_payload.get("user_id"), user_payload.get("username")) if value}
    if not identities:
        return False
    _prefix, _, ident = channel.partition(":")
    if not ident:
        return False
    try:
        from utils.resource_factory import ResourceFactory

        manager = ResourceFactory.get_initialized_chat_history_manager()
        if manager is None:
            # No store to check against — deny rather than assume ownership.
            logger.warning("Conversation channel authz denied: chat history manager unavailable")
            return False
        owner = await manager.get_session_owner(ident)
        if owner is None:
            # Unknown or unowned conversation: deny non-admins rather than
            # treating "no record" as "no restriction" (#14819 fails closed).
            return False
        return str(owner) in identities
    except Exception:
        logger.exception("Conversation channel authorization failed for %s", channel)
        return False


async def _send_error(ws: WebSocket, message: str) -> None:
    """Send an error frame to the client."""
    try:
        await ws.send_json({"type": "error", "message": message})
    except Exception:
        pass


async def _authorize_llc_channel(channel: str, user_payload: dict) -> bool:
    """Authorize subscription to tenant-scoped LLC channels (``company:``/``board:``).

    These channels carry per-company data (activity audit rows, board moves), so a
    client may only subscribe to a company it belongs to. Admins bypass. Fails
    closed on any error (#11386 security review).
    """
    if "admin" in user_payload.get("roles", []):
        return True
    user_id = str(user_payload.get("user_id") or user_payload.get("username") or "")
    if not user_id:
        return False
    prefix, _, ident = channel.partition(":")
    if not ident:
        return False
    try:
        from llc.services.membership_service import MembershipService
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            company_id = ident
            if prefix == "board":
                from llc.services.board import BoardService

                board = await BoardService().get_board(session, ident)
                if board is None:
                    return False
                company_id = str(board.company_id)
            return await MembershipService().is_member(session, company_id, user_id)
    except Exception:
        logger.exception("LLC channel authorization failed for %s", channel)
        return False


async def _authorize_resource_channel(channel: str, user_payload: dict) -> bool:
    """Authorize ``workflow:``/``heartbeat:``/``task:`` subscriptions (#11396).

    These prefixes previously had NO tenant check — any authenticated user could
    subscribe to any id (cross-tenant leak, latent today since nothing publishes
    to them yet). Per-resource owner resolution, admins bypass, fails closed:

    - ``workflow:{id}`` — the caller must hold ``view`` permission on that
      workflow (``WorkflowPermissionService.check_permission``, viewer+).
    - ``heartbeat:{id}`` — resolve ``LLCHeartbeatRun.company_id`` and require
      company membership (mirrors the ``board:`` resolver).
    - ``task:{id}`` — no ownership store exists for task ids (and no publisher
      or frontend consumer today), so non-admins are DENIED until one does.
    """
    if "admin" in user_payload.get("roles", []):
        return True
    user_id = str(user_payload.get("user_id") or user_payload.get("username") or "")
    if not user_id:
        return False
    prefix, _, ident = channel.partition(":")
    if not ident:
        return False
    if prefix == "task":
        logger.warning("task-channel subscribe denied for %s: no task ownership store (#11396)", user_id)
        return False
    try:
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            if prefix == "workflow":
                svc = WorkflowPermissionService(session)
                return await svc.check_permission(user_id, ident, "view")
            if prefix == "heartbeat":
                from sqlalchemy import select

                from llc.models.heartbeat_run import LLCHeartbeatRun
                from llc.services.membership_service import MembershipService

                run = (
                    await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == ident))
                ).scalar_one_or_none()
                if run is None:
                    return False
                return await MembershipService().is_member(session, str(run.company_id), user_id)
    except Exception:
        logger.exception("Resource channel authorization failed for %s", channel)
        return False
    return False


async def _authorize_channel(channel: str, user_payload: dict | None) -> bool:
    """Single authorization rule for a channel, shared by subscribe and command.

    #14824: commands must not be able to reach a channel the caller could not
    subscribe to. Deriving both from this one function is what keeps the two
    paths from drifting — a second copy of the rules is how one of them ends up
    weaker than the other.
    """
    if not user_payload:
        return True
    if channel.startswith("agent:"):
        claimed_id = channel.split(":", 1)[1]
        user_id = str(user_payload.get("user_id", ""))
        username = user_payload.get("username", "")
        is_admin = "admin" in user_payload.get("roles", [])
        return is_admin or claimed_id in (user_id, username)
    if channel.startswith("company:") or channel.startswith("board:"):
        return await _authorize_llc_channel(channel, user_payload)
    if channel.startswith("session:") or channel.startswith("chat:"):
        return await _authorize_conversation_channel(channel, user_payload)
    if channel.startswith("workflow:") or channel.startswith("heartbeat:") or channel.startswith("task:"):
        return await _authorize_resource_channel(channel, user_payload)
    # ``global`` is the shared broadcast channel: every authenticated client is
    # meant to see it, and it carries no per-tenant payload of its own.
    if channel == "global":
        return True
    # Everything else is DENIED.  This used to `return True`, which was
    # survivable while the socket was subscribe-only — every valid prefix above
    # has an explicit rule, so nothing reached data unchecked. It stopped being
    # survivable when ``dispatch_command`` started using this same function as
    # the only gate on a *write* path: a handler registered for a new prefix
    # (``research:``, ``operation:``, ...) would have been reachable by any
    # connected client with no check at all. Defaulting to deny means a new
    # channel type is inert until someone writes its rule, which is the failure
    # direction we want.
    logger.warning("Denying unrecognised channel prefix: %s", channel)
    return False


async def _handle_command(
    ws: WebSocket,
    channel: str,
    command: str,
    payload: dict,
    user_payload: dict | None,
) -> None:
    """Route one client command to the handler registered for its channel (#14824)."""
    try:
        result = await dispatch_command(channel, command, payload, user_payload, _authorize_channel)
    except CommandRefused as refusal:
        await _send_error(ws, refusal.reason)
        return
    await ws.send_json(
        {
            "type": "command_result",
            "channel": channel,
            "command": command,
            "result": result or {},
        }
    )


async def _handle_subscribe(
    ws: WebSocket,
    channel: str,
    user_payload: dict | None,
    last_event_id: int = 0,
) -> None:
    """Process a subscribe action, optionally replaying from ``last_event_id`` (#14818)."""
    if user_payload and channel.startswith("agent:"):
        claimed_id = channel.split(":", 1)[1]
        user_id = str(user_payload.get("user_id", ""))
        username = user_payload.get("username", "")
        is_admin = "admin" in user_payload.get("roles", [])
        if not is_admin and claimed_id not in (user_id, username):
            await _send_error(ws, f"Not authorized to subscribe to {channel}")
            return
    elif user_payload and (channel.startswith("company:") or channel.startswith("board:")):
        # Tenant-scoped LLC channels: enforce company membership (#11386).
        if not await _authorize_llc_channel(channel, user_payload):
            await _send_error(ws, f"Not authorized to subscribe to {channel}")
            return
    elif user_payload and (channel.startswith("session:") or channel.startswith("chat:")):
        # #14819: conversation channels are per-user; without this branch any
        # authenticated caller could subscribe to anyone's conversation.
        if not await _authorize_conversation_channel(channel, user_payload):
            await _send_error(ws, f"Not authorized to subscribe to {channel}")
            return
    elif user_payload and (
        channel.startswith("workflow:") or channel.startswith("heartbeat:") or channel.startswith("task:")
    ):
        # Per-resource owner resolution for the remaining scoped prefixes (#11396).
        if not await _authorize_resource_channel(channel, user_payload):
            await _send_error(ws, f"Not authorized to subscribe to {channel}")
            return
    ok = await get_event_bus().subscribe_ws(ws, channel)
    if not ok:
        await _send_error(ws, f"Invalid channel: {channel}")
        return

    # #14818: subscribe first, then replay.  Doing it in this order means events
    # published *during* the replay are delivered live rather than falling into
    # a second gap between the replay read and the subscription taking effect.
    replayed = 0
    if last_event_id > 0:
        result = await get_channel_event_stream().replay_since(channel, last_event_id)
        if result.resync_required:
            await ws.send_json(
                {
                    "type": "resync",
                    "channel": channel,
                    "reason": result.reason or "unknown",
                }
            )
        else:
            for message in result.events:
                await ws.send_json(message)
            replayed = len(result.events)

    await ws.send_json({"type": "subscribed", "channel": channel, "replayed": replayed})


async def _handle_unsubscribe(ws: WebSocket, channel: str) -> None:
    """Process an unsubscribe action from the client."""
    await get_event_bus().unsubscribe_ws(ws, channel)
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
        await _handle_subscribe(
            ws,
            data.get("channel", ""),
            user_payload,
            _coerce_last_event_id(data.get("last_event_id")),
        )
    elif action == "unsubscribe":
        await _handle_unsubscribe(ws, data.get("channel", ""))
    elif action == "command":
        await _handle_command(
            ws,
            data.get("channel", ""),
            data.get("command", ""),
            data.get("payload") or {},
            user_payload,
        )
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


@router.websocket("/ws/live")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="live_events_websocket",
    error_code_prefix="LIVE_EVENTS",
)
async def live_events_endpoint(websocket: WebSocket):
    """WebSocket endpoint for scoped real-time event streaming (#1408)."""
    if not await enforce_ws_origin(websocket):
        return
    # #9963: use the canonical WS auth (JWT), same as /api/ws — the local
    # raw-JWT check was too strict and rejected valid deployments.
    from auth_middleware import authenticate_websocket

    user_payload: dict | None = await authenticate_websocket(websocket)
    if _auth_required() and user_payload is None:
        # accept() before close(4001) so clients see a clean close frame
        # instead of a handshake 403 (project WS rule).
        await websocket.accept()
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
        await get_event_bus().remove_client(websocket)
        logger.info("Live events WebSocket connection cleaned up")
