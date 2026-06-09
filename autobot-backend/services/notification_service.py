# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multi-Channel Notification Service (#2157)

Dispatches workflow event notifications over four channels:
    EMAIL    - SMTP outbound email
    SLACK    - Slack incoming webhook POST
    WEBHOOK  - Arbitrary HTTP POST to a caller-supplied URL
    IN_APP   - Redis-backed notification store polled by the UI

Usage::

    from services.notification_service import (
from autobot_shared.logging_manager import get_logger
        NotificationService,
        NotificationChannel,
        NotificationEvent,
    )

    svc = NotificationService()
    await svc.send(
        event=NotificationEvent.WORKFLOW_COMPLETED,
        workflow_id="wf-abc",
        payload={"status": "ok", "duration_s": 12},
        config=my_notif_config,
    )
"""

import json
import smtplib
import time
import uuid
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from string import Template
from typing import Any, Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_7_DAYS

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

_NOTIFICATIONS_REDIS_DB = "main"
_NOTIFICATION_TTL_SECONDS = TTL_7_DAYS


class NotificationChannel(str, Enum):
    """Supported delivery channels for notifications."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    TELEGRAM = "telegram"  # MVA-2075


class NotificationEvent(str, Enum):
    """Workflow lifecycle events that can trigger notifications."""

    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    STEP_FAILED = "step_failed"
    APPROVAL_NEEDED = "approval_needed"
    SERVICE_FAILED = "service_failed"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NotificationConfig:
    """
    Per-workflow notification routing configuration.

    channels maps each NotificationEvent value to a list of NotificationChannel
    values that should receive notifications when that event fires.

    templates optionally overrides the default message template for a given
    event.  Template strings use Python's string.Template substitution syntax
    (``$variable`` / ``${variable}``).
    """

    workflow_id: str
    channels: Dict[str, List[str]] = field(default_factory=dict)
    templates: Dict[str, str] = field(default_factory=dict)

    # Channel-specific addresses / URLs
    email_recipients: List[str] = field(default_factory=list)
    slack_webhook_url: str | None = None
    webhook_url: str | None = None
    # user_id for IN_APP delivery
    user_id: str | None = None
    # Telegram chat_id for TELEGRAM delivery (MVA-2075)
    telegram_chat_id: str | None = None


# ---------------------------------------------------------------------------
# Default templates
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATES: Dict[str, str] = {
    NotificationEvent.WORKFLOW_COMPLETED: ("Workflow '$workflow_id' completed successfully."),
    NotificationEvent.WORKFLOW_FAILED: ("Workflow '$workflow_id' FAILED. Error: $error"),
    NotificationEvent.STEP_FAILED: ("Step '$step_name' in workflow '$workflow_id' failed. Error: $error"),
    NotificationEvent.APPROVAL_NEEDED: ("Workflow '$workflow_id' is waiting for approval at step '$step_name'."),
    NotificationEvent.SERVICE_FAILED: (
        "Service '$service' on '$hostname' transitioned $prev_state -> $new_state. $error_context"
    ),
}


# ---------------------------------------------------------------------------
# In-app notification store (Redis-backed)
# ---------------------------------------------------------------------------


class NotificationStore:
    """
    Redis-backed store for in-app notifications.

    Key schema:
        notifications:{user_id}          — Redis list (JSON entries, newest first)
        notification:{notification_id}   — Redis hash (individual record)

    Each notification JSON record::

        {
            "id": "<uuid>",
            "user_id": "<str>",
            "event": "<NotificationEvent.value>",
            "workflow_id": "<str>",
            "message": "<str>",
            "timestamp": <float>,
            "read": false
        }
    """

    _LIST_KEY_PREFIX = "notifications"
    _RECORD_KEY_PREFIX = "notification"

    def _list_key(self, user_id: str) -> str:
        return f"{self._LIST_KEY_PREFIX}:{user_id}"

    def _record_key(self, notification_id: str) -> str:
        return f"{self._RECORD_KEY_PREFIX}:{notification_id}"

    async def store(
        self,
        user_id: str,
        event: str,
        workflow_id: str,
        message: str,
    ) -> str | None:
        """
        Persist a notification for *user_id* and return the notification ID.

        Returns None if Redis is unavailable.
        """
        notification_id = str(uuid.uuid4())
        record: Dict[str, Any] = {
            "id": notification_id,
            "user_id": user_id,
            "event": event,
            "workflow_id": workflow_id,
            "message": message,
            "timestamp": time.time(),
            "read": False,
        }
        serialised = json.dumps(record)
        try:
            client = await get_redis_client(async_client=True, database=_NOTIFICATIONS_REDIS_DB)
            if client is None:
                logger.warning(
                    "Redis unavailable — in-app notification not stored (user=%s)",
                    user_id,
                )
                return None
            list_key = self._list_key(user_id)
            record_key = self._record_key(notification_id)
            await client.lpush(list_key, serialised)
            await client.expire(list_key, _NOTIFICATION_TTL_SECONDS)
            await client.set(record_key, serialised, ex=_NOTIFICATION_TTL_SECONDS)
            logger.debug("Stored in-app notification %s for user %s", notification_id, user_id)
            return notification_id
        except Exception as exc:
            logger.error("Failed to store in-app notification for user %s: %s", user_id, exc)
            return None

    async def list(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return the most recent *limit* notifications for *user_id* (newest first).

        Returns an empty list if Redis is unavailable or no notifications exist.
        """
        try:
            client = await get_redis_client(async_client=True, database=_NOTIFICATIONS_REDIS_DB)
            if client is None:
                logger.warning("Redis unavailable — cannot list notifications (user=%s)", user_id)
                return []
            raw_items = await client.lrange(self._list_key(user_id), 0, limit - 1)
            results: List[Dict[str, Any]] = []
            for raw in raw_items:
                try:
                    results.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError) as parse_err:
                    logger.warning("Skipping malformed notification record: %s", parse_err)
            return results
        except Exception as exc:
            logger.error("Failed to list notifications for user %s: %s", user_id, exc)
            return []

    async def mark_read(self, notification_id: str) -> bool:
        """
        Mark a notification as read by updating its ``read`` flag.

        The list entry is NOT patched (it is append-only); only the individual
        record hash is updated so reads can be checked by ID.

        Returns True on success, False if the notification was not found or Redis
        is unavailable.
        """
        try:
            client = await get_redis_client(async_client=True, database=_NOTIFICATIONS_REDIS_DB)
            if client is None:
                logger.warning(
                    "Redis unavailable — cannot mark notification %s as read",
                    notification_id,
                )
                return False
            record_key = self._record_key(notification_id)
            raw = await client.get(record_key)
            if raw is None:
                logger.warning("Notification %s not found in store", notification_id)
                return False
            record: Dict[str, Any] = json.loads(raw)
            record["read"] = True
            await client.set(record_key, json.dumps(record), ex=_NOTIFICATION_TTL_SECONDS)
            logger.debug("Marked notification %s as read", notification_id)
            return True
        except Exception as exc:
            logger.error("Failed to mark notification %s as read: %s", notification_id, exc)
            return False


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class NotificationService:
    """
    Multi-channel notification dispatcher for workflow lifecycle events.

    Channels are dispatched concurrently via asyncio-compatible helpers.
    Individual channel failures are caught and logged so that one broken
    channel cannot block others.
    """

    def __init__(self, store: NotificationStore | None = None) -> None:
        self._store = store or NotificationStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send(
        self,
        event: NotificationEvent,
        workflow_id: str,
        payload: Dict[str, Any],
        config: NotificationConfig,
    ) -> None:
        """
        Dispatch notifications for *event* on all channels configured in *config*.

        Channel failures are caught individually so that a broken SMTP server,
        for example, does not prevent Slack or in-app delivery.
        """
        channels_for_event: List[str] = config.channels.get(event.value, [])
        if not channels_for_event:
            logger.debug(
                "No channels configured for event %s on workflow %s",
                event.value,
                workflow_id,
            )
            return

        message = self.render_template(event.value, {**payload, "workflow_id": workflow_id})
        logger.info(
            "Dispatching event=%s workflow=%s channels=%s",
            event.value,
            workflow_id,
            channels_for_event,
        )

        for channel_str in channels_for_event:
            try:
                channel = NotificationChannel(channel_str)
            except ValueError:
                logger.warning("Unknown notification channel '%s' — skipping", channel_str)
                continue

            try:
                await self._dispatch(channel, event, workflow_id, message, payload, config)
            except Exception as exc:
                logger.error(
                    "Channel %s dispatch failed for event=%s workflow=%s: %s",
                    channel.value,
                    event.value,
                    workflow_id,
                    exc,
                )

    def render_template(self, event: str, context: Dict[str, Any]) -> str:
        """
        Render the message template for *event* with *context* values.

        Falls back to the built-in default template when no custom template is
        registered.  Missing substitution keys are left as-is (``safe_substitute``).
        """
        raw = _DEFAULT_TEMPLATES.get(event, "AutoBot notification: event=$event workflow=$workflow_id")
        tmpl = Template(raw)
        return tmpl.safe_substitute({"event": event, **{str(k): str(v) for k, v in context.items()}})

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        channel: NotificationChannel,
        event: NotificationEvent,
        workflow_id: str,
        message: str,
        payload: Dict[str, Any],
        config: NotificationConfig,
    ) -> None:
        """Route delivery to the correct channel handler."""
        if channel == NotificationChannel.EMAIL:
            for recipient in config.email_recipients:
                await self._send_email(
                    to=recipient,
                    subject=f"[AutoBot] {event.value.replace('_', ' ').title()} — {workflow_id}",
                    body=message,
                )
        elif channel == NotificationChannel.SLACK:
            if config.slack_webhook_url:
                await self._send_slack(config.slack_webhook_url, message)
            else:
                logger.warning(
                    "Slack channel requested but slack_webhook_url not set (workflow=%s)",
                    workflow_id,
                )
        elif channel == NotificationChannel.WEBHOOK:
            if config.webhook_url:
                await self._send_webhook(
                    config.webhook_url,
                    {
                        "event": event.value,
                        "workflow_id": workflow_id,
                        "message": message,
                        "payload": payload,
                    },
                )
            else:
                logger.warning(
                    "Webhook channel requested but webhook_url not set (workflow=%s)",
                    workflow_id,
                )
        elif channel == NotificationChannel.IN_APP:
            if config.user_id:
                await self._send_in_app(
                    user_id=config.user_id,
                    event=event.value,
                    workflow_id=workflow_id,
                    message=message,
                )
            else:
                logger.warning(
                    "IN_APP channel requested but user_id not set (workflow=%s)",
                    workflow_id,
                )
        elif channel == NotificationChannel.TELEGRAM:
            if config.telegram_chat_id:
                await self._send_telegram(
                    chat_id=config.telegram_chat_id,
                    message=message,
                )
            else:
                logger.warning(
                    "Telegram channel requested but telegram_chat_id not set (workflow=%s)",
                    workflow_id,
                )

    # ------------------------------------------------------------------
    # Channel implementations
    # ------------------------------------------------------------------

    async def _send_email(self, to: str, subject: str, body: str) -> None:
        """
        Send a plain-text email via SMTP.

        SMTP settings are read from the SSOT config environment variables:
            AUTOBOT_SMTP_HOST   (default: localhost)
            AUTOBOT_SMTP_PORT   (default: 587)
            AUTOBOT_SMTP_USER   (default: empty — anonymous)
            AUTOBOT_SMTP_PASSWORD (default: empty)
            AUTOBOT_SMTP_FROM   (default: autobot@localhost)
            AUTOBOT_SMTP_TLS    (default: true)
        """

        smtp_host = config.smtp_host
        smtp_port = int(config.smtp_port)
        smtp_user = config.smtp_user
        smtp_password = config.smtp_password
        smtp_from = config.smtp_from
        use_tls = config.smtp_tls.lower() != "false"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            if use_tls:
                from autobot_shared.tls import get_internal_tls_context

                context = get_internal_tls_context()  # #6702: canonical SSL context
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    if smtp_user:
                        server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_from, [to], msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    if smtp_user:
                        server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_from, [to], msg.as_string())
            logger.info("Email sent to %s (subject=%s)", to, subject)
        except smtplib.SMTPException as exc:
            logger.error("SMTP error sending email to %s: %s", to, exc)
            raise
        except OSError as exc:
            logger.error("Network error sending email to %s: %s", to, exc)
            raise

    async def _send_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """
        POST *payload* as JSON to *url*.

        Raises on non-2xx response or network error so the caller's error
        handler can log and continue.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AutoBot-Notifier/1.0",
        }
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status >= 400:
                        body_text = await resp.text()
                        logger.error(
                            "Webhook POST to %s returned HTTP %d: %s",
                            url,
                            resp.status,
                            body_text[:200],
                        )
                        resp.raise_for_status()
                    logger.info("Webhook delivered to %s (status=%d)", url, resp.status)
        except aiohttp.ClientError as exc:
            logger.error("HTTP client error delivering webhook to %s: %s", url, exc)
            raise

    async def _send_slack(self, webhook_url: str, message: str) -> None:
        """
        Post *message* to a Slack channel via an incoming webhook URL.

        Slack incoming webhooks accept ``{"text": "..."}`` JSON payloads.
        """
        await self._send_webhook(webhook_url, {"text": message})

    async def _send_telegram(self, chat_id: str, message: str) -> None:
        """
        Send *message* to a Telegram chat via TelegramBotService (MVA-2075).

        Args:
            chat_id: Telegram chat ID
            message: Notification message text
        """
        try:
            from services.telegram_bot_service import TelegramBotService

            service = await TelegramBotService.from_redis()
            await service.send_message(
                chat_id=chat_id,
                text=message,
            )
            logger.info(f"Sent Telegram notification to chat {chat_id}")
        except Exception as exc:
            logger.error(f"Failed to send Telegram notification to chat {chat_id}: {exc}")
            raise

    async def _send_in_app(
        self,
        user_id: str,
        event: str,
        workflow_id: str,
        message: str,
    ) -> None:
        """Persist an in-app notification via the NotificationStore."""
        notification_id = await self._store.store(
            user_id=user_id,
            event=event,
            workflow_id=workflow_id,
            message=message,
        )
        if notification_id:
            logger.debug(
                "In-app notification %s stored for user %s (workflow=%s)",
                notification_id,
                user_id,
                workflow_id,
            )
        else:
            logger.warning(
                "In-app notification could not be stored for user %s (workflow=%s)",
                user_id,
                workflow_id,
            )
