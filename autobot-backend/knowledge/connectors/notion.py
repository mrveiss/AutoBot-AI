# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Notion Knowledge Connector (Issue #4099)

Ingests Notion database rows and page content into the AutoBot knowledge base.
Supports incremental sync via last-edited-time comparison and Redis-backed
content-hash caching to avoid re-ingesting unchanged pages.
Issue #8145: Declares auth_schema() -> BearerAuth so the API layer can validate
the required ``token`` field before persisting the config.

Config keys (under ``ConnectorConfig.config``):
    token (str): Notion integration secret.
    database_ids (list[str]): Database IDs to sync. Required.
    page_size (int): Rows per query batch. Default 100.
    notion_api_base (str): Override API base URL (optional; for testing).
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List

import aiohttp

from autobot_shared.auth import BearerAuth
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_REDIS_HASH_KEY_PREFIX = "connector:notion:hash:"


@ConnectorRegistry.register("notion")
class NotionConnector(AbstractConnector):
    """Knowledge connector that pulls content from Notion databases.

    Each database row (page) becomes a knowledge source.  Page block text is
    concatenated and stored as a single KB fact keyed by the page ID.

    Change detection compares ``last_edited_time`` from the Notion API against
    a Redis-cached value so network-only calls drive sync decisions.
    """

    connector_type = "notion"
    # Issue #4421: needs a free Notion integration token (config.token).
    tier = 1

    @classmethod
    def auth_schema(cls) -> type:
        """Notion requires a bearer token (integration secret) — Issue #8145."""
        return BearerAuth

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._database_ids: List[str] = cfg.get("database_ids", [])
        self._page_size: int = int(cfg.get("page_size", 100))
        self._base_url: str = cfg.get("notion_api_base", _NOTION_API_BASE).rstrip("/")

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify Notion credentials by fetching the bot user."""
        result = await self._notion_request("GET", "/users/me")
        healthy = result.get("status_code") == 200
        if not healthy:
            self.logger.warning("Notion test_connection failed: HTTP %s", result.get("status_code"))
        return healthy

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every accessible page across all configured databases."""
        sources: List[SourceInfo] = []
        for db_id in self._database_ids:
            pages = await self._query_all_pages(db_id)
            for page in pages:
                sources.append(_page_to_source_info(page, db_id))
        return sources

    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Fetch block text for the Notion page identified by *source_id* (page ID)."""
        page_result = await self._notion_request("GET", "/pages/%s" % source_id)
        if page_result.get("status_code") != 200:
            self.logger.error(
                "Failed to fetch Notion page %s: HTTP %s",
                source_id,
                page_result.get("status_code"),
            )
            return None

        page_body = page_result.get("body", {})
        blocks_result = await self._notion_request("GET", "/blocks/%s/children?page_size=100" % source_id)
        blocks = []
        if blocks_result.get("status_code") == 200:
            blocks = blocks_result.get("body", {}).get("results", [])

        text = _blocks_to_text(blocks)
        title = _extract_title(page_body)
        if title:
            text = "%s\n\n%s" % (title, text)

        # Update stored hash so future incremental syncs are accurate
        if text.strip():
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            await self._store_hash(source_id, content_hash)

        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "notion_page_id": source_id,
                "notion_page_url": page_body.get("url", ""),
                "notion_title": title,
                "last_edited_time": page_body.get("last_edited_time", ""),
                "connector_id": self.config.connector_id,
            },
        )

    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Return ChangeInfo for pages added or modified since *since*.

        When *since* is None all pages are reported as 'added'.  Otherwise the
        page's ``last_edited_time`` is compared against the stored Redis hash
        timestamp.
        """
        changes: List[ChangeInfo] = []
        for db_id in self._database_ids:
            pages = await self._query_all_pages(db_id)
            for page in pages:
                page_id = page.get("id", "")
                last_edited = page.get("last_edited_time", "")
                change = await self._classify_change(page_id, last_edited, since)
                if change:
                    changes.append(change)
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _query_all_pages(self, database_id: str) -> List[Dict[str, Any]]:
        """Fetch all page rows from a Notion database (handles pagination)."""
        pages: List[Dict[str, Any]] = []
        endpoint = "/databases/%s/query" % database_id
        payload: Dict[str, Any] = {"page_size": self._page_size}
        cursor: str | None = None

        while True:
            if cursor:
                payload["start_cursor"] = cursor
            result = await self._notion_request("POST", endpoint, json_data=payload)
            if result.get("status_code") != 200:
                self.logger.error(
                    "Failed to query Notion database %s: HTTP %s",
                    database_id,
                    result.get("status_code"),
                )
                break

            body = result.get("body", {})
            pages.extend(body.get("results", []))
            if not body.get("has_more"):
                break
            cursor = body.get("next_cursor")

        return pages

    async def _classify_change(
        self,
        page_id: str,
        last_edited: str,
        since: datetime | None,
    ) -> ChangeInfo | None:
        """Return ChangeInfo when the page is new or was edited after *since*."""
        if since is None:
            return ChangeInfo(
                source_id=page_id,
                change_type="added",
                timestamp=now_utc(),
                details={"last_edited_time": last_edited},
            )

        stored_ts = await self._load_timestamp(page_id)
        if stored_ts is None or last_edited > stored_ts:
            change_type = "added" if stored_ts is None else "modified"
            await self._store_timestamp(page_id, last_edited)
            return ChangeInfo(
                source_id=page_id,
                change_type=change_type,
                timestamp=now_utc(),
                details={"last_edited_time": last_edited},
            )
        return None

    async def _load_timestamp(self, page_id: str) -> str | None:
        """Load last-known edited timestamp from Redis."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = get_redis_client(database="knowledge")
            key = "%sts:%s" % (_REDIS_HASH_KEY_PREFIX, page_id)
            value = redis.get(key)
            if hasattr(value, "__await__"):
                value = await value
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value
        except Exception as exc:
            self.logger.warning("Redis load_timestamp failed for %s: %s", page_id, exc)
            return None

    async def _store_timestamp(self, page_id: str, timestamp: str) -> None:
        """Persist last-edited timestamp for *page_id* in Redis."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = get_redis_client(database="knowledge")
            key = "%sts:%s" % (_REDIS_HASH_KEY_PREFIX, page_id)
            result = redis.set(key, timestamp)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            self.logger.warning("Redis store_timestamp failed for %s: %s", page_id, exc)

    async def _store_hash(self, page_id: str, content_hash: str) -> None:
        """Persist content hash for *page_id* in Redis."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = get_redis_client(database="knowledge")
            key = "%s%s" % (_REDIS_HASH_KEY_PREFIX, page_id)
            result = redis.set(key, content_hash)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            self.logger.warning("Redis store_hash failed for %s: %s", page_id, exc)

    async def _notion_request(
        self,
        method: str,
        endpoint: str,
        json_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Make an authenticated Notion API request."""
        url = "%s%s" % (self._base_url, endpoint)
        headers = {
            "Authorization": "Bearer %s" % self._token,
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers, json=json_data) as resp:
                    body = await resp.json(content_type=None)
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Notion request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}


# ------------------------------------------------------------------
# Module-level helpers (no state)
# ------------------------------------------------------------------


def _page_to_source_info(page: Dict[str, Any], database_id: str) -> SourceInfo:
    """Build a SourceInfo from a Notion page object."""
    page_id = page.get("id", "")
    last_edited = page.get("last_edited_time", "")
    try:
        last_modified = parse_utc_iso(last_edited)
    except (ValueError, AttributeError):
        last_modified = now_utc()

    return SourceInfo(
        source_id=page_id,
        name=_extract_title(page),
        path=page.get("url", ""),
        content_type="text/plain",
        size_bytes=0,
        last_modified=last_modified,
        metadata={
            "notion_database_id": database_id,
            "notion_page_url": page.get("url", ""),
            "last_edited_time": last_edited,
        },
    )


def _blocks_to_text(blocks: List[Dict[str, Any]]) -> str:
    """Convert Notion block children to plain text."""
    parts: List[str] = []
    for block in blocks:
        block_type = block.get("type", "")
        block_data = block.get(block_type, {})
        rich_text = block_data.get("rich_text", [])
        if rich_text:
            parts.append("".join(rt.get("plain_text", "") for rt in rich_text))
    return "\n".join(parts)


def _extract_title(obj: Dict[str, Any]) -> str:
    """Extract the plain-text title from a Notion page or database object."""
    title_array = obj.get("title", [])
    if title_array and isinstance(title_array, list):
        return "".join(t.get("plain_text", "") for t in title_array)

    props = obj.get("properties", {})
    for prop_name in ("Name", "Title", "title"):
        prop = props.get(prop_name, {})
        title_values = prop.get("title", [])
        if title_values:
            return "".join(t.get("plain_text", "") for t in title_values)

    return ""
