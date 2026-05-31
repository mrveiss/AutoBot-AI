# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for knowledge.connectors.gitlab — Issue #9011.

Tests GitLabConnector and GiteaConnector: connection testing, source
discovery, change detection, content fetching, and pagination.

All HTTP I/O (aiohttp) and Redis calls are mocked so tests run
without network or Redis access.
"""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.gitlab import (
    GitLabConnector,
    GiteaConnector,
    _is_text_file,
    _issue_to_text,
)
from knowledge.connectors.models import ConnectorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gl_config(**extra) -> ConnectorConfig:
    cfg = {
        "token": "glpat-test",
        "gitlab_url": "https://gitlab.example.com",
        "project_ids": ["42"],
        "sync_issues": True,
        "sync_merge_requests": True,
        "sync_files": False,
    }
    cfg.update(extra)
    return ConnectorConfig(
        connector_id="test-gl",
        connector_type="gitlab",
        name="Test GitLab",
        config=cfg,
    )


def _gitea_config(**extra) -> ConnectorConfig:
    cfg = {
        "token": "gttoken",
        "gitea_url": "https://gitea.example.com",
        "repos": ["alice/my-repo"],
        "sync_issues": True,
        "sync_merge_requests": True,
        "sync_files": False,
    }
    cfg.update(extra)
    return ConnectorConfig(
        connector_id="test-gitea",
        connector_type="gitea",
        name="Test Gitea",
        config=cfg,
    )


def _mock_response(status: int, payload: Any, content_type: str = "application/json") -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.content_type = content_type
    resp.json = AsyncMock(return_value=payload)
    resp.text = AsyncMock(return_value=payload if isinstance(payload, str) else "")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# _is_text_file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("README.md", True),
        ("main.py", True),
        ("app.ts", True),
        ("image.png", False),
        ("archive.zip", False),
        ("Makefile", False),
        ("docs/guide.rst", True),
    ],
)
def test_is_text_file(path, expected):
    assert _is_text_file(path) == expected


# ---------------------------------------------------------------------------
# _issue_to_text
# ---------------------------------------------------------------------------


def test_issue_to_text_basic():
    issue = {
        "iid": 3,
        "title": "Fix login bug",
        "state": "opened",
        "author": {"username": "alice"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "labels": [{"name": "bug"}, {"name": "priority::high"}],
        "description": "Login fails on mobile.",
    }
    text = _issue_to_text(issue)
    assert "Fix login bug" in text
    assert "alice" in text
    assert "bug" in text
    assert "Login fails on mobile." in text


def test_issue_to_text_pr_flag():
    issue = {
        "iid": 5,
        "title": "Add feature",
        "state": "merged",
        "author": {"username": "bob"},
        "created_at": "",
        "updated_at": "",
    }
    text = _issue_to_text(issue, is_pr=True)
    assert "Merge Request" in text


# ---------------------------------------------------------------------------
# GitLabConnector — test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_test_connection_ok():
    connector = GitLabConnector(_gl_config())
    resp = _mock_response(200, {"id": 1, "username": "bot"})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        result = await connector.test_connection()
    assert result is True


@pytest.mark.asyncio
async def test_gitlab_test_connection_fail():
    connector = GitLabConnector(_gl_config())
    resp = _mock_response(401, {"message": "401 Unauthorized"})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        result = await connector.test_connection()
    assert result is False


# ---------------------------------------------------------------------------
# GitLabConnector — discover_sources / change detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_discover_sources_issues_and_mrs():
    connector = GitLabConnector(_gl_config())

    issues_page = [
        {
            "iid": 1,
            "title": "Bug",
            "state": "opened",
            "author": {"username": "u"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "web_url": "https://gl/p/1",
        },
    ]
    mrs_page = [
        {
            "iid": 2,
            "title": "Feature",
            "state": "merged",
            "author": {"username": "v"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-03T00:00:00Z",
            "web_url": "https://gl/p/2",
        },
    ]

    async def fake_gl_get(path: str) -> Dict[str, Any]:
        if "merge_requests" in path:
            return {"status_code": 200, "body": mrs_page if "page=1" in path else []}
        return {"status_code": 200, "body": issues_page if "page=1" in path else []}

    with patch.object(connector, "_gl_get", side_effect=fake_gl_get):
        sources = await connector.discover_sources()

    titles = [s.name for s in sources]
    assert "Bug" in titles
    assert "Feature" in titles


@pytest.mark.asyncio
async def test_gitlab_detect_changes_full_sync():
    connector = GitLabConnector(_gl_config())

    async def fake_gl_get(path: str) -> Dict[str, Any]:
        if "merge_requests" in path:
            return {
                "status_code": 200,
                "body": [
                    {"iid": 10, "title": "MR", "updated_at": "2026-02-01T00:00:00Z"},
                ],
            }
        return {
            "status_code": 200,
            "body": [
                {"iid": 5, "title": "Issue", "updated_at": "2026-01-15T00:00:00Z"},
            ],
        }

    with (
        patch.object(connector, "_gl_get", side_effect=fake_gl_get),
        patch("knowledge.connectors.gitlab._load_ts", return_value=None),
        patch("knowledge.connectors.gitlab._store_ts"),
    ):
        changes = await connector.detect_changes(since=None)

    source_ids = [c.source_id for c in changes]
    assert any("issue:5" in sid for sid in source_ids)
    assert any("mr:10" in sid for sid in source_ids)
    assert all(c.change_type == "added" for c in changes)


# ---------------------------------------------------------------------------
# GitLabConnector — fetch_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_fetch_issue_content():
    connector = GitLabConnector(_gl_config())
    source_id = "gitlab:test-gl:project:42:issue:7"
    issue_data = {
        "iid": 7,
        "title": "Crash on start",
        "state": "opened",
        "author": {"username": "alice"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "description": "App crashes when starting.",
        "web_url": "https://gl/p/issues/7",
        "labels": [],
    }

    async def fake_gl_get(path: str) -> Dict[str, Any]:
        return {"status_code": 200, "body": issue_data}

    with (
        patch.object(connector, "_gl_get", side_effect=fake_gl_get),
        patch("knowledge.connectors.gitlab._store_ts"),
    ):
        result = await connector.fetch_content(source_id)

    assert result is not None
    assert result.source_id == source_id
    assert "Crash on start" in result.content
    assert result.metadata["gitlab_project_id"] == "42"
    assert result.metadata["gitlab_issue_iid"] == "7"


@pytest.mark.asyncio
async def test_gitlab_fetch_mr_content():
    connector = GitLabConnector(_gl_config())
    source_id = "gitlab:test-gl:project:42:mr:3"
    mr_data = {
        "iid": 3,
        "title": "Add dark mode",
        "state": "merged",
        "author": {"username": "bob"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-05T00:00:00Z",
        "description": "Implements dark mode toggle.",
        "web_url": "https://gl/p/mr/3",
        "labels": [],
    }

    async def fake_gl_get(path: str) -> Dict[str, Any]:
        return {"status_code": 200, "body": mr_data}

    with (
        patch.object(connector, "_gl_get", side_effect=fake_gl_get),
        patch("knowledge.connectors.gitlab._store_ts"),
    ):
        result = await connector.fetch_content(source_id)

    assert result is not None
    assert "Merge Request" in result.content
    assert result.metadata["gitlab_mr_iid"] == "3"


@pytest.mark.asyncio
async def test_gitlab_fetch_content_bad_source_id():
    connector = GitLabConnector(_gl_config())
    result = await connector.fetch_content("gitlab:bad")
    assert result is None


# ---------------------------------------------------------------------------
# GiteaConnector — test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_test_connection_ok():
    connector = GiteaConnector(_gitea_config())
    resp = _mock_response(200, {"id": 1, "login": "alice"})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        result = await connector.test_connection()
    assert result is True


@pytest.mark.asyncio
async def test_gitea_test_connection_fail():
    connector = GiteaConnector(_gitea_config())
    resp = _mock_response(401, {"message": "Unauthorized"})
    session = _mock_session(resp)
    with patch("aiohttp.ClientSession", return_value=session):
        result = await connector.test_connection()
    assert result is False


# ---------------------------------------------------------------------------
# GiteaConnector — repo parsing
# ---------------------------------------------------------------------------


def test_gitea_repo_parsing_valid():
    connector = GiteaConnector(_gitea_config(repos=["owner/repo", "org/project"]))
    assert len(connector._repos) == 2
    assert connector._repos[0] == ("owner", "repo")
    assert connector._repos[1] == ("org", "project")


def test_gitea_repo_parsing_invalid_skipped():
    connector = GiteaConnector(_gitea_config(repos=["bad-no-slash", "ok/repo"]))
    assert len(connector._repos) == 1
    assert connector._repos[0] == ("ok", "repo")


# ---------------------------------------------------------------------------
# GiteaConnector — discover_sources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_discover_sources():
    connector = GiteaConnector(_gitea_config())

    issues = [
        {
            "number": 1,
            "title": "Bug",
            "state": "open",
            "updated_at": "2026-01-01T00:00:00Z",
            "html_url": "https://gitea/alice/my-repo/issues/1",
            "user": {"login": "alice"},
            "created_at": "2026-01-01T00:00:00Z",
        },
    ]
    prs = [
        {
            "number": 2,
            "title": "PR title",
            "state": "open",
            "updated_at": "2026-01-01T00:00:00Z",
            "html_url": "https://gitea/alice/my-repo/pulls/2",
            "user": {"login": "alice"},
            "created_at": "2026-01-01T00:00:00Z",
        },
    ]

    async def fake_gitea_get(path: str) -> Dict[str, Any]:
        if "pulls" in path:
            return {"status_code": 200, "body": prs if "page=1" in path else []}
        return {"status_code": 200, "body": issues if "page=1" in path else []}

    with patch.object(connector, "_gitea_get", side_effect=fake_gitea_get):
        sources = await connector.discover_sources()

    titles = [s.name for s in sources]
    assert "Bug" in titles
    assert "PR title" in titles


# ---------------------------------------------------------------------------
# GiteaConnector — fetch_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitea_fetch_issue_content():
    connector = GiteaConnector(_gitea_config())
    source_id = "gitea:test-gitea:repo:alice:my-repo:issue:1"
    issue_data = {
        "number": 1,
        "title": "Memory leak",
        "state": "open",
        "user": {"login": "alice"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-10T00:00:00Z",
        "body": "Memory grows unbounded.",
        "html_url": "https://gitea/alice/my-repo/issues/1",
        "labels": [],
    }

    async def fake_gitea_get(path: str) -> Dict[str, Any]:
        return {"status_code": 200, "body": issue_data}

    with (
        patch.object(connector, "_gitea_get", side_effect=fake_gitea_get),
        patch("knowledge.connectors.gitlab._store_ts"),
    ):
        result = await connector.fetch_content(source_id)

    assert result is not None
    assert "Memory leak" in result.content
    assert result.metadata["gitea_owner"] == "alice"
    assert result.metadata["gitea_repo"] == "my-repo"
    assert result.metadata["issue_number"] == "1"


@pytest.mark.asyncio
async def test_gitea_fetch_content_bad_source_id():
    connector = GiteaConnector(_gitea_config())
    result = await connector.fetch_content("gitea:bad:short")
    assert result is None


# ---------------------------------------------------------------------------
# Source ID format
# ---------------------------------------------------------------------------


def test_gitlab_source_id_format():
    connector = GitLabConnector(_gl_config())
    sid = connector._source_id("99", "issue", "5")
    assert sid == "gitlab:test-gl:project:99:issue:5"


def test_gitea_source_id_format():
    connector = GiteaConnector(_gitea_config())
    sid = connector._source_id("alice", "my-repo", "pr", "7")
    assert sid == "gitea:test-gitea:repo:alice:my-repo:pr:7"
