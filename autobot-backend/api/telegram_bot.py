# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Telegram Bot API Endpoints (MVA-2074)

Provides webhook endpoint for receiving Telegram messages and
routing them to AutoBot chat service.
"""

import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.schemas_chat import ChatMessage
from api.schemas_system import (
    TelegramBotConfigRequest,
    TelegramBotConfigResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.gateway.gateway_manager import GatewayManager
from services.telegram_bot_service import (
    TelegramBotService,
    get_telegram_bot_token,
    get_telegram_webhook_secret,
    save_telegram_bot_token,
    save_telegram_webhook_secret,
)
from utils.chat_utils import generate_request_id

logger = get_logger(__name__)

router = APIRouter(tags=["telegram-bot"])

# Module-level gateway manager — shared, stateless
gateway_manager = GatewayManager()


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


async def _route_to_chat_and_reply(request: Request, unified_message: Any) -> None:
    """
    Route a normalized Telegram message to AutoBot chat service and send the reply.

    Handles:
    - Bot commands (/status, /task, etc.) (MVA-2075)
    - File attachments (MVA-2075)
    - Regular chat messages

    Uses request.app.state to access chat_history_manager and llm_service,
    matching the same pattern as api/chat.py.

    Args:
        request: FastAPI request (provides access to app.state services)
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
    from utils.chat_utils import get_chat_history_manager
    from utils.lazy_singleton import lazy_init_singleton

    session_id = _get_chat_session_id(unified_message.channel_id)
    request_id = generate_request_id()

    # Build ChatMessage from normalized Telegram message
    chat_message = ChatMessage(
        content=unified_message.message,
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
    chat_history_manager = get_chat_history_manager(request)

    from services.llm_service import LLMService

    llm_service = lazy_init_singleton(request.app.state, "llm_service", LLMService)
    memory_interface = getattr(request.app.state, "memory_interface", None)

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


@router.post("/telegram/webhook")
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

    Security: Verifies X-Telegram-Bot-Api-Secret-Token header matches stored secret.

    Args:
        request: FastAPI request (for header access)
        update: Telegram Update object

    Returns:
        200 OK to acknowledge receipt
    """
    try:
        # Verify webhook secret token (MVA-2074 security requirement)
        stored_secret = await get_telegram_webhook_secret()
        if not stored_secret:
            logger.error("Telegram webhook secret not configured")
            return JSONResponse({"status": "ok"})  # Return OK to avoid retry storm

        request_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if request_secret != stored_secret:
            logger.warning("Telegram webhook authentication failed - invalid secret token")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        # Extract message from update
        message = update.get("message")
        if not message:
            # Not a message update (could be callback_query, etc.)
            logger.debug("Telegram update without message, ignoring")
            return JSONResponse({"status": "ok"})

        # Add platform identifier for gateway
        raw_message = {**update, "platform": "telegram"}

        # Normalize message via TelegramAdapter
        unified_message = await gateway_manager.normalize_message(raw_message)
        logger.info(
            "Received Telegram message from user %s in chat %s",
            unified_message.user_id,
            unified_message.channel_id,
        )

        # Route to AutoBot chat service
        await _route_to_chat_and_reply(request, unified_message)

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
    Configure Telegram bot token and webhook.

    Requires admin permission.

    Args:
        request: Configuration request with bot token

    Returns:
        Configuration status and bot info
    """
    try:
        # Create service with new token
        service = TelegramBotService(bot_token=request.bot_token)

        # Verify token is valid
        is_valid = await service.verify_token()
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Telegram bot token",
            )

        # Save token to Redis
        await save_telegram_bot_token(request.bot_token)

        # Set webhook if URL provided
        webhook_url = None
        if request.webhook_url:
            # Generate secure random secret token
            secret_token = secrets.token_urlsafe(32)

            # Save secret to Redis
            await save_telegram_webhook_secret(secret_token)

            # Set webhook with secret
            await service.set_webhook(request.webhook_url, secret_token)
            webhook_url = request.webhook_url

        return TelegramBotConfigResponse(
            status="success",
            message="Telegram bot configured successfully",
            webhook_url=webhook_url,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to configure Telegram bot")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to configure Telegram bot",
        ) from exc


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

    except Exception:
        logger.exception("Failed to send Telegram response")
        raise
