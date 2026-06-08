# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Notion Integration (Issue #4099)

Provides read/write access to Notion workspaces for knowledge base grounding
and task tracking.  Authenticates via a Notion integration token (Bearer).

Base URL: https://api.notion.com/v1
Notion-Version: 2022-06-28

Supported actions:
- list_databases    — enumerate accessible databases
- query_database    — filter/sort rows from a database
- get_page          — retrieve a page and its block content
- create_page       — create a new page inside a database
- update_page       — update page properties
"""

import time
from typing import Any, Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = get_logger(__name__)

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionIntegration(BaseIntegration):
    """Notion workspace integration.

    Authentication: Bearer token (``config.token``)
    Base URL defaults to https://api.notion.com/v1

    Config keys (``IntegrationConfig``):
        token (str): Notion integration secret.
        base_url (str): Override API base URL (optional; for testing).
    """

    def __init__(self, config: IntegrationConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or _NOTION_API_BASE).rstrip("/")

    # ------------------------------------------------------------------
    # BaseIntegration interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> IntegrationHealth:
        """Test Notion connection by fetching the bot user info."""
        start = time.monotonic()
        try:
            result = await self._notion_request("GET", "/users/me")
            latency_ms = (time.monotonic() - start) * 1000

            if result.get("status_code") == 200:
                self._status = IntegrationStatus.CONNECTED
                body = result.get("body", {})
                return IntegrationHealth(
                    provider="notion",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency_ms,
                    message="Connected successfully",
                    details={
                        "bot_id": body.get("id"),
                        "name": body.get("name"),
                        "workspace_name": body.get("bot", {}).get("workspace_name", ""),
                    },
                )
            if result.get("status_code") == 401:
                self._status = IntegrationStatus.UNAUTHORIZED
                return IntegrationHealth(
                    provider="notion",
                    status=IntegrationStatus.UNAUTHORIZED,
                    message="Invalid or expired Notion token",
                )
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="notion",
                status=IntegrationStatus.ERROR,
                message="HTTP %s" % result.get("status_code"),
            )
        except Exception:
            self.logger.exception("Notion connection test failed")
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="notion",
                status=IntegrationStatus.ERROR,
                message="Connection test failed",
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Notion actions."""
        return [
            IntegrationAction(
                name="list_databases",
                description="List all Notion databases accessible to the integration",
                method="POST",
                parameters={},
            ),
            IntegrationAction(
                name="query_database",
                description="Query rows from a Notion database with optional filters",
                method="POST",
                parameters={
                    "database_id": "Notion database ID (UUID)",
                    "filter": "Filter object as per Notion API (optional)",
                    "sorts": "Sort array as per Notion API (optional)",
                    "page_size": "Maximum rows to return (default 100)",
                },
            ),
            IntegrationAction(
                name="get_page",
                description="Retrieve a Notion page and its block children",
                method="GET",
                parameters={"page_id": "Notion page ID (UUID)"},
            ),
            IntegrationAction(
                name="create_page",
                description="Create a new page inside a Notion database",
                method="POST",
                parameters={
                    "database_id": "Parent database ID",
                    "properties": "Page property values as per Notion API",
                    "children": "Block children array (optional)",
                },
            ),
            IntegrationAction(
                name="update_page",
                description="Update properties of an existing Notion page",
                method="PATCH",
                parameters={
                    "page_id": "Notion page ID",
                    "properties": "Property values to update",
                    "archived": "Set to true to archive the page (optional)",
                },
            ),
        ]

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a named action with the provided parameters."""
        action_map: Dict[str, Any] = {
            "list_databases": self._list_databases,
            "query_database": self._query_database,
            "get_page": self._get_page,
            "create_page": self._create_page,
            "update_page": self._update_page,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": "Unknown action: %s" % action}
        try:
            return await handler(params)
        except Exception:
            self.logger.exception("Notion action %s failed", action)
            return {"error": "Action failed"}

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    async def _list_databases(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for all databases shared with the integration."""
        payload: Dict[str, Any] = {"filter": {"value": "database", "property": "object"}}
        result = await self._notion_request("POST", "/search", json_data=payload)
        if result.get("status_code") == 200:
            body = result.get("body", {})
            databases = [
                {
                    "id": db.get("id"),
                    "title": _extract_title(db),
                    "url": db.get("url"),
                    "created_time": db.get("created_time"),
                    "last_edited_time": db.get("last_edited_time"),
                }
                for db in body.get("results", [])
            ]
            return {"databases": databases, "has_more": body.get("has_more", False)}
        return {"error": "HTTP %s" % result.get("status_code")}

    async def _query_database(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query database rows."""
        database_id = params.get("database_id")
        if not database_id:
            return {"error": "database_id required"}

        payload: Dict[str, Any] = {"page_size": int(params.get("page_size", 100))}
        if "filter" in params:
            payload["filter"] = params["filter"]
        if "sorts" in params:
            payload["sorts"] = params["sorts"]

        endpoint = "/databases/%s/query" % database_id
        result = await self._notion_request("POST", endpoint, json_data=payload)
        if result.get("status_code") == 200:
            body = result.get("body", {})
            rows = [
                {
                    "id": page.get("id"),
                    "url": page.get("url"),
                    "created_time": page.get("created_time"),
                    "last_edited_time": page.get("last_edited_time"),
                    "properties": page.get("properties", {}),
                }
                for page in body.get("results", [])
            ]
            return {"rows": rows, "has_more": body.get("has_more", False)}
        return {"error": "HTTP %s" % result.get("status_code")}

    async def _get_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve page metadata and block children."""
        page_id = params.get("page_id")
        if not page_id:
            return {"error": "page_id required"}

        page_result = await self._notion_request("GET", "/pages/%s" % page_id)
        if page_result.get("status_code") != 200:
            return {"error": "HTTP %s" % page_result.get("status_code")}

        blocks_result = await self._notion_request("GET", "/blocks/%s/children?page_size=100" % page_id)
        blocks = []
        if blocks_result.get("status_code") == 200:
            blocks = blocks_result.get("body", {}).get("results", [])

        page_body = page_result.get("body", {})
        return {
            "id": page_body.get("id"),
            "url": page_body.get("url"),
            "title": _extract_title(page_body),
            "created_time": page_body.get("created_time"),
            "last_edited_time": page_body.get("last_edited_time"),
            "properties": page_body.get("properties", {}),
            "blocks": blocks,
        }

    async def _create_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new page inside a database."""
        database_id = params.get("database_id")
        properties = params.get("properties")
        if not database_id or not properties:
            return {"error": "database_id and properties required"}

        payload: Dict[str, Any] = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        if "children" in params:
            payload["children"] = params["children"]

        result = await self._notion_request("POST", "/pages", json_data=payload)
        if result.get("status_code") == 200:
            body = result.get("body", {})
            return {
                "id": body.get("id"),
                "url": body.get("url"),
                "created_time": body.get("created_time"),
            }
        return {"error": "HTTP %s" % result.get("status_code")}

    async def _update_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update page properties or archive status."""
        page_id = params.get("page_id")
        if not page_id:
            return {"error": "page_id required"}

        payload: Dict[str, Any] = {}
        if "properties" in params:
            payload["properties"] = params["properties"]
        if "archived" in params:
            payload["archived"] = bool(params["archived"])

        if not payload:
            return {"error": "No update fields provided"}

        result = await self._notion_request("PATCH", "/pages/%s" % page_id, json_data=payload)
        if result.get("status_code") == 200:
            body = result.get("body", {})
            return {
                "id": body.get("id"),
                "url": body.get("url"),
                "last_edited_time": body.get("last_edited_time"),
            }
        return {"error": "HTTP %s" % result.get("status_code")}

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _notion_request(
        self,
        method: str,
        endpoint: str,
        json_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Notion API."""
        url = "%s%s" % (self._base_url, endpoint)
        headers = {
            "Authorization": "Bearer %s" % self.config.token,
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
# Utilities
# ------------------------------------------------------------------


def _extract_title(obj: Dict[str, Any]) -> str:
    """Extract the plain-text title from a Notion page or database object."""
    # Database title field
    title_array = obj.get("title", [])
    if title_array and isinstance(title_array, list):
        return "".join(t.get("plain_text", "") for t in title_array)

    # Page title via Name property
    props = obj.get("properties", {})
    for prop_name in ("Name", "Title", "title"):
        prop = props.get(prop_name, {})
        title_values = prop.get("title", [])
        if title_values:
            return "".join(t.get("plain_text", "") for t in title_values)

    return ""
