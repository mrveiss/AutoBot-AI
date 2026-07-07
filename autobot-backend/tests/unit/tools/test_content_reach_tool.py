# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Part B — unified content_reach agent tool (#10932)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: build a ToolRegistry instance without real __init__
# ---------------------------------------------------------------------------


def _make_registry():
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()
    return registry


# ---------------------------------------------------------------------------
# B3 — content_reach in get_available_tools()
# ---------------------------------------------------------------------------


def test_content_reach_in_get_available_tools() -> None:
    """'content_reach' appears in get_available_tools()."""
    with patch("chat_workflow.tool_handler.BROWSER_TOOL_NAMES", frozenset()):
        registry = _make_registry()
        tools = registry.get_available_tools()

    assert "content_reach" in tools


# ---------------------------------------------------------------------------
# B2 — dispatch key "contentreach" resolves
# ---------------------------------------------------------------------------


def test_dispatch_contentreach_resolves() -> None:
    """Normalized 'contentreach' resolves to content_reach handler."""
    registry = _make_registry()
    handler = registry._get_tool_handler("contentreach")
    assert handler is not None


# ---------------------------------------------------------------------------
# B4 — CONTENT_REACH_SCHEMA in _BUILTIN_TOOL_SCHEMAS with 5-source enum
# ---------------------------------------------------------------------------


def test_content_reach_schema_in_builtin_tool_schemas() -> None:
    """'content_reach' key is present in _BUILTIN_TOOL_SCHEMAS."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS

    assert "content_reach" in _BUILTIN_TOOL_SCHEMAS


def test_content_reach_schema_has_five_source_enum() -> None:
    """CONTENT_REACH_SCHEMA source enum lists all 5 sources."""
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS

    schema = _BUILTIN_TOOL_SCHEMAS["content_reach"]
    enum_values = set(schema["properties"]["source"]["enum"])
    assert enum_values == {"web_search", "web_page", "youtube", "reddit", "social"}


# ---------------------------------------------------------------------------
# B1 — content_reach method: success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_reach_success() -> None:
    """content_reach returns status='success' and includes result text."""
    from content_reach.base import ContentResult
    from source_attribution import SourceType

    registry = _make_registry()

    mock_result = ContentResult(
        success=True,
        source_type=SourceType.WEB_SEARCH,
        backend_used="ddgs",
        text="Some search content",
        url="",
    )
    mock_registry = MagicMock()
    mock_registry.fetch = AsyncMock(return_value=mock_result)

    with patch("content_reach.registry.get_content_source_registry", return_value=mock_registry):
        result = await registry.content_reach("web_search", query="test query")

    assert result["status"] == "success"
    assert "Some search content" in result["result"]
    assert result["tool_name"] == "content_reach"


# ---------------------------------------------------------------------------
# B1 — content_reach method: unsuccessful ContentResult (success=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_reach_unsuccessful_result() -> None:
    """content_reach returns status='error' when ContentResult.success is False."""
    from content_reach.base import ContentResult
    from source_attribution import SourceType

    registry = _make_registry()

    mock_result = ContentResult.failure(SourceType.WEB_SEARCH, "backend timeout")
    mock_registry = MagicMock()
    mock_registry.fetch = AsyncMock(return_value=mock_result)

    with patch("content_reach.registry.get_content_source_registry", return_value=mock_registry):
        result = await registry.content_reach("web_search", query="test query")

    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# B1 + C3 — SSRF guard: private URL blocked at tool boundary, fetch NOT called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_content_reach_blocks_private_url() -> None:
    """content_reach blocks a private IP URL and does NOT call registry.fetch."""
    registry = _make_registry()

    mock_registry = MagicMock()
    mock_registry.fetch = AsyncMock()

    with patch("content_reach.registry.get_content_source_registry", return_value=mock_registry):
        # Use the real ensure_public_url path but monkeypatch the underlying
        # is_public_url_async so we control what "non-public" means in tests.
        with patch(
            "content_reach._url_guard._is_public_url_async",
            new=AsyncMock(return_value=False),
        ):
            result = await registry.content_reach(
                "web_page",
                url="http://169.254.169.254/latest/meta-data/",
            )

    assert result["status"] == "error"
    mock_registry.fetch.assert_not_called()
