# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Telegram Bot Service (MVA-2074, MVA-2075, #9606)

Manages Telegram bot instance, sends messages via Bot API,
handles webhook verification, and supports file/photo uploads.

Security: Bot tokens and webhook secrets are encrypted at rest using
AES-256-GCM field encryption (see autobot_shared.field_encryption).
"""

from typing import Any, Dict, Optional

import aiohttp

from autobot_shared.field_encryption import decrypt_field, encrypt_field
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client

logger = get_logger(__name__)

# Redis keys for storing Telegram bot config
TELEGRAM_BOT_TOKEN_KEY = "autobot:settings:telegram_bot_token"
TELEGRAM_WEBHOOK_SECRET_KEY = "autobot:settings:telegram_webhook_secret"

# Sentinel prefix for encrypted values (backward compatibility)
_ENCRYPTED_PREFIX = "enc:"


class TelegramBotService:
    """Service for managing Telegram bot interactions."""

    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize Telegram bot service.

        Args:
            bot_token: Telegram Bot API token (optional, will load from Redis if not provided)
        """
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}" if bot_token else None

    @classmethod
    async def from_redis(cls) -> "TelegramBotService":
        """
        Load bot token from Redis and create service instance.

        Security: Automatically decrypts encrypted tokens (prefixed with 'enc:').
        """
        redis = await get_redis_client()
        if redis is None:
            logger.error("Redis client not available for Telegram bot service")
            return cls(bot_token=None)

        bot_token = await redis.get(TELEGRAM_BOT_TOKEN_KEY)
        if bot_token:
            bot_token = bot_token.decode("utf-8") if isinstance(bot_token, bytes) else bot_token
            # Decrypt if encrypted (backward compatible with plaintext tokens)
            if bot_token.startswith(_ENCRYPTED_PREFIX):
                try:
                    bot_token = decrypt_field(bot_token[len(_ENCRYPTED_PREFIX) :])
                    logger.info("Loaded and decrypted Telegram bot token from Redis")
                except Exception as exc:
                    logger.error(f"Failed to decrypt Telegram bot token: {exc}")
                    return cls(bot_token=None)
            else:
                logger.warning("Telegram bot token is stored in plaintext (not encrypted)")
                logger.info("Loaded Telegram bot token from Redis")
        else:
            logger.warning("No Telegram bot token found in Redis")

        return cls(bot_token=bot_token)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: Optional[int] = None,
        parse_mode: str = "Markdown",
    ) -> Dict[str, Any]:
        """
        Send a message via Telegram Bot API.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            reply_to_message_id: Optional message ID to reply to
            parse_mode: Message formatting mode (Markdown or HTML)

        Returns:
            API response dict

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/sendMessage"
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram sendMessage failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                logger.info(f"Sent Telegram message to chat {chat_id}")
                return result

    async def set_webhook(self, webhook_url: str, secret_token: str) -> Dict[str, Any]:
        """
        Set the webhook URL for receiving Telegram updates with secret token.

        Args:
            webhook_url: Public HTTPS URL where Telegram will send updates
            secret_token: Secret token for webhook authentication

        Returns:
            API response dict

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/setWebhook"
            payload = {
                "url": webhook_url,
                "secret_token": secret_token,
            }
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram setWebhook failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                logger.info(f"Set Telegram webhook to {webhook_url}")
                return result

    async def get_webhook_info(self) -> Dict[str, Any]:
        """
        Get current webhook information.

        Returns:
            Webhook info dict

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/getWebhookInfo"
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram getWebhookInfo failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                return result

    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """
        Get file metadata from Telegram (MVA-2075).

        Args:
            file_id: Telegram file ID

        Returns:
            File metadata including file_path for download

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/getFile"
            payload = {"file_id": file_id}
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram getFile failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                if result.get("ok"):
                    return result.get("result", {})
                return {}

    async def download_file(self, file_path: str) -> bytes:
        """
        Download file content from Telegram servers (MVA-2075).

        Args:
            file_path: File path from getFile response

        Returns:
            File content as bytes

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If download fails
        """
        if not self.bot_token:
            raise ValueError("Telegram bot token not configured")

        download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"

        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"File download failed: {response.status} - {error_text}")
                    response.raise_for_status()

                content = await response.read()
                logger.info(f"Downloaded file from Telegram: {file_path}")
                return content

    async def send_photo(
        self,
        chat_id: str,
        photo: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        message_thread_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a photo via Telegram Bot API (MVA-2075).

        Args:
            chat_id: Telegram chat ID
            photo: File ID or URL
            caption: Optional caption text
            reply_to_message_id: Optional message ID to reply to
            message_thread_id: Optional thread ID for group chats

        Returns:
            API response dict

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "photo": photo,
        }

        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = "Markdown"

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/sendPhoto"
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram sendPhoto failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                logger.info(f"Sent photo to Telegram chat {chat_id}")
                return result

    async def send_document(
        self,
        chat_id: str,
        document: str,
        caption: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        message_thread_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a document via Telegram Bot API (MVA-2075).

        Args:
            chat_id: Telegram chat ID
            document: File ID or URL
            caption: Optional caption text
            reply_to_message_id: Optional message ID to reply to
            message_thread_id: Optional thread ID for group chats

        Returns:
            API response dict

        Raises:
            ValueError: If bot token not configured
            aiohttp.ClientError: If API request fails
        """
        if not self.bot_token or not self.base_url:
            raise ValueError("Telegram bot token not configured")

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "document": document,
        }

        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = "Markdown"

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/sendDocument"
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram sendDocument failed: {response.status} - {error_text}")
                    response.raise_for_status()

                result = await response.json()
                logger.info(f"Sent document to Telegram chat {chat_id}")
                return result

    async def verify_token(self) -> bool:
        """
        Verify that the bot token is valid by calling getMe.

        Returns:
            True if token is valid, False otherwise
        """
        if not self.bot_token or not self.base_url:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/getMe"
                async with session.get(url) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("ok"):
                            bot_info = result.get("result", {})
                            logger.info(f"Telegram bot verified: @{bot_info.get('username')}")
                            return True
            return False
        except Exception as exc:
            logger.error(f"Failed to verify Telegram bot token: {exc}")
            return False


async def save_telegram_bot_token(bot_token: str) -> None:
    """
    Save Telegram bot token to Redis (encrypted).

    Args:
        bot_token: Telegram Bot API token
    """
    redis = await get_redis_client()
    if redis is None:
        raise RuntimeError("Redis client not available")

    # Encrypt the token before storing
    try:
        encrypted_token = _ENCRYPTED_PREFIX + encrypt_field(bot_token)
        await redis.set(TELEGRAM_BOT_TOKEN_KEY, encrypted_token)
        logger.info("Saved encrypted Telegram bot token to Redis")
    except Exception as exc:
        logger.error(f"Failed to encrypt Telegram bot token: {exc}")
        raise


async def get_telegram_bot_token() -> Optional[str]:
    """
    Get Telegram bot token from Redis (decrypted).

    Returns:
        Decrypted bot token or None if not configured
    """
    redis = await get_redis_client()
    if redis is None:
        logger.error("Redis client not available")
        return None

    bot_token = await redis.get(TELEGRAM_BOT_TOKEN_KEY)
    if bot_token:
        bot_token = bot_token.decode("utf-8") if isinstance(bot_token, bytes) else bot_token
        # Decrypt if encrypted (backward compatible with plaintext tokens)
        if bot_token.startswith(_ENCRYPTED_PREFIX):
            try:
                return decrypt_field(bot_token[len(_ENCRYPTED_PREFIX) :])
            except Exception as exc:
                logger.error(f"Failed to decrypt Telegram bot token: {exc}")
                return None
        else:
            logger.warning("Telegram bot token is stored in plaintext (not encrypted)")
            return bot_token
    return None


async def save_telegram_webhook_secret(secret: str) -> None:
    """
    Save Telegram webhook secret to Redis with encryption.

    Security: Secret is encrypted using AES-256-GCM before storage (#9606).

    Args:
        secret: Webhook secret token
    """
    redis = await get_redis_client()
    if redis is None:
        raise RuntimeError("Redis client not available")

    # Encrypt secret before storage (#9606)
    encrypted_secret = _ENCRYPTED_PREFIX + encrypt_field(secret)
    await redis.set(TELEGRAM_WEBHOOK_SECRET_KEY, encrypted_secret)
    logger.info("Saved encrypted Telegram webhook secret to Redis")


async def get_telegram_webhook_secret() -> Optional[str]:
    """
    Get Telegram webhook secret from Redis with decryption.

    Security: Automatically decrypts encrypted secrets (prefixed with 'enc:').

    Returns:
        Decrypted webhook secret or None if not configured
    """
    redis = await get_redis_client()
    if redis is None:
        logger.error("Redis client not available")
        return None

    secret = await redis.get(TELEGRAM_WEBHOOK_SECRET_KEY)
    if secret:
        secret = secret.decode("utf-8") if isinstance(secret, bytes) else secret

        # Decrypt if encrypted (#9606)
        if secret.startswith(_ENCRYPTED_PREFIX):
            try:
                return decrypt_field(secret[len(_ENCRYPTED_PREFIX):])
            except Exception as e:
                logger.error(f"Failed to decrypt Telegram webhook secret: {e}")
                return None

        # Return plaintext for backward compatibility
        return secret
    return None
