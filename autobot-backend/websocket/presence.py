# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Presence WebSocket Handler

Real-time presence tracking for multi-user sessions.
Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class PresenceManager:
    """
    Manage real-time presence for session collaboration.

    Tracks connected users per session and broadcasts join/leave events.
    """

    def __init__(self):
        """Initialize presence manager."""
        # session_id -> {user_id -> set of WebSocket connections}
        self._sessions: Dict[str, Dict[str, Set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )

        # WebSocket -> (session_id, user_id) for cleanup
        self._connection_map: Dict[WebSocket, tuple] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(
        self, session_id: str, user_id: str, websocket: WebSocket
    ) -> None:
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
                    "timestamp": datetime.utcnow().isoformat(),
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

                        logger.info(
                            f"User {user_id} fully disconnected "
                            f"from session {session_id}"
                        )

                        # Broadcast leave event
                        await self._broadcast_event(
                            session_id,
                            {
                                "type": "user_left",
                                "user_id": user_id,
                                "timestamp": datetime.utcnow().isoformat(),
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
        # Register connection
        await presence_manager.connect(session_id, user_id, websocket)

        # Send current online users
        online_users = await presence_manager.get_online_users(session_id)
        await websocket.send_json(
            {
                "type": "presence_sync",
                "online_users": online_users,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle ping/pong for keep-alive
                if message.get("type") == "ping":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue

                # Broadcast custom messages to session
                if message.get("type") == "broadcast":
                    payload = message.get("payload", {})
                    await presence_manager.broadcast_to_session(
                        session_id,
                        {
                            "type": "user_message",
                            "user_id": user_id,
                            "payload": payload,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

            except WebSocketDisconnect:
                logger.info(
                    f"WebSocket disconnected for user {user_id} "
                    f"in session {session_id}"
                )
                break
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from client: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
    finally:
        # Unregister connection
        await presence_manager.disconnect(websocket)
