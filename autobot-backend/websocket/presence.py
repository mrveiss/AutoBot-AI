# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session Presence WebSocket Handler

Real-time presence tracking for multi-user sessions.
Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

import asyncio
import json
import uuid
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.exc import SQLAlchemyError

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from models.collaboration_event import CollaborationEvent
from user_management.database import get_async_session_factory

logger = get_logger(__name__)


class PresenceManager:
    """
    Manage real-time presence for session collaboration.

    Tracks connected users per session and broadcasts join/leave events.
    """

    def __init__(self):
        """Initialize presence manager."""
        # session_id -> {user_id -> set of WebSocket connections}
        self._sessions: Dict[str, Dict[str, Set[WebSocket]]] = defaultdict(lambda: defaultdict(set))

        # WebSocket -> (session_id, user_id) for cleanup
        self._connection_map: Dict[WebSocket, tuple] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, user_id: str, websocket: WebSocket) -> None:
        """
        Register user connection to session.

        Args:
            session_id: Session identifier
            user_id: User identifier
            websocket: WebSocket connection
        """
        async with self._lock:
            # Track connection
            self._sessions[session_id][user_id].add(websocket)
            self._connection_map[websocket] = (session_id, user_id)

            logger.info(
                f"User {user_id} connected to session {session_id} "
                f"(total: {len(self._sessions[session_id][user_id])})"
            )

            # Broadcast join event to other participants
            await self._broadcast_event(
                session_id,
                {
                    "type": "user_joined",
                    "user_id": user_id,
                    "timestamp": utc_timestamp(),
                },
                exclude=websocket,
            )

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Unregister user connection.

        Args:
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            # Get session and user from connection map
            if websocket not in self._connection_map:
                return

            session_id, user_id = self._connection_map.pop(websocket)

            # Remove connection
            if session_id in self._sessions:
                if user_id in self._sessions[session_id]:
                    self._sessions[session_id][user_id].discard(websocket)

                    # If user has no more connections, remove user
                    if not self._sessions[session_id][user_id]:
                        del self._sessions[session_id][user_id]

                        logger.info(f"User {user_id} fully disconnected " f"from session {session_id}")

                        # Broadcast leave event
                        await self._broadcast_event(
                            session_id,
                            {
                                "type": "user_left",
                                "user_id": user_id,
                                "timestamp": utc_timestamp(),
                            },
                        )

                # Clean up empty session
                if not self._sessions[session_id]:
                    del self._sessions[session_id]

    async def get_online_users(self, session_id: str) -> List[str]:
        """
        Get list of online users in session.

        Args:
            session_id: Session identifier

        Returns:
            List of user IDs currently connected
        """
        async with self._lock:
            if session_id not in self._sessions:
                return []

            return list(self._sessions[session_id].keys())

    async def send_to_user(self, session_id: str, user_id: str, message: dict) -> int:
        """
        Send message to specific user in session.

        Args:
            session_id: Session identifier
            user_id: Target user identifier
            message: Message dictionary to send

        Returns:
            Number of connections message was sent to
        """
        async with self._lock:
            if session_id not in self._sessions:
                return 0

            if user_id not in self._sessions[session_id]:
                return 0

            connections = self._sessions[session_id][user_id]
            message_json = json.dumps(message)
            sent_count = 0

            for ws in connections:
                try:
                    await ws.send_text(message_json)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")

            return sent_count

    async def _broadcast_event(
        self,
        session_id: str,
        message: dict,
        exclude: WebSocket = None,
    ) -> int:
        """
        Broadcast message to all session participants.

        Args:
            session_id: Session identifier
            message: Message dictionary to broadcast
            exclude: Optional WebSocket to exclude from broadcast

        Returns:
            Number of connections message was sent to
        """
        if session_id not in self._sessions:
            return 0

        message_json = json.dumps(message)
        sent_count = 0

        for user_id, connections in self._sessions[session_id].items():
            for ws in connections:
                if ws == exclude:
                    continue

                try:
                    await ws.send_text(message_json)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to broadcast to {user_id}: {e}")

        return sent_count

    async def broadcast_to_session(self, session_id: str, message: dict) -> int:
        """
        Broadcast message to all users in session.

        Args:
            session_id: Session identifier
            message: Message to broadcast

        Returns:
            Number of connections reached
        """
        async with self._lock:
            return await self._broadcast_event(session_id, message)


# Global presence manager instance
presence_manager = PresenceManager()


# ====================================================================
# WebSocket Endpoint Handler
# ====================================================================


async def _send_presence_sync(websocket: WebSocket, session_id: str) -> None:
    """Helper for presence_websocket_handler. Send initial online users list. Ref: #1088."""
    online_users = await presence_manager.get_online_users(session_id)
    await websocket.send_json(
        {
            "type": "presence_sync",
            "online_users": online_users,
            "timestamp": utc_timestamp(),
        }
    )


async def _persist_activity_event(session_id: str, user_id: str, payload: dict) -> None:
    """Best-effort persistence of a live 'activity' broadcast (#16460).

    Counterpart to api/collaboration.py's ``_record_event`` for the
    'secret_shared' kind: that one rides a REST call and already has a DB
    session, this one rides the generic broadcast relay and owns its own
    (matching api/presence_ws.py's ``_authorized_participant`` pattern for
    the same reason -- this module has no request-scoped session to borrow).
    A failure here must never break delivery to the other live participants.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        user_uuid = None

    try:
        session_factory = get_async_session_factory()
        async with session_factory() as db:
            db.add(
                CollaborationEvent(
                    session_id=session_id,
                    kind="activity",
                    user_id=user_uuid,
                    username=payload.get("username"),
                    payload=payload,
                )
            )
            await db.commit()
    except SQLAlchemyError as exc:
        logger.warning("collaboration activity persistence failed: %s", type(exc).__name__)


async def _handle_presence_message(
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    message: dict,
) -> bool:
    """Helper for presence_websocket_handler. Handle one inbound message. Ref: #1088.

    Returns True to continue the loop, False to break out.
    """
    if message.get("type") == "ping":
        await websocket.send_json({"type": "pong", "timestamp": utc_timestamp()})
        return True
    if message.get("type") == "broadcast":
        payload = message.get("payload", {})
        if isinstance(payload, dict) and payload.get("kind") == "activity":
            await _persist_activity_event(session_id, user_id, payload)
        await presence_manager.broadcast_to_session(
            session_id,
            {
                "type": "user_message",
                "user_id": user_id,
                "payload": payload,
                "timestamp": utc_timestamp(),
            },
        )
    return True


async def _presence_message_loop(websocket: WebSocket, session_id: str, user_id: str) -> None:
    """Helper for presence_websocket_handler. Run the receive-dispatch loop. Ref: #1088."""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
            if not await _handle_presence_message(websocket, session_id, user_id, message):
                break
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user_id} in session {session_id}")
            break
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from client: {e}")
            await websocket.send_json({"type": "error", "message": "Invalid JSON"})
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            break


async def presence_websocket_handler(
    websocket: WebSocket,
    session_id: str,
    user_id: str,
) -> None:
    """
    WebSocket handler for session presence.

    Args:
        websocket: WebSocket connection
        session_id: Session identifier
        user_id: User identifier
    """
    await websocket.accept()
    try:
        await presence_manager.connect(session_id, user_id, websocket)
        await _send_presence_sync(websocket, session_id)
        await _presence_message_loop(websocket, session_id, user_id)
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
    finally:
        await presence_manager.disconnect(websocket)
