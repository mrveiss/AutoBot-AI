# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WhatsApp Channel Adapter

Issue #9007: WhatsApp Business API integration for bidirectional messaging.
Adapts WhatsApp webhook messages to the unified Gateway message format.
"""

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

from integrations.whatsapp_integration import WhatsAppIntegration
from ..types import ChannelType, GatewaySession, MessageType, UnifiedMessage
from .base import BaseChannelAdapter

logger = get_logger(__name__)


class WhatsAppAdapter(BaseChannelAdapter):
    """
    WhatsApp channel adapter.

    Translates between WhatsApp Business API messages and unified Gateway messages.
    Handles incoming webhooks and outgoing messages through WhatsAppIntegration.
    """

    def __init__(self, integration: WhatsAppIntegration) -> None:
        """
        Initialize WhatsApp adapter.

        Args:
            integration: WhatsAppIntegration instance for API calls
        """
        super().__init__(ChannelType.WHATSAPP)
        self.integration = integration

    async def send_message(
        self,
        message: UnifiedMessage,
        session: GatewaySession,
        connection_context: Any | None = None,
    ) -> bool:
        """
        Send message through WhatsApp.

        Args:
            message: Unified message to send
            session: Session associated with message
            connection_context: Dict with 'phone_number' key

        Returns:
            True if sent successfully
        """
        if not isinstance(connection_context, dict):
            logger.error("WhatsApp connection context must be dict with 'phone_number'")
            return False

        phone_number = connection_context.get("phone_number")
        if not phone_number:
            logger.error("WhatsApp connection context missing 'phone_number'")
            return False

        try:
            # Map message types to WhatsApp actions
            if message.message_type == MessageType.AGENT_TEXT:
                params = {
                    "to": phone_number,
                    "body": str(message.content),
                    "preview_url": message.metadata.get("preview_url", False),
                }
                result = await self.integration.send_text_message(params)
                return result.get("ok", False)

            elif message.message_type == MessageType.AGENT_TOOL_OUTPUT:
                # Send tool output as formatted text
                content = message.content
                if isinstance(content, dict):
                    formatted = f"```\n{content}\n```"
                else:
                    formatted = str(content)
                params = {"to": phone_number, "body": formatted}
                result = await self.integration.send_text_message(params)
                return result.get("ok", False)

            elif message.message_type == MessageType.SYSTEM_ERROR:
                # Send error message
                params = {
                    "to": phone_number,
                    "body": f"❌ Error: {message.content}",
                }
                result = await self.integration.send_text_message(params)
                return result.get("ok", False)

            else:
                logger.warning(
                    "Unsupported WhatsApp message type: %s", message.message_type
                )
                return False

        except Exception as e:
            logger.error("Error sending WhatsApp message: %s", e, exc_info=True)
            return False

    async def receive_message(
        self,
        raw_data: Any,
        session: GatewaySession,
    ) -> UnifiedMessage | None:
        """
        Receive and parse WhatsApp webhook message.

        Args:
            raw_data: WhatsApp webhook payload (dict)
            session: Session receiving the message

        Returns:
            Parsed UnifiedMessage or None

        WhatsApp webhook format:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "+1234567890",
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        """
        try:
            if not isinstance(raw_data, dict):
                logger.warning("Invalid WhatsApp webhook format: %s", type(raw_data))
                return None

            # Extract message from webhook structure
            entry = raw_data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])

            if not messages:
                logger.debug("No messages in WhatsApp webhook")
                return None

            msg_data = messages[0]
            msg_type = msg_data.get("type")
            sender = msg_data.get("from")
            msg_id = msg_data.get("id")

            # Map WhatsApp message types to Gateway types
            if msg_type == "text":
                content = msg_data.get("text", {}).get("body", "")
                message_type = MessageType.USER_TEXT

            elif msg_type == "image":
                content = msg_data.get("image", {})
                message_type = MessageType.USER_IMAGE

            elif msg_type == "audio":
                content = msg_data.get("audio", {})
                message_type = MessageType.USER_VOICE

            elif msg_type == "document":
                content = msg_data.get("document", {})
                message_type = MessageType.USER_FILE

            else:
                logger.warning("Unsupported WhatsApp message type: %s", msg_type)
                return None

            # Create unified message
            unified_msg = UnifiedMessage(
                message_id=msg_id or "",
                session_id=session.session_id,
                channel=ChannelType.WHATSAPP,
                message_type=message_type,
                content=content,
                metadata={
                    "from": sender,
                    "timestamp": msg_data.get("timestamp"),
                    "whatsapp_type": msg_type,
                },
            )

            # Mark message as read
            if msg_id:
                await self.integration.mark_message_read({"message_id": msg_id})

            return unified_msg

        except Exception as e:
            logger.error("Error parsing WhatsApp message: %s", e, exc_info=True)
            return None

    async def connect(
        self,
        session: GatewaySession,
        connection_params: Dict[str, Any],
    ) -> Any:
        """
        Establish WhatsApp connection (opt-in check).

        Args:
            session: Session to connect
            connection_params: Must include 'phone_number'

        Returns:
            Connection context dict with phone_number
        """
        phone_number = connection_params.get("phone_number")
        if not phone_number:
            raise ValueError("WhatsApp connection requires 'phone_number' parameter")

        # Check opt-in status
        opt_status = await self.integration.check_opt_in_status(
            {"phone_number": phone_number}
        )
        if not opt_status.get("opted_in", False):
            raise ValueError(f"Phone number {phone_number} has not opted in")

        logger.info(
            "WhatsApp connection established for session=%s, phone=%s",
            session.session_id,
            phone_number,  # codeql[py/clear-text-logging-sensitive-data]
        )

        return {"phone_number": phone_number, "opted_in": True}

    async def disconnect(
        self,
        session: GatewaySession,
        connection_context: Any | None = None,
    ) -> None:
        """
        Close WhatsApp connection (no-op for webhook-based channel).

        Args:
            session: Session to disconnect
            connection_context: Connection context (unused)
        """
        logger.debug("WhatsApp disconnect for session=%s", session.session_id)
        # No cleanup needed for webhook-based channel

    async def handle_heartbeat(
        self,
        session: GatewaySession,
        connection_context: Any | None = None,
    ) -> bool:
        """
        Handle heartbeat for WhatsApp connection (opt-in status check).

        Args:
            session: Session to check
            connection_context: Dict with 'phone_number'

        Returns:
            True if still opted in, False if opted out
        """
        if not isinstance(connection_context, dict):
            return False

        phone_number = connection_context.get("phone_number")
        if not phone_number:
            return False

        try:
            opt_status = await self.integration.check_opt_in_status(
                {"phone_number": phone_number}
            )
            return opt_status.get("opted_in", False)
        except Exception as e:
            logger.error("WhatsApp heartbeat check failed: %s", e, exc_info=True)
            return False
