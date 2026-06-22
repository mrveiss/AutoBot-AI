# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
WhatsApp Business API Service (Issue #9007)

Bridges the inbound WhatsApp webhook route to the reusable
``WhatsAppIntegration`` (``integrations/whatsapp_integration.py``):

- Stores/loads channel credentials in Redis, encrypted at rest with the same
  AES-256-GCM field encryption used by the Telegram channel.
- Verifies the ``X-Hub-Signature-256`` HMAC that Meta attaches to every webhook
  delivery (Meta security requirement).
- Flattens Meta's nested webhook envelope into the flat shape the gateway
  ``WhatsAppAdapter`` expects, so messages can be normalized and routed to chat.
- Downloads inbound media via the Graph API media endpoint (GH#10267).

Security: access token and app secret are encrypted at rest (see
``autobot_shared.field_encryption``).
"""

import hashlib
import hmac
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.field_encryption import decrypt_field, encrypt_field
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from integrations.base import IntegrationConfig
from integrations.whatsapp_integration import WhatsAppIntegration

logger = get_logger(__name__)

# Redis keys for storing WhatsApp channel config (key names, not secrets)
WHATSAPP_ACCESS_TOKEN_KEY = "autobot:settings:whatsapp_access_token"  # nosec B105 - Redis key name
WHATSAPP_APP_SECRET_KEY = "autobot:settings:whatsapp_app_secret"  # nosec B105 - Redis key name
WHATSAPP_VERIFY_TOKEN_KEY = "autobot:settings:whatsapp_verify_token"  # nosec B105 - Redis key name
WHATSAPP_PHONE_NUMBER_ID_KEY = "autobot:settings:whatsapp_phone_number_id"  # nosec B105 - Redis key name
WHATSAPP_BUSINESS_ACCOUNT_ID_KEY = "autobot:settings:whatsapp_business_account_id"  # nosec B105 - Redis key name
WHATSAPP_BASE_URL_KEY = "autobot:settings:whatsapp_base_url"  # nosec B105 - Redis key name

# Sentinel prefix for encrypted values (backward compatibility with plaintext)
_ENCRYPTED_PREFIX = "enc:"


def _decode(raw: Any) -> Optional[str]:
    """Decode a Redis value to ``str``, decrypting if it carries the enc: prefix."""
    if raw is None:
        return None
    value = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if value.startswith(_ENCRYPTED_PREFIX):
        return decrypt_field(value[len(_ENCRYPTED_PREFIX) :])
    return value


async def _set_encrypted(key: str, value: str) -> None:
    """Store an encrypted value in Redis under ``key``."""
    redis = await get_redis_client()
    if redis is None:
        logger.error("Redis unavailable; cannot persist WhatsApp config key %s", key)
        return
    await redis.set(key, f"{_ENCRYPTED_PREFIX}{encrypt_field(value)}")


async def _set_plain(key: str, value: str) -> None:
    """Store a non-secret value in Redis under ``key``."""
    redis = await get_redis_client()
    if redis is None:
        logger.error("Redis unavailable; cannot persist WhatsApp config key %s", key)
        return
    await redis.set(key, value)


async def _get(key: str) -> Optional[str]:
    """Load and decode a value from Redis under ``key``."""
    redis = await get_redis_client()
    if redis is None:
        return None
    return _decode(await redis.get(key))


async def save_whatsapp_config(
    access_token: str,
    phone_number_id: str,
    app_secret: str,
    verify_token: str,
    business_account_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> None:
    """Persist WhatsApp channel credentials (secrets encrypted at rest)."""
    await _set_encrypted(WHATSAPP_ACCESS_TOKEN_KEY, access_token)
    await _set_encrypted(WHATSAPP_APP_SECRET_KEY, app_secret)
    await _set_encrypted(WHATSAPP_VERIFY_TOKEN_KEY, verify_token)
    await _set_plain(WHATSAPP_PHONE_NUMBER_ID_KEY, phone_number_id)
    if business_account_id:
        await _set_plain(WHATSAPP_BUSINESS_ACCOUNT_ID_KEY, business_account_id)
    if base_url:
        await _set_plain(WHATSAPP_BASE_URL_KEY, base_url)
    logger.info("Saved WhatsApp channel configuration")


async def get_whatsapp_verify_token() -> Optional[str]:
    """Return the Meta webhook verify token, or None if unconfigured."""
    return await _get(WHATSAPP_VERIFY_TOKEN_KEY)


async def get_whatsapp_app_secret() -> Optional[str]:
    """Return the Meta app secret used for signature verification."""
    return await _get(WHATSAPP_APP_SECRET_KEY)


async def build_integration() -> Optional[WhatsAppIntegration]:
    """Construct a ``WhatsAppIntegration`` from stored credentials.

    Returns None when the channel has not been configured.
    """
    access_token = await _get(WHATSAPP_ACCESS_TOKEN_KEY)
    phone_number_id = await _get(WHATSAPP_PHONE_NUMBER_ID_KEY)
    if not access_token or not phone_number_id:
        logger.warning("WhatsApp channel not configured; cannot build integration")
        return None

    config = IntegrationConfig(
        name="whatsapp",
        provider="whatsapp",
        api_key=access_token,
        base_url=await _get(WHATSAPP_BASE_URL_KEY),
        extra={
            "phone_number_id": phone_number_id,
            "business_account_id": await _get(WHATSAPP_BUSINESS_ACCOUNT_ID_KEY),
        },
    )
    return WhatsAppIntegration(config)


def verify_webhook_signature(payload: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    """Verify Meta's ``X-Hub-Signature-256`` HMAC over the raw request body.

    Meta signs every webhook delivery with ``sha256=<hex>`` computed using the
    app secret. Fails closed: a missing/malformed header or absent secret yields
    False.
    """
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    provided = signature_header[len("sha256=") :]
    expected = hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


async def download_whatsapp_media(media_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Download WhatsApp media bytes via the Graph API media endpoint.

    Flow (Graph API):
      1. GET /{media-id}  -> JSON with a short-lived ``url`` field.
      2. GET {url} with Bearer access token -> raw media bytes.

    Returns:
        Tuple of (raw_bytes, mime_type) on success; (None, None) on failure.
        Never raises; logs and returns (None, None) on any error.

    GH#10267 -- mirrors telegram_adapter's has_file/media-download flow.
    """
    import aiohttp

    access_token = await _get(WHATSAPP_ACCESS_TOKEN_KEY)
    if not access_token:
        logger.warning("Cannot download WhatsApp media — access token not configured")
        return None, None

    base_url = (await _get(WHATSAPP_BASE_URL_KEY)) or "https://graph.facebook.com/v18.0"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 1: resolve the temporary download URL
            async with session.get(f"{base_url}/{media_id}", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(
                        "WhatsApp media metadata fetch failed (media_id=%s, status=%s)",
                        media_id,
                        resp.status,
                    )
                    return None, None
                meta = await resp.json()

            download_url = meta.get("url")
            mime_type: Optional[str] = meta.get("mime_type")
            if not download_url:
                logger.warning("WhatsApp media metadata missing 'url' field (media_id=%s)", media_id)
                return None, None

            # Step 2: fetch the raw bytes
            async with session.get(download_url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(
                        "WhatsApp media download failed (media_id=%s, status=%s)",
                        media_id,
                        resp.status,
                    )
                    return None, None
                raw_bytes = await resp.read()
                # Prefer Content-Type from the download response if metadata lacked it
                if not mime_type:
                    mime_type = resp.headers.get("Content-Type")
                return raw_bytes, mime_type

    except Exception as exc:
        logger.error("Exception downloading WhatsApp media (media_id=%s): %s", media_id, exc)
        return None, None


# Media types that carry a downloadable ``id`` in the Meta webhook envelope.
_MEDIA_MESSAGE_TYPES = frozenset({"image", "audio", "voice", "video", "document", "sticker"})


def flatten_messages(webhook_body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten a Meta webhook envelope into adapter-ready message dicts.

    Meta nests messages under ``entry[].changes[].value.messages[]``. The gateway
    ``WhatsAppAdapter`` expects a flat dict with ``from``, ``chat_id``, ``body``,
    ``id``, ``timestamp``.  Text messages carry a routable ``body``; media messages
    (image/audio/voice/video/document/sticker) carry a ``media_id`` so the webhook
    handler can download them and attach them to the chat pipeline (GH#10267).
    """
    flattened: List[Dict[str, Any]] = []
    for entry in webhook_body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                sender = message.get("from", "")
                msg_type = message.get("type", "text")
                body = message.get("text", {}).get("body", "") if msg_type == "text" else ""

                # Extract the media object id for downloadable types (GH#10267)
                media_id: Optional[str] = None
                if msg_type in _MEDIA_MESSAGE_TYPES:
                    media_obj = message.get(msg_type, {})
                    media_id = media_obj.get("id") if isinstance(media_obj, dict) else None

                flat: Dict[str, Any] = {
                    "platform": "whatsapp",
                    "from": sender,
                    "chat_id": sender,
                    "body": body,
                    "id": message.get("id"),
                    "timestamp": message.get("timestamp", 0),
                    "message_type": msg_type,
                }
                if media_id:
                    flat["media_id"] = media_id
                flattened.append(flat)
    return flattened
