# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Telegram Bot API Endpoints (MVA-2074)

Provides webhook endpoint for receiving Telegram messages and
routing them to AutoBot chat service.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.schemas_system import (
    TelegramWebhookUpdate,
    TelegramBotConfigRequest,
    TelegramBotConfigResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.gateway.gateway_manager import GatewayManager
from services.gateway.adapters import NormalizedResponse
from services.telegram_bot_service import (
    TelegramBotService,
    save_telegram_bot_token,
    get_telegram_bot_token,
)
from utils.chat_utils import generate_message_id, generate_request_id

logger = get_logger(__name__)

router = APIRouter(tags=["telegram-bot"])

# Initialize gateway manager for message normalization
gateway_manager = GatewayManager()


@router.post("/telegram/webhook")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="telegram_webhook",
    error_code_prefix="TELEGRAM_BOT",
)
async def telegram_webhook(
    update: Dict[str, Any] = Body(...),
) -> JSONResponse:
    """
    Receive Telegram webhook updates and route to chat service.

    This endpoint is called by Telegram servers when a message is sent to the bot.
    Messages are normalized via TelegramAdapter and routed to AutoBot chat.

    Args:
        update: Telegram Update object

    Returns:
        200 OK to acknowledge receipt
    """
    try:
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
            f"Received Telegram message from user {unified_message.user_id} "
            f"in chat {unified_message.channel_id}"
        )

        # TODO: Route to AutoBot chat service
        # This will be implemented when chat service integration is ready
        # For now, just acknowledge receipt

        # Example of what the full integration would look like:
        # chat_response = await send_to_chat_service(
        #     user_id=unified_message.user_id,
        #     message=unified_message.message,
        #     platform="telegram",
        #     channel_id=unified_message.channel_id,
        #     metadata=unified_message.metadata,
        # )
        #
        # # Send response back to Telegram
        # await send_telegram_response(
        #     chat_id=unified_message.channel_id,
        #     response_text=chat_response.text,
        #     message_id=unified_message.metadata.get("message_id"),
        # )

        return JSONResponse({"status": "ok"})

    except Exception as exc:
        logger.exception("Failed to process Telegram webhook update")
        # Return 200 to prevent Telegram from retrying
        return JSONResponse({"status": "error", "message": str(exc)})


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
            await service.set_webhook(request.webhook_url)
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
            detail=f"Failed to configure Telegram bot: {str(exc)}",
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
            detail=f"Failed to get Telegram bot config: {str(exc)}",
        ) from exc


async def send_telegram_response(
    chat_id: str,
    response_text: str,
    message_id: Optional[int] = None,
) -> None:
    """
    Send a response back to Telegram user.

    Args:
        chat_id: Telegram chat ID
        response_text: Response message text
        message_id: Optional message ID to reply to
    """
    try:
        service = await TelegramBotService.from_redis()
        await service.send_message(
            chat_id=chat_id,
            text=response_text,
            reply_to_message_id=message_id,
        )
        logger.info(f"Sent response to Telegram chat {chat_id}")
    except Exception as exc:
        logger.exception("Failed to send Telegram response")
        raise
