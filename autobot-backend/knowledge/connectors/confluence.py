# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Confluence Knowledge Connector (Issue #10538)

Ingests Atlassian Confluence pages into the AutoBot knowledge base so wiki
content becomes searchable via ``kb.search``.

SCAFFOLD NOTE: This connector is registered only when the
``kb_enterprise_connectors`` feature flag is enabled
(``AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true`` — see
``knowledge/connectors/__init__.py``). No credentials are hardcoded; the
values below are documentation placeholders only.

Config keys (under ``ConnectorConfig.config``):
    base_url (str): Confluence site base URL, e.g.
        "https://your-domain.atlassian.net/wiki". Required.
    username (str): Atlassian account email used for basic auth. Required.
        Canonical ``BasicAuth`` field (Issue #12221) — matches
        ``auth_schema()`` below so the auth-schema validation and
        credential-store encryption path actually secures the field the
        connector reads.
    password (str): Atlassian API token, used as the HTTP Basic password.
        Required. Canonical ``BasicAuth`` field (Issue #12221).
    space_keys (list[str]): Confluence space keys to sync. Required.
    page_size (int): Pages per query batch. Default 25.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from autobot_shared.auth import BasicAuth
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from knowledge.connectors.base import AbstractConnector, RetryableError, instance_host_egress
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)


@ConnectorRegistry.register("confluence")
class ConfluenceConnector(AbstractConnector):
    """Knowledge connector that pulls pages from Confluence spaces.

    Each page becomes one KB fact keyed by
    ``confluence:{connector_id}:page:{page_id}``. Change detection compares
    the page's ``version.when`` timestamp against a Redis-cached value so
    only edited pages are re-fetched.
    """

    connector_type = "confluence"
    # Issue #4421: needs an Atlassian API token — tier 2 (credentialed).
    tier = 2
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        """Confluence Cloud uses HTTP Basic auth (email + API token) — Issue #8145."""
        return BasicAuth

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata (Issue #8147)."""
        return {
            "type": "object",
            "required": ["confluence_page_id", "confluence_space_key"],
            "properties": {
                "confluence_page_id": {"type": "string", "description": "Confluence page ID"},
                "confluence_space_key": {"type": "string", "description": "Confluence space key"},
                "confluence_title": {"type": "string", "description": "Page title"},
                "confluence_url": {"type": "string", "description": "Web URL to the page"},
                "version_when": {"type": "string", "description": "ISO-8601 timestamp of the last edit"},
            },
        }

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._email: str = cfg.get("username", "")
        self._api_token: str = cfg.get("password", "")
        self._base_url: str = cfg.get("base_url", "").rstrip("/")
        self._space_keys: List[str] = cfg.get("space_keys", [])
        self._page_size: int = int(cfg.get("page_size", 25))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify credentials by fetching the accessible spaces list."""
        result = await self._get("/rest/api/space?limit=1")
        healthy = result.get("status_code") == 200
        if not healthy:
            self.logger.warning("Confluence test_connection failed: HTTP %s", result.get("status_code"))
        return healthy

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every page across all configured spaces."""
        sources: List[SourceInfo] = []
        for space_key in self._space_keys:
            pages = await self._list_pages(space_key)
            for page in pages:
                sources.append(_page_to_source_info(self.config.connector_id, page, space_key))
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch storage-format body text for the Confluence page in *source_id*."""
        page_id = _parse_page_id(source_id)
        if page_id is None:
            self.logger.error("Malformed Confluence source_id: %s", source_id)
            return None

        result = await self._get("/rest/api/content/%s?expand=body.storage,space,version" % page_id)
        if result.get("status_code") != 200:
            self.logger.error("Failed to fetch Confluence page %s: HTTP %s", page_id, result.get("status_code"))
            return None

        page = result.get("body", {})
        title = page.get("title", "")
        html = page.get("body", {}).get("storage", {}).get("value", "")
        text = _html_to_text(html)
        if title:
            text = "%s\n\n%s" % (title, text)

        version_when = page.get("version", {}).get("when", "")
        if version_when:
            await self._store_ts(page_id, version_when)

        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "confluence_page_id": page_id,
                "confluence_space_key": page.get("space", {}).get("key", ""),
                "confluence_title": title,
                "confluence_url": _page_web_url(self._base_url, page),
                "version_when": version_when,
                "connector_type": self.connector_type,
            },
        )

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        """Return ChangeInfo for pages created/edited since *since*."""
        changes: List[ChangeInfo] = []
        for space_key in self._space_keys:
            pages = await self._list_pages(space_key)
            for page in pages:
                page_id = page.get("id", "")
                change = await self._classify_change(page_id, since)
                if change:
                    changes.append(change)
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_pages(self, space_key: str) -> List[Dict[str, Any]]:
        """Fetch all pages in a space (handles pagination via ``start``)."""
        pages: List[Dict[str, Any]] = []
        start = 0
        while True:
            path = "/rest/api/content?spaceKey=%s&type=page&limit=%d&start=%d&expand=version" % (
                space_key,
                self._page_size,
                start,
            )
            result = await self.fetch_with_retry(lambda p=path: self._get(p))
            if result.get("status_code") != 200:
                self.logger.error(
                    "Failed to list Confluence pages for space %s: HTTP %s",
                    space_key,
                    result.get("status_code"),
                )
                break
            body = result.get("body", {})
            batch = body.get("results", [])
            pages.extend(batch)
            if len(batch) < self._page_size:
                break
            start += self._page_size
        return pages

    async def _classify_change(self, page_id: str, since: Optional[datetime]) -> Optional[ChangeInfo]:
        """Return ChangeInfo when the page is new or has a newer version than stored."""
        if since is None:
            return ChangeInfo(
                source_id=_build_source_id(self.config.connector_id, page_id),
                change_type="added",
                timestamp=now_utc(),
                details={"page_id": page_id},
            )

        result = await self._get("/rest/api/content/%s?expand=version" % page_id)
        if result.get("status_code") != 200:
            return None
        version_when = result.get("body", {}).get("version", {}).get("when", "")

        stored = await self._load_ts(page_id)
        if stored is None or version_when > stored:
            change_type = "added" if stored is None else "modified"
            await self._store_ts(page_id, version_when)
            return ChangeInfo(
                source_id=_build_source_id(self.config.connector_id, page_id),
                change_type=change_type,
                timestamp=now_utc(),
                details={"page_id": page_id, "version_when": version_when},
            )
        return None

    async def _get(self, path: str) -> Dict[str, Any]:
        """Make an authenticated GET request to the Confluence REST API."""
        url = "%s%s" % (self._base_url, path)
        auth = aiohttp.BasicAuth(login=self._email, password=self._api_token)
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            # Operator-configured instance host — private opt-in applies (#13625).
            async with get_http_client().tracked_request(
                "GET",
                url,
                auth=auth,
                timeout=timeout,
                suppress_error_log=True,
                guard_egress=instance_host_egress(),
            ) as resp:
                if resp.status == 429:
                    raise RetryableError("Confluence rate-limited", status_code=429)
                if resp.status >= 500:
                    raise RetryableError("Confluence server error %d" % resp.status, status_code=resp.status)
                body = await resp.json(content_type=None)
                return {"status_code": resp.status, "body": body}
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("Confluence request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level helpers (no state)
# ---------------------------------------------------------------------------
# Issue #12659: _load_ts()/_store_ts() moved to AbstractConnector — this
# connector's Redis prefix ("connector:confluence:ts:") matches the base
# class default derived from connector_type, so no override is needed.


def _build_source_id(connector_id: str, page_id: str) -> str:
    return "confluence:%s:page:%s" % (connector_id, page_id)


def _parse_page_id(source_id: str) -> Optional[str]:
    parts = source_id.split(":")
    # Format: confluence:{connector_id}:page:{page_id}
    if len(parts) != 4 or parts[2] != "page":
        return None
    return parts[3]


def _page_to_source_info(connector_id: str, page: Dict[str, Any], space_key: str) -> SourceInfo:
    page_id = page.get("id", "")
    version = page.get("version", {})
    updated_raw = version.get("when", "")
    try:
        last_modified = parse_utc_iso(updated_raw)
    except (ValueError, AttributeError):
        last_modified = now_utc()
    return SourceInfo(
        source_id=_build_source_id(connector_id, page_id),
        name=page.get("title", ""),
        path="",
        content_type="text/plain",
        size_bytes=0,
        last_modified=last_modified,
        metadata={"space_key": space_key, "page_id": page_id, "version_when": updated_raw},
    )


def _page_web_url(base_url: str, page: Dict[str, Any]) -> str:
    webui = page.get("_links", {}).get("webui", "")
    return "%s%s" % (base_url, webui) if webui else ""


def _html_to_text(html: str) -> str:
    """Strip Confluence storage-format HTML/XML markup down to plain text."""
    import re

    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


__all__ = ["ConfluenceConnector"]
