# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Manual MCP Bridge (Issue #3287).

Tests cover:
- Man page lookup with cache hit / cache miss paths
- Graceful handling of unavailable man command
- Documentation index search
- Redis cache write / read helpers
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_man_page_content():
    """Minimal ManPageContent-like object returned by get_man_page_content."""
    content = MagicMock()
    content.command = "ls"
    content.section = "1"
    content.title = "list directory contents"
    content.synopsis = "ls [OPTION]... [FILE]..."
    content.description = "List information about the FILEs."
    content.options = "  -a, --all  do not ignore entries starting with ."
    content.examples = "ls -la /tmp"
    content.see_also = "dir(1), vdir(1)"
    return content


@pytest.fixture
def empty_man_page_content():
    """ManPageContent with no useful data (command not found)."""
    content = MagicMock()
    content.command = "nonexistent_cmd_xyz"
    content.section = "1"
    content.title = ""
    content.synopsis = ""
    content.description = ""
    content.options = ""
    content.examples = ""
    content.see_also = ""
    return content


# ---------------------------------------------------------------------------
# _serialize_man_page
# ---------------------------------------------------------------------------


def test_serialize_man_page_cached_flag():
    from api.manual_mcp import _serialize_man_page

    content = MagicMock()
    content.command = "grep"
    content.section = "1"
    content.title = "search files"
    content.synopsis = "grep [OPTIONS]"
    content.description = "Search for PATTERN in FILE."
    content.options = "-i"
    content.examples = "grep foo bar.txt"
    content.see_also = "awk(1)"

    result = _serialize_man_page(content, cached=True)
    assert result["cached"] is True
    assert result["command"] == "grep"
    assert result["title"] == "search files"


def test_serialize_man_page_not_cached():
    from api.manual_mcp import _serialize_man_page

    content = MagicMock()
    content.command = "cat"
    content.section = "1"
    content.title = "concatenate files"
    content.synopsis = "cat [OPTION]... [FILE]..."
    content.description = "Concatenate FILE(s) to standard output."
    content.options = "-n"
    content.examples = "cat file.txt"
    content.see_also = ""

    result = _serialize_man_page(content, cached=False)
    assert result["cached"] is False


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_format():
    from api.manual_mcp import _cache_key

    key = _cache_key("ls", "1")
    assert "manual_mcp:man:" in key
    assert "ls" in key
    assert "1" in key


# ---------------------------------------------------------------------------
# _get_cached_man_page — cache hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cached_man_page_hit():
    from api.manual_mcp import _get_cached_man_page

    cached_data = {
        "command": "ls",
        "section": "1",
        "title": "list directory contents",
        "synopsis": "",
        "description": "List information",
        "options": "",
        "examples": "",
        "see_also": "",
        "cached": False,  # will be overwritten to True
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(cached_data)

    with patch("api.manual_mcp.get_redis_client", return_value=mock_redis):
        result = await _get_cached_man_page("ls", "1")

    assert result is not None
    assert result["cached"] is True
    assert result["command"] == "ls"


# ---------------------------------------------------------------------------
# _get_cached_man_page — cache miss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cached_man_page_miss():
    from api.manual_mcp import _get_cached_man_page

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    with patch("api.manual_mcp.get_redis_client", return_value=mock_redis):
        result = await _get_cached_man_page("ls", "1")

    assert result is None


# ---------------------------------------------------------------------------
# _get_cached_man_page — Redis unavailable (graceful degradation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_cached_man_page_redis_error():
    from api.manual_mcp import _get_cached_man_page

    with patch("api.manual_mcp.get_redis_client", side_effect=Exception("Redis down")):
        result = await _get_cached_man_page("ls", "1")

    assert result is None  # should not raise


# ---------------------------------------------------------------------------
# _store_man_page_cache — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_man_page_cache_success():
    from api.manual_mcp import _store_man_page_cache

    mock_redis = MagicMock()

    with patch("api.manual_mcp.get_redis_client", return_value=mock_redis):
        await _store_man_page_cache("ls", "1", {"command": "ls"})

    mock_redis.setex.assert_called_once()


# ---------------------------------------------------------------------------
# _store_man_page_cache — Redis error is non-fatal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_man_page_cache_redis_error():
    from api.manual_mcp import _store_man_page_cache

    with patch("api.manual_mcp.get_redis_client", side_effect=Exception("Redis down")):
        # must not raise
        await _store_man_page_cache("ls", "1", {"command": "ls"})


# ---------------------------------------------------------------------------
# _lookup_man_page — cache hit skips subprocess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_man_page_cache_hit():
    from api.manual_mcp import _lookup_man_page

    hit_data = {
        "command": "ls",
        "section": "1",
        "title": "list directory contents",
        "synopsis": "",
        "description": "List information",
        "options": "",
        "examples": "",
        "see_also": "",
        "cached": True,
    }

    with patch("api.manual_mcp._get_cached_man_page", new=AsyncMock(return_value=hit_data)):
        with patch("api.manual_mcp._fetch_man_page") as mock_fetch:
            result = await _lookup_man_page("ls", "1")

    assert result["cached"] is True
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# _lookup_man_page — cache miss → subprocess → stored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_man_page_cache_miss_fetches(sample_man_page_content):
    from api.manual_mcp import _lookup_man_page

    fetched = {
        "command": "ls",
        "section": "1",
        "title": "list directory contents",
        "synopsis": "ls [OPTION]...",
        "description": "List information about the FILEs.",
        "options": "",
        "examples": "",
        "see_also": "",
        "cached": False,
    }

    with patch("api.manual_mcp._get_cached_man_page", new=AsyncMock(return_value=None)):
        with patch("api.manual_mcp._fetch_man_page", new=AsyncMock(return_value=fetched)):
            with patch("api.manual_mcp._store_man_page_cache", new=AsyncMock()) as mock_store:
                result = await _lookup_man_page("ls", "1")

    assert result["title"] == "list directory contents"
    mock_store.assert_called_once()


# ---------------------------------------------------------------------------
# _lookup_man_page — empty result not cached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_man_page_empty_not_cached():
    from api.manual_mcp import _lookup_man_page

    empty = {
        "command": "nonexistent",
        "section": "1",
        "title": "",
        "synopsis": "",
        "description": "",
        "options": "",
        "examples": "",
        "see_also": "",
        "cached": False,
    }

    with patch("api.manual_mcp._get_cached_man_page", new=AsyncMock(return_value=None)):
        with patch("api.manual_mcp._fetch_man_page", new=AsyncMock(return_value=empty)):
            with patch("api.manual_mcp._store_man_page_cache", new=AsyncMock()) as mock_store:
                result = await _lookup_man_page("nonexistent", "1")

    assert result["title"] == ""
    mock_store.assert_not_called()


# ---------------------------------------------------------------------------
# mcp_lookup_man_page endpoint — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_lookup_man_page_success():
    from api.manual_mcp import ManPageRequest, mcp_lookup_man_page

    fetched = {
        "command": "ls",
        "section": "1",
        "title": "list directory contents",
        "synopsis": "ls [OPTION]...",
        "description": "List information",
        "options": "",
        "examples": "",
        "see_also": "",
        "cached": False,
    }

    with patch("api.manual_mcp._lookup_man_page", new=AsyncMock(return_value=fetched)):
        response = await mcp_lookup_man_page(ManPageRequest(command="ls"), current_user={"id": "test"})

    assert response["success"] is True
    assert response["command"] == "ls"
    assert response["error"] is None


# ---------------------------------------------------------------------------
# mcp_lookup_man_page endpoint — command not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_lookup_man_page_not_found():
    from api.manual_mcp import ManPageRequest, mcp_lookup_man_page

    empty = {
        "command": "xyz_notfound",
        "section": "1",
        "title": "",
        "description": "",
    }

    with patch("api.manual_mcp._lookup_man_page", new=AsyncMock(return_value=empty)):
        response = await mcp_lookup_man_page(ManPageRequest(command="xyz_notfound"), current_user={"id": "test"})

    assert response["success"] is False
    assert "xyz_notfound" in response["error"]


# ---------------------------------------------------------------------------
# mcp_lookup_man_page endpoint — exception → graceful error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_lookup_man_page_exception():
    from api.manual_mcp import ManPageRequest, mcp_lookup_man_page

    with patch("api.manual_mcp._lookup_man_page", new=AsyncMock(side_effect=RuntimeError("oops"))):
        response = await mcp_lookup_man_page(ManPageRequest(command="ls"), current_user={"id": "test"})

    assert response["success"] is False
    assert response["result"] is None


# ---------------------------------------------------------------------------
# _query_doc_index — subprocess path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_doc_index_subprocess():
    from api.manual_mcp import _query_doc_index

    man_k_output = "ls (1)               - list directory contents\n" "lsblk (8)            - list block devices\n"

    mock_proc = MagicMock()
    mock_proc.stdout = man_k_output

    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # cache miss

    with patch("api.manual_mcp.get_redis_client", return_value=mock_redis):
        with patch("subprocess.run", return_value=mock_proc):
            results = await _query_doc_index("ls", 10)

    assert len(results) >= 1
    commands = [r["command"] for r in results]
    assert "ls" in commands


# ---------------------------------------------------------------------------
# _query_doc_index — man subprocess failure returns empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_doc_index_subprocess_failure():
    from api.manual_mcp import _query_doc_index

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    with patch("api.manual_mcp.get_redis_client", return_value=mock_redis):
        with patch("subprocess.run", side_effect=Exception("man not found")):
            results = await _query_doc_index("ls", 10)

    assert results == []


# ---------------------------------------------------------------------------
# mcp_search_man_pages endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_search_man_pages_success():
    from api.manual_mcp import ManPageSearchRequest, mcp_search_man_pages

    hits = [{"command": "ls", "section": "1", "summary": "list directory contents"}]

    with patch("api.manual_mcp._query_doc_index", new=AsyncMock(return_value=hits)):
        response = await mcp_search_man_pages(ManPageSearchRequest(query="ls"), current_user={"id": "test"})

    assert response["success"] is True
    assert response["count"] == 1
    assert response["results"][0]["command"] == "ls"


# ---------------------------------------------------------------------------
# mcp_get_doc_index endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_get_doc_index_empty():
    from api.manual_mcp import ManPageSearchRequest, mcp_get_doc_index

    with patch("api.manual_mcp._query_doc_index", new=AsyncMock(return_value=[])):
        response = await mcp_get_doc_index(ManPageSearchRequest(query="nonexistent_xyz"), current_user={"id": "test"})

    assert response["success"] is True
    assert response["count"] == 0
    assert response["results"] == []
