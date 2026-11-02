# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Telegram Bot API Endpoints (MVA-2074)

Provides webhook endpoint for receiving Telegram messages and
routing them to AutoBot chat service.
"""

import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.schemas_chat import ChatMessage
from api.schemas_telegram import TelegramBotConfigRequest, TelegramBotConfigResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.gateway.gateway_manager import GatewayManager
from services.gateway.ingest_governor import ingest_governor
from services.telegram_bot_service import (
    TelegramBotService,
    get_telegram_bot_id,
    get_telegram_bot_token,
    get_telegram_webhook_secret,
    save_telegram_bot_id,
    save_telegram_bot_token,
    save_telegram_webhook_secret,
)
from services.telegram_polling import (
    INGEST_MODE_POLLING,
    delete_webhook,
    get_ingest_mode,
    save_ingest_mode,
)
from utils.chat_utils import chat_history_manager_for, generate_request_id

logger = get_logger(__name__)

router = APIRouter(tags=["telegram-bot"])

# Module-level gateway manager — shared, stateless
gateway_manager = GatewayManager()

# Resolve the bot's own Telegram user id for the Gateway ingest self-filter
# (#14028) from Redis — set by configure_telegram_bot() via getMe() — rather
# than requiring an operator to hand-configure AUTOBOT_GATEWAY_BOT_ID_TELEGRAM.
ingest_governor.register_bot_id_resolver("telegram", get_telegram_bot_id)


async def telegram_gateway_response_handler(platform_response: Dict[str, Any]) -> None:
    """
    Handle denormalized Telegram responses from the gateway (MVA-2373).

    Reads the `_api_method` field set by TelegramAdapter.denormalize_response()
    and routes to the appropriate TelegramBotService method.

    Args:
        platform_response: Denormalized Telegram API payload with `_api_method` field

    Raises:
        ValueError: If required fields are missing
    """
    service = await TelegramBotService.from_redis()

    # Extract routing key set by TelegramAdapter.denormalize_response()
    api_method = platform_response.pop("_api_method", "sendMessage")
    chat_id = platform_response.get("chat_id")

    if not chat_id:
        raise ValueError("Telegram response missing required 'chat_id' field")

    # Route based on API method
    if api_method == "sendPhoto":
        await service.send_photo(
            chat_id=chat_id,
            photo=platform_response.get("photo"),
            caption=platform_response.get("caption"),
            reply_to_message_id=platform_response.get("reply_to_message_id"),
            message_thread_id=platform_response.get("message_thread_id"),
        )
    elif api_method == "sendDocument":
        await service.send_document(
            chat_id=chat_id,
            document=platform_response.get("document"),
            caption=platform_response.get("caption"),
            reply_to_message_id=platform_response.get("reply_to_message_id"),
            message_thread_id=platform_response.get("message_thread_id"),
        )
    else:
        # Default: sendMessage
        await service.send_message(
            chat_id=chat_id,
            text=platform_response.get("text"),
            reply_to_message_id=platform_response.get("reply_to_message_id"),
            parse_mode=platform_response.get("parse_mode", "Markdown"),
        )


# Register Telegram response handler with gateway
gateway_manager.register_response_handler("telegram", telegram_gateway_response_handler)


def _get_chat_session_id(chat_id: str) -> str:
    """Return a stable session ID for a Telegram chat."""
    return f"telegram_{chat_id}"


async def _handle_command(command: str, args: list[str], chat_id: str, message_id: int) -> Optional[str]:
    """
    Handle Telegram bot commands (MVA-2075).

    Args:
        command: Command name (without /)
        args: Command arguments
        chat_id: Telegram chat ID
        message_id: Message ID

    Returns:
        Response text or None if command not recognized
    """
    if command == "start":
        return "🤖 Welcome to AutoBot! Send me a message and I'll help you with AI-powered automation."

    elif command == "status":
        return "✅ AutoBot is online and ready to help!"

    elif command == "task":
        if not args:
            return "Usage: /task <task description>\nExample: /task analyze this code"
        task_desc = " ".join(args)
        return f"📝 Task received: {task_desc}\n\nProcessing with AI..."

    elif command == "help":
        return """
**AutoBot Commands:**

/start - Start conversation
/status - Check bot status
/task <description> - Create an AI task
/help - Show this help message

You can also just send me a regular message!
        """.strip()

    return None  # Unknown command


async def _route_to_chat_and_reply(app: FastAPI, unified_message: Any) -> None:
    """
    Route a normalized Telegram message to AutoBot chat service and send the reply.

    Handles:
    - Bot commands (/status, /task, etc.) (MVA-2075)
    - File attachments (MVA-2075)
    - Regular chat messages

    Uses app.state to access chat_history_manager and llm_service, matching
    the same pattern as api/chat.py. Takes the app rather than a request so
    the webhook and the polling ingest (#19010) share it.

    Args:
        app: FastAPI app (provides access to app.state services)
        unified_message: Normalized message from TelegramAdapter
    """
    # Handle bot commands (MVA-2075)
    if unified_message.metadata.get("is_command"):
        command = unified_message.metadata.get("command")
        args = unified_message.metadata.get("command_args", [])
        message_id = unified_message.metadata.get("message_id")

        response_text = await _handle_command(command, args, unified_message.channel_id, message_id)

        if response_text:
            await send_telegram_response(
                chat_id=unified_message.channel_id,
                response_text=response_text,
                message_id=message_id,
            )
            logger.info(f"Handled command /{command} in chat {unified_message.channel_id}")
            return

    # Handle file downloads (MVA-2075)
    if unified_message.metadata.get("has_file"):
        file_id = unified_message.metadata.get("file_id")
        file_type = unified_message.metadata.get("file_type")
        logger.info(f"Received {file_type} file from Telegram: {file_id} in chat {unified_message.channel_id}")
        # File metadata is already in metadata, can be processed by chat service

    from api.chat import process_chat_message
    from utils.lazy_singleton import lazy_init_singleton

    session_id = _get_chat_session_id(unified_message.channel_id)
    request_id = generate_request_id()

    # ChatMessage.content requires >=1 char. Caption-less media (photo/voice/
    # document/video/audio with no text) normalizes to an empty message, which
    # would raise ValidationError and drop the update. Synthesize a placeholder
    # naming the attachment so the turn is valid and the model knows media was
    # sent (GH#10483, mirrors the WhatsApp fix GH#10481).
    content = unified_message.message
    if not content and unified_message.metadata.get("has_file"):
        content = f"[{unified_message.metadata.get('file_type', 'media')} attachment]"

    # Build ChatMessage from normalized Telegram message
    chat_message = ChatMessage(
        content=content,
        role="user",
        session_id=session_id,
        metadata={
            "platform": "telegram",
            "telegram_user_id": unified_message.user_id,
            "telegram_chat_id": unified_message.channel_id,
            **unified_message.metadata,
        },
    )

    # Get services from app state (same pattern as chat.py)
    chat_history_manager = chat_history_manager_for(app.state)

    from services.llm_service import get_llm_service

    llm_service = lazy_init_singleton(app.state, "llm_service", get_llm_service)
    memory_interface = getattr(app.state, "memory_interface", None)

    # Generate AI response
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

    # Send response back to Telegram
    reply_message_id = unified_message.metadata.get("message_id")
    thread_id = unified_message.metadata.get("thread_id")
    await send_telegram_response(
        chat_id=unified_message.channel_id,
        response_text=response_data.content,
        message_id=reply_message_id,
        thread_id=thread_id,
    )
    logger.info(
        "Sent Telegram reply to chat %s (session %s)",
        unified_message.channel_id,
        session_id,
    )


async def process_telegram_update(app: FastAPI, update: Dict[str, Any]) -> None:
    """Normalize one Telegram update and route it to chat (#19010).

    The single ingest path for both the webhook and the polling ingest: the
    TelegramAdapter, then ingest governance (bot-self filter / dedup /
    recursion guard, #14028), then the chat reply.
    """
    message = update.get("message")
    if not message:
        # Not a message update (could be callback_query, etc.)
        logger.debug("Telegram update without message, ignoring")
        return

    # None means the governance stage dropped it; already logged why.
    unified_message = await gateway_manager.normalize_message({**update, "platform": "telegram"})
    if unified_message is None:
        return

    logger.info(
        "Received Telegram message from user %s in chat %s",
        unified_message.user_id,
        unified_message.channel_id,
    )
    await _route_to_chat_and_reply(app, unified_message)


async def verify_telegram_secret(request: Request) -> None:
    """Authenticate a Telegram webhook call (MVA-2074, GH#9657 fail-closed).

    Declared as a route dependency rather than an in-body check so the secret is
    verified *before* FastAPI validates the request body: an unauthenticated
    caller must not be able to probe the payload schema with a 422, and a request
    that arrives while no webhook secret is stored must fail closed with 503
    whatever its body looks like.
    """
    stored_secret = await get_telegram_webhook_secret()
    if not stored_secret:
        logger.error("Telegram webhook secret not configured - failing closed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook authentication not configured",
        )

    request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not request_secret:
        logger.warning("Telegram webhook authentication failed - missing secret header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication header",
        )

    if not secrets.compare_digest(request_secret, stored_secret):
        logger.warning("Telegram webhook authentication failed - invalid secret token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


async def reject_webhook_in_polling_mode() -> None:
    """Refuse webhook updates while the stored ingest mode is polling (#19010).

    Selecting polling deletes the Telegram webhook but leaves the stored secret
    in place (credential cleanup is human-approved, #17038), so a request that
    still carries it would otherwise inject updates alongside the poller. Runs
    after ``verify_telegram_secret`` so an unauthenticated caller never learns
    the ingest mode.
    """
    if await get_ingest_mode() == INGEST_MODE_POLLING:
        logger.warning("Telegram webhook call rejected: ingest mode is polling")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook ingest is disabled",
        )


@router.post(
    "/telegram/webhook",
    dependencies=[Depends(verify_telegram_secret), Depends(reject_webhook_in_polling_mode)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="telegram_webhook",
    error_code_prefix="TELEGRAM_BOT",
)
async def telegram_webhook(
    request: Request,
    update: Dict[str, Any] = Body(...),
) -> JSONResponse:
    """
    Receive Telegram webhook updates and route to chat service.

    This endpoint is called by Telegram servers when a message is sent to the bot.
    Messages are normalized via TelegramAdapter and routed to AutoBot chat.

    Security: Verifies the X-Telegram-Bot-Api-Secret-Token header matches the
    stored secret, enforced by the ``verify_telegram_secret`` route dependency
    so authentication runs before the request body is parsed. While the ingest
    mode is polling the route answers 409 (``reject_webhook_in_polling_mode``),
    so the webhook and the poller are never both live.

    Args:
        request: FastAPI request (for header access)
        update: Telegram Update object

    Returns:
        200 OK to acknowledge receipt
    """
    try:
        await process_telegram_update(request.app, update)
        return JSONResponse({"status": "ok"})

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process Telegram webhook update")
        # Return 200 to prevent Telegram from retrying, no error details to client
        return JSONResponse({"status": "ok"})


@router.post(
    "/telegram/config",
    response_model=TelegramBotConfigResponse,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="configure_telegram_bot",
    error_code_prefix="TELEGRAM_BOT",
)
async def configure_telegram_bot(
    request: TelegramBotConfigRequest,
) -> TelegramBotConfigResponse:
    """
    Configure Telegram bot token and ingest mode (webhook or polling, #19010).

    Requires admin permission.

    Args:
        request: Configuration request with bot token

    Returns:
        Configuration status and bot info
    """
    try:
        # Create service with new token
        service = TelegramBotService(bot_token=request.bot_token)

        # Verify token is valid (also resolves the bot's own account info)
        bot_info = await service.get_me()
        if bot_info is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Telegram bot token",
            )

        # Save token to Redis
        await save_telegram_bot_token(request.bot_token)

        # Persist the bot's own numeric id for the Gateway ingest self-filter
        # (#14028) — without this, the filter has nothing to compare inbound
        # authors against and silently never fires.
        bot_id = bot_info.get("id")
        if bot_id is not None:
            await save_telegram_bot_id(str(bot_id))
        else:
            logger.warning("Telegram getMe() response missing 'id' — ingest self-filter left unconfigured")

        webhook_url = await _apply_ingest_mode(service, request)

        return TelegramBotConfigResponse(
            status="success",
            message="Telegram bot configured successfully",
            webhook_url=webhook_url,
            ingest_mode=request.ingest_mode,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to configure Telegram bot")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to configure Telegram bot",
        ) from exc


async def _apply_ingest_mode(service: TelegramBotService, request: TelegramBotConfigRequest) -> Optional[str]:
    """Make the requested ingest mode the only live one; returns the webhook URL set.

    Polling deletes the webhook (Telegram refuses ``getUpdates`` while one is
    set); webhook mode stops the poller at its next tick via the stored mode.
    """
    if request.ingest_mode == INGEST_MODE_POLLING:
        await delete_webhook(service)
        await save_ingest_mode(request.ingest_mode)
        return None

    await save_ingest_mode(request.ingest_mode)
    if not request.webhook_url:
        return None
    secret_token = secrets.token_urlsafe(32)
    await save_telegram_webhook_secret(secret_token)
    await service.set_webhook(request.webhook_url, secret_token)
    return request.webhook_url


@router.get(
    "/telegram/config",
    response_model=TelegramBotConfigResponse,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_telegram_config",
    error_code_prefix="TELEGRAM_BOT",
)
async def get_telegram_config() -> TelegramBotConfigResponse:
    """
    Get current Telegram bot configuration.

    Requires admin permission.

    Returns:
        Current webhook URL and configuration status
    """
    try:
        # Check if token is configured
        bot_token = await get_telegram_bot_token()
        if not bot_token:
            return TelegramBotConfigResponse(
                status="not_configured",
                message="Telegram bot not configured",
                webhook_url=None,
            )

        # Get webhook info
        service = TelegramBotService(bot_token=bot_token)
        webhook_info = await service.get_webhook_info()

        webhook_url = None
        if webhook_info.get("ok"):
            result = webhook_info.get("result", {})
            webhook_url = result.get("url", "")

        return TelegramBotConfigResponse(
            status="configured",
            message="Telegram bot is configured",
            webhook_url=webhook_url if webhook_url else None,
            ingest_mode=await get_ingest_mode(),
        )

    except Exception as exc:
        logger.exception("Failed to get Telegram bot config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get Telegram bot config",
        ) from exc


async def send_telegram_response(
    chat_id: str,
    response_text: str,
    message_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    file_id: Optional[str] = None,
    file_type: Optional[str] = None,
) -> None:
    """
    Send a response back to Telegram user (MVA-2074, MVA-2075).

    Supports:
    - Text messages
    - Photos (via file_id)
    - Documents (via file_id)
    - Thread replies (group chats)

    Args:
        chat_id: Telegram chat ID
        response_text: Response message text or caption
        message_id: Optional message ID to reply to
        thread_id: Optional thread ID for group chats (MVA-2075)
        file_id: Optional file ID to send photo/document (MVA-2075)
        file_type: Optional file type ('photo' or 'document') (MVA-2075)
    """
    try:
        service = await TelegramBotService.from_redis()

        # Send photo
        if file_id and file_type == "photo":
            await service.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=response_text,
                reply_to_message_id=message_id,
                message_thread_id=thread_id,
            )
            logger.info(f"Sent photo response to Telegram chat {chat_id}")

        # Send document
        elif file_id and file_type == "document":
            await service.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=response_text,
                reply_to_message_id=message_id,
                message_thread_id=thread_id,
            )
            logger.info(f"Sent document response to Telegram chat {chat_id}")

        # Send text message
        else:
            await service.send_message(
                chat_id=chat_id,
                text=response_text,
                reply_to_message_id=message_id,
                message_thread_id=thread_id,
            )
            if thread_id:
                logger.info(f"Sent response to Telegram chat {chat_id} thread {thread_id}")
            else:
                logger.info(f"Sent response to Telegram chat {chat_id}")

        # Record this agent-authored send for the recursion guard (#14028) —
        # this is the actual live send seam (GatewayManager.route_message is
        # not reached from this webhook path), so recording here is what
        # makes the guard real rather than decorative.
        await ingest_governor.record_agent_send(platform="telegram", channel_id=str(chat_id))
    except Exception:
        logger.exception("Failed to send Telegram response")
        raise
