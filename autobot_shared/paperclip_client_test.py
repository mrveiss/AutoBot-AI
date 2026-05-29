# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for autobot_shared.paperclip_client (GH#8944)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from autobot_shared.paperclip_client import (
    PaperclipClient,
    _content_fingerprint,
)


def _make_client(**kwargs) -> PaperclipClient:
    return PaperclipClient(
        api_url="http://paperclip.test",
        api_key="test-key",
        run_id="run-123",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _content_fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_stable():
    assert _content_fingerprint("hello world") == _content_fingerprint("hello world")


def test_fingerprint_normalises_whitespace():
    assert _content_fingerprint("  hello   world  ") == _content_fingerprint("hello world")


def test_fingerprint_different_texts():
    assert _content_fingerprint("foo") != _content_fingerprint("bar")


# ---------------------------------------------------------------------------
# create_issue_idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_issue_returns_existing_when_found():
    existing = {"id": "issue-abc", "title": "Fix 99", "status": "in_progress"}

    client = _make_client()
    with (
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_search_issue_by_title", new_callable=AsyncMock, return_value=existing),
        patch.object(client, "_post_json", new_callable=AsyncMock) as mock_post,
        patch.object(client, "_redis_get", return_value=None),
        patch.object(client, "_redis_set"),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.create_issue_idempotent("co-1", "Fix 99")

    assert result == existing
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_create_issue_creates_when_not_found():
    new_issue = {"id": "issue-new", "title": "Fix 99", "status": "todo"}

    client = _make_client()
    with (
        patch.object(client, "_redis_get", return_value=None),
        patch.object(client, "_redis_set"),
        patch.object(client, "_search_issue_by_title", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=new_issue),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.create_issue_idempotent("co-1", "Fix 99")

    assert result == new_issue


@pytest.mark.asyncio
async def test_create_issue_uses_redis_cache_hit():
    existing = {"id": "issue-cached", "title": "Fix 99", "status": "in_progress"}

    client = _make_client()
    with (
        patch.object(client, "_redis_get", return_value="issue-cached"),
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value=existing),
        patch.object(client, "_search_issue_by_title", new_callable=AsyncMock) as mock_search,
        patch.object(client, "_post_json", new_callable=AsyncMock) as mock_post,
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.create_issue_idempotent("co-1", "Fix 99")

    assert result == existing
    mock_search.assert_not_called()
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_create_issue_falls_through_on_stale_cache():
    new_issue = {"id": "issue-new", "title": "Fix 99", "status": "todo"}

    client = _make_client()
    with (
        patch.object(client, "_redis_get", return_value="issue-stale"),
        patch.object(client, "_redis_delete"),
        patch.object(client, "_redis_set"),
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_search_issue_by_title", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=new_issue),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.create_issue_idempotent("co-1", "Fix 99")

    assert result == new_issue


# ---------------------------------------------------------------------------
# post_comment_idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_comment_suppressed_when_redis_hit():
    client = _make_client()
    with (
        patch.object(client, "_redis_exists", return_value=True),
        patch.object(client, "_post_json", new_callable=AsyncMock) as mock_post,
    ):
        result = await client.post_comment_idempotent("issue-1", "All good.")

    assert result is None
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_post_comment_proceeds_and_sets_dedup_key():
    comment = {"id": "c-1", "body": "All good."}
    client = _make_client()
    with (
        patch.object(client, "_redis_exists", return_value=False),
        patch.object(client, "_redis_set") as mock_set,
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=comment),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.post_comment_idempotent("issue-1", "All good.")

    assert result == comment
    mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_post_comment_dedup_disabled_via_ttl_zero():
    comment = {"id": "c-2", "body": "Always post."}
    client = _make_client()
    with (
        patch.object(client, "_redis_exists") as mock_exists,
        patch.object(client, "_redis_set") as mock_set,
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=comment),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.post_comment_idempotent("issue-1", "Always post.", dedup_ttl=0)

    assert result == comment
    mock_exists.assert_not_called()
    mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# update_status_idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_no_op_when_already_same():
    client = _make_client()
    with (
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value={"id": "i-1", "status": "done"}),
        patch.object(client, "_patch_json", new_callable=AsyncMock) as mock_patch,
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.update_status_idempotent("i-1", "done")

    assert result is None
    mock_patch.assert_not_called()


@pytest.mark.asyncio
async def test_update_status_applies_when_different():
    updated = {"id": "i-1", "status": "done"}
    client = _make_client()
    with (
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value={"id": "i-1", "status": "in_progress"}),
        patch.object(client, "_patch_json", new_callable=AsyncMock, return_value=updated),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.update_status_idempotent("i-1", "done", comment="Done!")

    assert result == updated


@pytest.mark.asyncio
async def test_update_status_applies_when_issue_not_found():
    updated = {"id": "i-1", "status": "done"}
    client = _make_client()
    with (
        patch.object(client, "_get_issue", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_patch_json", new_callable=AsyncMock, return_value=updated),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.update_status_idempotent("i-1", "done")

    assert result == updated


# ---------------------------------------------------------------------------
# Redis fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_issue_continues_when_redis_unavailable():
    new_issue = {"id": "issue-new", "title": "Fix 99", "status": "todo"}
    client = _make_client()
    with (
        patch("autobot_shared.paperclip_client._get_sync_redis", return_value=None),
        patch.object(client, "_search_issue_by_title", new_callable=AsyncMock, return_value=None),
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=new_issue),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.create_issue_idempotent("co-1", "Fix 99")

    assert result == new_issue


@pytest.mark.asyncio
async def test_post_comment_continues_when_redis_unavailable():
    comment = {"id": "c-3", "body": "ok"}
    client = _make_client()
    with (
        patch("autobot_shared.paperclip_client._get_sync_redis", return_value=None),
        patch.object(client, "_post_json", new_callable=AsyncMock, return_value=comment),
        patch.object(client, "_ensure_session", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        result = await client.post_comment_idempotent("issue-1", "ok")

    assert result == comment
