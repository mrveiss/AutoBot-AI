# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WhatsApp Business API Endpoints (Issue #9007)

Provides the inbound webhook (Meta verification challenge + message delivery)
and admin configuration endpoints for the WhatsApp channel, mirroring the
Telegram bot adapter (``api/telegram_bot.py``):

    Meta servers ──▶ POST /whatsapp/webhook
                       ├─ verify X-Hub-Signature-256 (app secret)
                       ├─ flatten Meta envelope ──▶ GatewayManager.normalize_message
                       ├─ process_chat_message (AutoBot chat pipeline)
                       └─ WhatsAppIntegration.send_text_message (reply)

Outbound replies reuse ``WhatsAppIntegration`` so opt-in enforcement, error
handling, and PII masking are applied on the send path.

Issue #10267 - Route inbound WhatsApp media/voice into chat pipeline.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from api.schemas_chat import ChatMessage
from api.schemas_system import WhatsAppConfigRequest, WhatsAppConfigResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.gateway.gateway_manager import GatewayManager
from services.whatsapp_service import (
    build_integration,
    download_whatsapp_media,
    flatten_messages,
    get_whatsapp_app_secret,
    get_whatsapp_verify_token,
    save_whatsapp_config,
    verify_webhook_signature,
)
from utils.chat_utils import generate_request_id

logger = get_logger(__name__)

router = APIRouter(tags=["whatsapp"])

# Module-level gateway manager — shared, stateless (matches telegram_bot.py)
gateway_manager = GatewayManager()


def _get_chat_session_id(chat_id: str) -> str:
    """Return a stable session ID for a WhatsApp conversation."""
    return f"whatsapp_{chat_id}"


async def send_whatsapp_response(to: str, response_text: str) -> None:
    """Send a text reply back to a WhatsApp user via ``WhatsAppIntegration``."""
    integration = await build_integration()
    if integration is None:
        logger.error("Cannot send WhatsApp reply — channel not configured")
        return
    await integration.send_text_message({"to": to, "body": response_text})


async def _route_to_chat_and_reply(
    request: Request,
    unified_message: Any,
    media_bytes: Optional[bytes] = None,
    media_mime_type: Optional[str] = None,
) -> None:
    """Route a normalized WhatsApp message to chat and send the AI reply.

    Args:
        request:         FastAPI request (used to reach app.state services).
        unified_message: Gateway-normalized message.
        media_bytes:     Raw media bytes downloaded from the Graph API, if the
                         inbound message carried a media attachment (GH#10267).
        media_mime_type: MIME type of the downloaded media, or None.
    """
    from api.chat import process_chat_message
    from services.llm_service import LLMService
    from utils.chat_utils import get_chat_history_manager
    from utils.lazy_singleton import lazy_init_singleton

    session_id = _get_chat_session_id(unified_message.channel_id)
    request_id = generate_request_id()

    extra_metadata: Dict[str, Any] = {}
    if media_bytes is not None:
        # Attach media to the chat message metadata mirroring telegram_adapter's has_file pattern
        extra_metadata["has_file"] = True
        extra_metadata["file_bytes"] = media_bytes
        extra_metadata["file_type"] = unified_message.metadata.get("message_type", "media")
        if media_mime_type:
            extra_metadata["mime_type"] = media_mime_type

    chat_message = ChatMessage(
        content=unified_message.message,
        role="user",
        session_id=session_id,
        metadata={
            "platform": "whatsapp",
            "whatsapp_user_id": unified_message.user_id,
            "whatsapp_chat_id": unified_message.channel_id,
            **unified_message.metadata,
            **extra_metadata,
        },
    )

    chat_history_manager = get_chat_history_manager(request)
    llm_service = lazy_init_singleton(request.app.state, "llm_service", LLMService)
    memory_interface = getattr(request.app.state, "memory_interface", None)

    response_data = await process_chat_message(
        message=chat_message,
        chat_history_manager=chat_history_manager,
        llm_service=llm_service,
        memory_interface=memory_interface,
        knowledge_base=None,
        config={},
        request_id=request_id,
        author_id=unified_message.user_id,
    )

    await send_whatsapp_response(unified_message.channel_id, response_data.content)
    logger.info("Sent WhatsApp reply (session %s)", session_id)


@router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(request: Request) -> PlainTextResponse:
    """Answer Meta's webhook subscription challenge.

    Meta sends ``hub.mode=subscribe`` with ``hub.verify_token`` and
    ``hub.challenge``; echo the challenge only when the token matches.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    stored_token = await get_whatsapp_verify_token()
    if not stored_token:
        logger.error("WhatsApp verify token not configured — failing closed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook not configured")

    if mode == "subscribe" and token == stored_token:
        return PlainTextResponse(content=challenge)

    logger.warning("WhatsApp webhook verification failed — token mismatch")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/whatsapp/webhook")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="whatsapp_webhook",
    error_code_prefix="WHATSAPP",
)
async def whatsapp_webhook(request: Request) -> JSONResponse:
    """Receive WhatsApp webhook deliveries and route messages to chat.

    Security: verifies the ``X-Hub-Signature-256`` HMAC over the raw body using
    the stored app secret (Meta security requirement). Fails closed.

    Text messages are routed immediately.  Media messages (image/audio/voice/
    video/document) are downloaded from the Graph API and attached to the chat
    message as ``has_file`` metadata before dispatch, mirroring the Telegram
    adapter's has_file flow (GH#10267).
    """
    raw_body = await request.body()

    app_secret = await get_whatsapp_app_secret()
    if not app_secret:
        logger.error("WhatsApp app secret not configured — failing closed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook not configured")

    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_webhook_signature(raw_body, signature, app_secret):
        logger.warning("WhatsApp webhook signature verification failed")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    import json

    try:
        webhook_body: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("WhatsApp webhook body is not valid JSON")
        return JSONResponse({"status": "ok"})

    for raw_message in flatten_messages(webhook_body):
        media_bytes: Optional[bytes] = None
        media_mime_type: Optional[str] = None

        if not raw_message.get("body"):
            # Non-text inbound message — attempt to download and route media (GH#10267)
            media_id: Optional[str] = raw_message.get("media_id")
            if not media_id:
                logger.info(
                    "Received non-text WhatsApp message type=%s (no downloadable media_id)",
                    raw_message.get("message_type"),
                )
                continue
            media_bytes, media_mime_type = await download_whatsapp_media(media_id)
            if media_bytes is None:
                logger.warning(
                    "Could not download WhatsApp media (media_id=%s, type=%s) — skipping",
                    media_id,
                    raw_message.get("message_type"),
                )
                continue
            logger.info(
                "Downloaded WhatsApp media (media_id=%s, type=%s, size=%d bytes)",
                media_id,
                raw_message.get("message_type"),
                len(media_bytes),
            )

        unified_message = await gateway_manager.normalize_message(raw_message)
        await _route_to_chat_and_reply(request, unified_message, media_bytes, media_mime_type)

    return JSONResponse({"status": "ok"})


@router.post(
    "/whatsapp/config",
    response_model=WhatsAppConfigResponse,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="configure_whatsapp",
    error_code_prefix="WHATSAPP",
)
async def configure_whatsapp(config: WhatsAppConfigRequest) -> WhatsAppConfigResponse:
    """Configure WhatsApp Business API credentials. Requires admin permission.

    Verifies the access token against the Meta API before persisting.
    """
    await save_whatsapp_config(
        access_token=config.access_token,
        phone_number_id=config.phone_number_id,
        app_secret=config.app_secret,
        verify_token=config.verify_token,
        business_account_id=config.business_account_id,
        base_url=config.base_url,
    )

    integration = await build_integration()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to build integration")

    health = await integration.test_connection()
    phone_number = health.details.get("phone_number") if health.details else None
    return WhatsAppConfigResponse(
        status="success",
        message=health.message,
        phone_number=phone_number,
    )


@router.get(
    "/whatsapp/config",
    response_model=WhatsAppConfigResponse,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_whatsapp_config",
    error_code_prefix="WHATSAPP",
)
async def get_whatsapp_config() -> WhatsAppConfigResponse:
    """Return current WhatsApp channel status. Requires admin permission."""
    integration = await build_integration()
    if integration is None:
        return WhatsAppConfigResponse(status="not_configured", message="WhatsApp channel not configured")

    health = await integration.test_connection()
    phone_number = health.details.get("phone_number") if health.details else None
    return WhatsAppConfigResponse(
        status="configured",
        message=health.message,
        phone_number=phone_number,
    )
