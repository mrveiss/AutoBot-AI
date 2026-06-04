# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WhatsApp Business API Webhook Integration
Receives incoming WhatsApp messages and routes them to AutoBot agents.
Issue #9007: WhatsApp channel adapter for bidirectional messaging.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig
from integrations.whatsapp_integration import WhatsAppIntegration
from services.gateway.channel_adapters import WhatsAppAdapter
from services.gateway.types import ChannelType, GatewaySession

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


class WhatsAppWebhookVerification(BaseModel):
    """WhatsApp webhook verification response."""

    challenge: str


class WhatsAppWebhookReceiveResponse(BaseModel):
    """WhatsApp webhook processing response."""

    status: str
    processed: int
    timestamp: str


@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """
    Verify WhatsApp webhook subscription.

    Meta requires webhook verification on initial setup:
    GET /webhook/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=CHALLENGE

    Returns:
        hub.challenge value if verification succeeds

    Raises:
        HTTPException: If verification token is invalid
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    # Load verify token from environment or config
    from autobot_shared.ssot_config import config

    expected_token = config.get("WHATSAPP_VERIFY_TOKEN", "autobot-verify-token")

    if mode == "subscribe" and token == expected_token:
        logger.info("WhatsApp webhook verification succeeded")
        return int(challenge) if challenge else ""

    logger.warning(
        "WhatsApp webhook verification failed: mode=%s, token=%s",
        mode,
        token,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed",
    )


@router.post("/whatsapp", response_model=WhatsAppWebhookReceiveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_whatsapp_webhook",
    error_code_prefix="WHATSAPP_WEBHOOK",
)
async def receive_whatsapp_webhook(payload: Dict[str, Any], request: Request):
    """
    Receive incoming WhatsApp messages from Meta webhook.

    Meta sends webhooks for:
    - Incoming messages (text, image, audio, document, video)
    - Message status updates (sent, delivered, read, failed)
    - Account changes (phone number changes, business profile updates)

    This endpoint processes incoming messages and routes them to AutoBot agents.

    Args:
        payload: WhatsApp webhook payload
        request: FastAPI request object

    Returns:
        Processing status response

    Webhook payload structure:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "PHONE_NUMBER_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "123", "display_phone_number": "+1234567890"},
                    "messages": [{
                        "from": "+1234567890",
                        "id": "wamid.xxx",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": "Hello"}
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    """
    try:
        from autobot_shared.time_utils import now_utc

        logger.info("Received WhatsApp webhook: %s", payload.get("object"))

        # Extract messages from webhook
        entry_list = payload.get("entry", [])
        processed_count = 0

        for entry in entry_list:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                if not messages:
                    logger.debug("No messages in webhook entry")
                    continue

                # Process each message
                for msg in messages:
                    await _process_whatsapp_message(msg, value.get("metadata", {}))
                    processed_count += 1

        return {
            "status": "success",
            "processed": processed_count,
            "timestamp": now_utc().isoformat(),
        }

    except Exception as e:
        logger.error("Failed to process WhatsApp webhook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook",
        )


async def _process_whatsapp_message(msg: Dict[str, Any], metadata: Dict[str, Any]):
    """
    Process a single WhatsApp message and route to AutoBot agent.

    Args:
        msg: Message data from webhook
        metadata: Metadata about the phone number
    """
    try:
        sender = msg.get("from")
        msg_type = msg.get("type")
        msg_id = msg.get("id")

        logger.info(
            "Processing WhatsApp message: id=%s, from=%s, type=%s",
            msg_id,
            sender,  # codeql[py/clear-text-logging-sensitive-data]
            msg_type,
        )

        # Load WhatsApp integration config
        from autobot_shared.ssot_config import config

        phone_number_id = metadata.get("phone_number_id")
        if not phone_number_id:
            logger.warning("WhatsApp message missing phone_number_id in metadata")
            return

        # Create integration config
        integration_config = IntegrationConfig(
            name="whatsapp",
            provider="whatsapp",
            api_key=config.get("WHATSAPP_ACCESS_TOKEN", ""),
            base_url=config.get(
                "WHATSAPP_API_BASE_URL",
                "https://graph.facebook.com/v18.0",
            ),
            extra={
                "phone_number_id": phone_number_id,
                "business_account_id": config.get("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
            },
        )

        # Create integration and adapter
        integration = WhatsAppIntegration(integration_config)
        adapter = WhatsAppAdapter(integration)

        # Check opt-in status
        opt_status = await integration.check_opt_in_status({"phone_number": sender})
        if not opt_status.get("opted_in", False):
            logger.warning(
                "Received message from non-opted-in user: %s",
                sender,  # codeql[py/clear-text-logging-sensitive-data]
            )
            # Optionally send opt-in instructions
            return

        # Create or retrieve gateway session
        session = GatewaySession(
            session_id=f"whatsapp_{sender}",
            user_id=sender or "",
            channel=ChannelType.WHATSAPP,
            metadata={"phone_number": sender, "phone_number_id": phone_number_id},
        )

        # Parse message using adapter
        unified_msg = await adapter.receive_message({"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}, session)

        if unified_msg:
            logger.info(
                "Parsed WhatsApp message into unified format: msg_id=%s, type=%s",
                unified_msg.message_id,
                unified_msg.message_type,
            )

            # TODO: Route to appropriate AutoBot agent
            # This will be implemented in the gateway routing logic
            # For now, log that message was received
            logger.info(
                "WhatsApp message ready for routing: session=%s, content=%s",
                session.session_id,
                str(unified_msg.content)[:100],
            )
        else:
            logger.warning("Failed to parse WhatsApp message: %s", msg)

    except Exception as e:
        logger.error(
            "Failed to process WhatsApp message %s: %s",
            msg.get("id"),
            e,
            exc_info=True,
        )
