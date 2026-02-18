# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WebSocket Channel Adapter

Issue #732: Unified Gateway for multi-channel communication.
Adapts WebSocket connections to the unified Gateway message format.
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from ..types import ChannelType, GatewaySession, MessageType, UnifiedMessage
from .base import BaseChannelAdapter

logger = logging.getLogger(__name__)


class WebSocketAdapter(BaseChannelAdapter):
    """
    WebSocket channel adapter.

    Translates between WebSocket messages and unified Gateway messages.
    """

    def __init__(self):
        """Initialize WebSocket adapter."""
        super().__init__(ChannelType.WEBSOCKET)

    async def send_message(
        self,
        message: UnifiedMessage,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> bool:
        """
        Send message through WebSocket.

        Args:
            message: Unified message to send
            session: Session associated with message
            connection_context: WebSocket connection

        Returns:
            True if sent successfully
        """
        if not isinstance(connection_context, WebSocket):
            logger.error("Invalid connection context for WebSocket")
            return False

        websocket: WebSocket = connection_context

        # Check connection state
        if websocket.client_state != WebSocketState.CONNECTED:
            logger.warning("WebSocket not connected")
            return False

        try:
            # Convert to WebSocket format
            ws_message = self._to_websocket_format(message)

            # Send as JSON
            await websocket.send_json(ws_message)
            return True

        except Exception as e:
            logger.error("Error sending WebSocket message: %s", e, exc_info=True)
            return False

    async def receive_message(
        self,
        raw_data: Any,
        session: GatewaySession,
    ) -> Optional[UnifiedMessage]:
        """
        Receive and parse WebSocket message.

        Args:
            raw_data: Raw WebSocket data (dict or str)
            session: Session receiving the message

        Returns:
            Parsed UnifiedMessage or None
        """
        try:
            # Parse JSON if string
            if isinstance(raw_data, str):
                data = json.loads(raw_data)
            elif isinstance(raw_data, dict):
                data = raw_data
            else:
                logger.warning("Invalid WebSocket message format: %s", type(raw_data))
                return None

            # Convert from WebSocket format
            return self._from_websocket_format(data, session)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse WebSocket JSON: %s", e)
            return None
        except Exception as e:
            logger.error("Error receiving WebSocket message: %s", e, exc_info=True)
            return None

    async def connect(
        self,
        session: GatewaySession,
        connection_params: Dict[str, Any],
    ) -> Any:
        """
        Accept WebSocket connection.

        Args:
            session: Session to connect
            connection_params: Must contain 'websocket' key with WebSocket instance

        Returns:
            WebSocket connection object
        """
        websocket = connection_params.get("websocket")
        if not isinstance(websocket, WebSocket):
            raise ValueError("connection_params must contain 'websocket' key")

        # Accept connection
        await websocket.accept()

        logger.info("WebSocket connected for session %s", session.session_id)

        return websocket

    async def disconnect(
        self,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> None:
        """
        Close WebSocket connection.

        Args:
            session: Session to disconnect
            connection_context: WebSocket connection
        """
        if not isinstance(connection_context, WebSocket):
            return

        websocket: WebSocket = connection_context

        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
                logger.info("WebSocket disconnected for session %s", session.session_id)
        except Exception as e:
            logger.error("Error closing WebSocket: %s", e, exc_info=True)

    async def handle_heartbeat(
        self,
        session: GatewaySession,
        connection_context: Optional[Any] = None,
    ) -> bool:
        """
        Send WebSocket heartbeat/ping.

        Args:
            session: Session to send heartbeat for
            connection_context: WebSocket connection

        Returns:
            True if connection alive
        """
        if not isinstance(connection_context, WebSocket):
            return False

        websocket: WebSocket = connection_context

        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                # Send ping (WebSocket protocol handles this automatically)
                heartbeat_msg = UnifiedMessage(
                    session_id=session.session_id,
                    channel=ChannelType.WEBSOCKET,
                    message_type=MessageType.SESSION_HEARTBEAT,
                    content={"status": "alive"},
                )
                return await self.send_message(heartbeat_msg, session, websocket)
            return False

        except Exception as e:
            logger.error("Heartbeat failed: %s", e)
            return False

    def _to_websocket_format(self, message: UnifiedMessage) -> Dict[str, Any]:
        """
        Convert UnifiedMessage to WebSocket format.

        Args:
            message: Unified message

        Returns:
            WebSocket-compatible dictionary
        """
        # Map MessageType to legacy WebSocket event types
        event_type_map = {
            MessageType.USER_TEXT: "user_message",
            MessageType.AGENT_TEXT: "llm_response",
            MessageType.AGENT_THOUGHT: "thought",
            MessageType.AGENT_TOOL_CODE: "tool_code",
            MessageType.AGENT_TOOL_OUTPUT: "tool_output",
            MessageType.SYSTEM_STATUS: "progress",
            MessageType.SYSTEM_ERROR: "error",
            MessageType.SYSTEM_PROGRESS: "progress",
            MessageType.SESSION_START: "session_start",
            MessageType.SESSION_END: "session_end",
            MessageType.SESSION_HEARTBEAT: "heartbeat",
        }

        event_type = event_type_map.get(message.message_type, "message")

        # Format content based on type
        data = (
            message.content
            if isinstance(message.content, dict)
            else {"content": message.content}
        )

        return {
            "type": event_type,
            "data": data,
            "message_id": message.message_id,
            "timestamp": message.created_at.isoformat(),
            "metadata": message.metadata,
        }

    def _from_websocket_format(
        self,
        data: Dict[str, Any],
        session: GatewaySession,
    ) -> UnifiedMessage:
        """
        Convert WebSocket message to UnifiedMessage.

        Args:
            data: WebSocket message data
            session: Associated session

        Returns:
            UnifiedMessage
        """
        # Map legacy WebSocket event types to MessageType
        type_map = {
            "user_message": MessageType.USER_TEXT,
            "message": MessageType.USER_TEXT,
            "voice": MessageType.USER_VOICE,
            "image": MessageType.USER_IMAGE,
            "file": MessageType.USER_FILE,
        }

        ws_type = data.get("type", "message")
        message_type = type_map.get(ws_type, MessageType.USER_TEXT)

        # Extract content
        content = data.get("data") or data.get("content") or data.get("message", "")

        return UnifiedMessage(
            session_id=session.session_id,
            channel=ChannelType.WEBSOCKET,
            message_type=message_type,
            content=content,
            metadata=data.get("metadata", {}),
        )
