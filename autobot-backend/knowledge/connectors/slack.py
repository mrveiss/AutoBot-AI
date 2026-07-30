# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Slack Knowledge Connector (Issue #10538)

Ingests Slack channel/thread history into the AutoBot knowledge base so chat
discussions become searchable via ``kb.search``. Complements
``integrations/slack_integration.py``, which only pushes outbound
notifications/approvals and does not ingest history.

SCAFFOLD NOTE: This connector is registered only when the
``kb_enterprise_connectors`` feature flag is enabled
(``AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true`` — see
``knowledge/connectors/__init__.py``). No credentials are hardcoded; the
values below are documentation placeholders only.

Config keys (under ``ConnectorConfig.config``):
    token (str): Slack bot token (``xoxb-...``) with
        ``channels:history``, ``groups:history`` and ``channels:read``
        scopes. Required. Canonical ``BearerAuth`` field (Issue #12221) —
        matches ``auth_schema()`` below so the auth-schema validation and
        credential-store encryption path actually secures the field the
        connector reads.
    channel_ids (list[str]): Slack channel IDs to sync. Required.
    sync_threads (bool): Also ingest thread replies. Default True.
    oldest (str): Slack ``ts`` lower bound for the initial sync. Default "0".
    page_size (int): Messages per page (Slack API ``limit``). Default 200.
    slack_api_base (str): Override API base URL (optional; for testing).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from autobot_shared.auth import BearerAuth
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector, RetryableError
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_SLACK_API_BASE = "https://slack.com/api"

# Issue #12659: _load_ts()/_store_ts() moved to AbstractConnector — this
# connector's Redis prefix ("connector:slack:ts:") matches the base class
# default derived from connector_type, so no override is needed.


@ConnectorRegistry.register("slack")
class SlackConnector(AbstractConnector):
    """Knowledge connector that ingests Slack channel/thread history.

    Each top-level message becomes one KB fact keyed by
    ``slack:{connector_id}:channel:{channel_id}:ts:{message_ts}``. Thread
    replies are appended to the parent message's content when
    ``sync_threads`` is enabled, so a thread ingests as a single fact.

    Change detection compares each channel's newest message ``ts`` against a
    Redis-cached checkpoint so only new/updated messages are re-fetched.
    """

    connector_type = "slack"
    # Issue #4421: needs a Slack bot token — free to create, so tier 1.
    tier = 1
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        """Slack requires a bearer bot token — Issue #8145."""
        return BearerAuth

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata (Issue #8147)."""
        return {
            "type": "object",
            "required": ["slack_channel_id", "slack_message_ts"],
            "properties": {
                "slack_channel_id": {"type": "string", "description": "Slack channel ID"},
                "slack_message_ts": {"type": "string", "description": "Message timestamp (Slack ts)"},
                "slack_permalink": {"type": "string", "description": "Permalink to the message"},
                "slack_author": {"type": "string", "description": "Author user ID"},
                "thread_reply_count": {"type": "integer", "description": "Number of thread replies included"},
            },
        }

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._channel_ids: List[str] = cfg.get("channel_ids", [])
        self._sync_threads: bool = cfg.get("sync_threads", True)
        self._oldest: str = cfg.get("oldest", "0")
        self._page_size: int = int(cfg.get("page_size", 200))
        self._base_url: str = cfg.get("slack_api_base", _SLACK_API_BASE).rstrip("/")

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify the bot token via ``auth.test``."""
        result = await self._slack_post("/auth.test")
        healthy = result.get("status_code") == 200 and result.get("body", {}).get("ok") is True
        if not healthy:
            self.logger.warning("Slack test_connection failed: %s", result.get("body", {}).get("error"))
        return healthy

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every top-level message in every configured channel."""
        sources: List[SourceInfo] = []
        for channel_id in self._channel_ids:
            messages = await self._history(channel_id, oldest=self._oldest)
            for message in messages:
                sources.append(_message_to_source_info(self.config.connector_id, channel_id, message))
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch a message (and optionally its thread) for *source_id*."""
        channel_id, ts = _parse_source_id(source_id)
        if channel_id is None:
            self.logger.error("Malformed Slack source_id: %s", source_id)
            return None

        messages = await self._history(channel_id, oldest=ts, latest=ts, inclusive=True, limit=1)
        if not messages:
            self.logger.error("Slack message not found: channel=%s ts=%s", channel_id, ts)
            return None

        message = messages[0]
        reply_count = 0
        text_parts = [_message_to_text(message)]
        if self._sync_threads and message.get("thread_ts") == ts and message.get("reply_count", 0) > 0:
            replies = await self._replies(channel_id, ts)
            reply_count = len(replies)
            text_parts.extend(_message_to_text(r) for r in replies)

        await self._store_ts(channel_id, ts)
        return ContentResult(
            source_id=source_id,
            content="\n\n".join(p for p in text_parts if p.strip()),
            content_type="text/plain",
            metadata={
                "slack_channel_id": channel_id,
                "slack_message_ts": ts,
                "slack_permalink": message.get("permalink", ""),
                "slack_author": message.get("user", ""),
                "thread_reply_count": reply_count,
                "connector_type": self.connector_type,
            },
        )

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        """Return ChangeInfo for messages posted/updated after *since*."""
        changes: List[ChangeInfo] = []
        for channel_id in self._channel_ids:
            oldest = self._since_to_ts(since)
            stored = await self._load_ts(channel_id)
            messages = await self._history(channel_id, oldest=oldest)
            newest_ts = stored
            for message in messages:
                ts = message.get("ts", "")
                change_type = "added" if stored is None or ts > stored else "modified"
                changes.append(
                    ChangeInfo(
                        source_id=_build_source_id(self.config.connector_id, channel_id, ts),
                        change_type=change_type,
                        timestamp=now_utc(),
                        details={"channel_id": channel_id, "ts": ts},
                    )
                )
                if newest_ts is None or ts > newest_ts:
                    newest_ts = ts
            if newest_ts is not None and newest_ts != stored:
                await self._store_ts(channel_id, newest_ts)
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _since_to_ts(since: Optional[datetime]) -> str:
        """Convert a datetime to a Slack ``ts`` lower bound string."""
        if since is None:
            return "0"
        return "%f" % since.timestamp()

    async def _history(
        self,
        channel_id: str,
        oldest: str = "0",
        latest: Optional[str] = None,
        inclusive: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch messages from ``conversations.history``, handling pagination."""
        messages: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        page_limit = limit or self._page_size

        while True:
            payload: Dict[str, Any] = {
                "channel": channel_id,
                "oldest": oldest,
                "limit": page_limit,
            }
            if latest is not None:
                payload["latest"] = latest
            if inclusive:
                payload["inclusive"] = "true"
            if cursor:
                payload["cursor"] = cursor

            result = await self.fetch_with_retry(lambda p=payload: self._slack_post("/conversations.history", p))
            body = result.get("body", {})
            if result.get("status_code") != 200 or not body.get("ok"):
                self.logger.error(
                    "Slack conversations.history failed for %s: %s",
                    channel_id,
                    body.get("error"),
                )
                break

            messages.extend(body.get("messages", []))
            if limit is not None:
                break
            cursor = body.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break

        return messages

    async def _replies(self, channel_id: str, thread_ts: str) -> List[Dict[str, Any]]:
        """Fetch thread replies (excluding the parent) via ``conversations.replies``."""
        result = await self._slack_post(
            "/conversations.replies",
            {"channel": channel_id, "ts": thread_ts, "limit": self._page_size},
        )
        body = result.get("body", {})
        if result.get("status_code") != 200 or not body.get("ok"):
            self.logger.warning("Slack conversations.replies failed for %s/%s", channel_id, thread_ts)
            return []
        return [m for m in body.get("messages", []) if m.get("ts") != thread_ts]

    async def _slack_post(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an authenticated POST request to the Slack Web API."""
        url = "%s%s" % (self._base_url, endpoint)
        headers = {
            "Authorization": "Bearer %s" % self._token,
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with get_http_client().tracked_request(
                "POST",
                url,
                headers=headers,
                json=json_data or {},
                timeout=timeout,
                suppress_error_log=True,
            ) as resp:
                if resp.status == 429:
                    raise RetryableError("Slack rate-limited", status_code=429)
                if resp.status >= 500:
                    raise RetryableError("Slack server error %d" % resp.status, status_code=resp.status)
                body = await resp.json(content_type=None)
                return {"status_code": resp.status, "body": body}
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("Slack request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {"ok": False, "error": str(exc)}}


# ---------------------------------------------------------------------------
# Module-level helpers (no state)
# ---------------------------------------------------------------------------


def _build_source_id(connector_id: str, channel_id: str, ts: str) -> str:
    return "slack:%s:channel:%s:ts:%s" % (connector_id, channel_id, ts)


def _parse_source_id(source_id: str) -> tuple:
    parts = source_id.split(":")
    # Format: slack:{connector_id}:channel:{channel_id}:ts:{ts}
    if len(parts) != 6 or parts[2] != "channel" or parts[4] != "ts":
        return None, None
    return parts[3], parts[5]


def _message_to_source_info(connector_id: str, channel_id: str, message: Dict[str, Any]) -> SourceInfo:
    ts = message.get("ts", "")
    try:
        last_modified = datetime.fromtimestamp(float(ts), tz=now_utc().tzinfo)
    except (ValueError, TypeError):
        last_modified = now_utc()
    return SourceInfo(
        source_id=_build_source_id(connector_id, channel_id, ts),
        name=_message_to_text(message)[:80],
        path=message.get("permalink", ""),
        content_type="text/plain",
        size_bytes=0,
        last_modified=last_modified,
        metadata={"channel_id": channel_id, "ts": ts, "user": message.get("user", "")},
    )


def _message_to_text(message: Dict[str, Any]) -> str:
    author = message.get("user", "unknown")
    text = message.get("text", "")
    return "[%s] %s" % (author, text)


__all__ = ["SlackConnector"]
