# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Jira Knowledge Connector (Issue #10538)

Ingests Jira issues (with comments) into the AutoBot knowledge base so
tracker content becomes searchable via ``kb.search``.

SCAFFOLD NOTE: This connector is registered only when the
``kb_enterprise_connectors`` feature flag is enabled
(``AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS=true`` — see
``knowledge/connectors/__init__.py``). No credentials are hardcoded; the
values below are documentation placeholders only.

Config keys (under ``ConnectorConfig.config``):
    base_url (str): Jira site base URL, e.g.
        "https://your-domain.atlassian.net". Required.
    username (str): Atlassian account email used for basic auth. Required.
        Canonical ``BasicAuth`` field (Issue #12221) — matches
        ``auth_schema()`` below so the auth-schema validation and
        credential-store encryption path actually secures the field the
        connector reads.
    password (str): Atlassian API token, used as the HTTP Basic password.
        Required. Canonical ``BasicAuth`` field (Issue #12221).
    project_keys (list[str]): Jira project keys to sync. Required.
    jql (str): Optional JQL override; when set, replaces the
        project-key-derived query entirely.
    page_size (int): Issues per search batch. Default 50.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from autobot_shared.auth import BasicAuth
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from knowledge.connectors.base import AbstractConnector, RetryableError
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

# Issue #12659: _load_ts()/_store_ts() moved to AbstractConnector — this
# connector's Redis prefix ("connector:jira:ts:") matches the base class
# default derived from connector_type, so no override is needed.


@ConnectorRegistry.register("jira")
class JiraConnector(AbstractConnector):
    """Knowledge connector that pulls issues (and comments) from Jira projects.

    Each issue becomes one KB fact keyed by
    ``jira:{connector_id}:issue:{issue_key}``, with comments concatenated
    into the issue body. Change detection uses JQL ``updated >=`` filtering
    plus a Redis-cached ``updated`` timestamp per issue.
    """

    connector_type = "jira"
    # Issue #4421: needs an Atlassian API token — tier 2 (credentialed).
    tier = 2
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        """Jira Cloud uses HTTP Basic auth (email + API token) — Issue #8145."""
        return BasicAuth

    @classmethod
    def output_schema(cls) -> Dict[str, Any]:
        """Return JSONSchema for ContentResult.metadata (Issue #8147)."""
        return {
            "type": "object",
            "required": ["jira_issue_key", "jira_project_key"],
            "properties": {
                "jira_issue_key": {"type": "string", "description": "Jira issue key, e.g. ABC-123"},
                "jira_project_key": {"type": "string", "description": "Jira project key"},
                "jira_summary": {"type": "string", "description": "Issue summary/title"},
                "jira_status": {"type": "string", "description": "Current workflow status"},
                "jira_url": {"type": "string", "description": "Web URL to the issue"},
                "updated": {"type": "string", "description": "ISO-8601 last-updated timestamp"},
                "comment_count": {"type": "integer", "description": "Number of comments included"},
            },
        }

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._email: str = cfg.get("username", "")
        self._api_token: str = cfg.get("password", "")
        self._base_url: str = cfg.get("base_url", "").rstrip("/")
        self._project_keys: List[str] = cfg.get("project_keys", [])
        self._jql_override: str = cfg.get("jql", "")
        self._page_size: int = int(cfg.get("page_size", 50))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Verify credentials via ``/rest/api/3/myself``."""
        result = await self._get("/rest/api/3/myself")
        healthy = result.get("status_code") == 200
        if not healthy:
            self.logger.warning("Jira test_connection failed: HTTP %s", result.get("status_code"))
        return healthy

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo for every issue matching the configured JQL."""
        issues = await self._search(self._build_jql())
        return [_issue_to_source_info(self.config.connector_id, issue) for issue in issues]

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch issue fields and comments for the Jira issue in *source_id*."""
        issue_key = _parse_issue_key(source_id)
        if issue_key is None:
            self.logger.error("Malformed Jira source_id: %s", source_id)
            return None

        result = await self._get("/rest/api/3/issue/%s" % issue_key)
        if result.get("status_code") != 200:
            self.logger.error("Failed to fetch Jira issue %s: HTTP %s", issue_key, result.get("status_code"))
            return None

        issue = result.get("body", {})
        fields = issue.get("fields", {})
        comments = fields.get("comment", {}).get("comments", [])
        text = _issue_to_text(issue_key, fields, comments)

        updated = fields.get("updated", "")
        if updated:
            await self._store_ts(issue_key, updated)

        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "jira_issue_key": issue_key,
                "jira_project_key": fields.get("project", {}).get("key", ""),
                "jira_summary": fields.get("summary", ""),
                "jira_status": fields.get("status", {}).get("name", ""),
                "jira_url": "%s/browse/%s" % (self._base_url, issue_key),
                "updated": updated,
                "comment_count": len(comments),
                "connector_type": self.connector_type,
            },
        )

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        """Return ChangeInfo for issues created/updated since *since*."""
        jql = self._build_jql(since=since)
        issues = await self._search(jql)
        changes: List[ChangeInfo] = []
        for issue in issues:
            issue_key = issue.get("key", "")
            updated = issue.get("fields", {}).get("updated", "")
            change = await self._classify_change(issue_key, updated, since)
            if change:
                changes.append(change)
        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_jql(self, since: Optional[datetime] = None) -> str:
        """Build the JQL query for discovery/change-detection searches."""
        if self._jql_override:
            return self._jql_override
        keys = ",".join(self._project_keys)
        jql = "project in (%s)" % keys if keys else "order by updated desc"
        if since is not None:
            jql += ' AND updated >= "%s"' % since.strftime("%Y-%m-%d %H:%M")
        return jql

    async def _classify_change(self, issue_key: str, updated: str, since: Optional[datetime]) -> Optional[ChangeInfo]:
        """Return ChangeInfo when the issue is new or newer than its stored checkpoint."""
        if since is None:
            return ChangeInfo(
                source_id=_build_source_id(self.config.connector_id, issue_key),
                change_type="added",
                timestamp=now_utc(),
                details={"issue_key": issue_key, "updated": updated},
            )

        stored = await self._load_ts(issue_key)
        if stored is None or updated > stored:
            change_type = "added" if stored is None else "modified"
            await self._store_ts(issue_key, updated)
            return ChangeInfo(
                source_id=_build_source_id(self.config.connector_id, issue_key),
                change_type=change_type,
                timestamp=now_utc(),
                details={"issue_key": issue_key, "updated": updated},
            )
        return None

    async def _search(self, jql: str) -> List[Dict[str, Any]]:
        """Run a JQL search, handling pagination via ``startAt``."""
        issues: List[Dict[str, Any]] = []
        start_at = 0
        while True:
            payload = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": self._page_size,
                "fields": ["summary", "status", "project", "updated", "comment"],
            }
            result = await self.fetch_with_retry(lambda p=payload: self._post("/rest/api/3/search", p))
            if result.get("status_code") != 200:
                self.logger.error("Jira search failed: HTTP %s", result.get("status_code"))
                break
            body = result.get("body", {})
            batch = body.get("issues", [])
            issues.extend(batch)
            total = body.get("total", len(issues))
            start_at += len(batch)
            if not batch or start_at >= total:
                break
        return issues

    async def _get(self, path: str) -> Dict[str, Any]:
        return await self._request("GET", path)

    async def _post(self, path: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", path, json_data=json_data)

    async def _request(self, method: str, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an authenticated request to the Jira REST API."""
        url = "%s%s" % (self._base_url, path)
        auth = aiohttp.BasicAuth(login=self._email, password=self._api_token)
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with get_http_client().tracked_request(
                method, url, auth=auth, json=json_data, timeout=timeout, suppress_error_log=True
            ) as resp:
                if resp.status == 429:
                    raise RetryableError("Jira rate-limited", status_code=429)
                if resp.status >= 500:
                    raise RetryableError("Jira server error %d" % resp.status, status_code=resp.status)
                body = await resp.json(content_type=None)
                return {"status_code": resp.status, "body": body}
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("Jira request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level helpers (no state)
# ---------------------------------------------------------------------------


def _build_source_id(connector_id: str, issue_key: str) -> str:
    return "jira:%s:issue:%s" % (connector_id, issue_key)


def _parse_issue_key(source_id: str) -> Optional[str]:
    parts = source_id.split(":")
    # Format: jira:{connector_id}:issue:{issue_key}
    if len(parts) != 4 or parts[2] != "issue":
        return None
    return parts[3]


def _issue_to_source_info(connector_id: str, issue: Dict[str, Any]) -> SourceInfo:
    issue_key = issue.get("key", "")
    fields = issue.get("fields", {})
    updated_raw = fields.get("updated", "")
    try:
        last_modified = parse_utc_iso(updated_raw)
    except (ValueError, AttributeError):
        last_modified = now_utc()
    return SourceInfo(
        source_id=_build_source_id(connector_id, issue_key),
        name=fields.get("summary", ""),
        path="",
        content_type="text/plain",
        size_bytes=0,
        last_modified=last_modified,
        metadata={
            "project_key": fields.get("project", {}).get("key", ""),
            "issue_key": issue_key,
            "updated": updated_raw,
        },
    )


def _issue_to_text(issue_key: str, fields: Dict[str, Any], comments: List[Dict[str, Any]]) -> str:
    parts = [
        "Issue %s: %s" % (issue_key, fields.get("summary", "")),
        "Status: %s" % fields.get("status", {}).get("name", ""),
        "Project: %s" % fields.get("project", {}).get("key", ""),
        "Updated: %s" % fields.get("updated", ""),
    ]
    description = _adf_to_text(fields.get("description"))
    if description.strip():
        parts.append("")
        parts.append(description.strip())
    for comment in comments:
        body = _adf_to_text(comment.get("body"))
        if body.strip():
            author = comment.get("author", {}).get("displayName", "unknown")
            parts.append("")
            parts.append("Comment by %s: %s" % (author, body.strip()))
    return "\n".join(parts)


def _adf_to_text(node: Any) -> str:
    """Extract plain text from a Jira Atlassian Document Format (ADF) node.

    Falls back to str() for legacy plain-text description/comment bodies.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return str(node)

    parts: List[str] = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content", []) or []:
        parts.append(_adf_to_text(child))
    return " ".join(p for p in parts if p)


__all__ = ["JiraConnector"]
