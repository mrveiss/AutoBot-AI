# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for GitHubIntegration (Issue #4097)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.github_integration import GitHubIntegration


def _make_integration(token: str = "ghp_test") -> GitHubIntegration:
    cfg = IntegrationConfig(name="github", provider="github", token=token)
    return GitHubIntegration(cfg)


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_healthy() -> None:
    integration = _make_integration()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"login": "testuser", "id": 1})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_resp)

    with patch("integrations.github_integration.aiohttp.ClientSession", return_value=mock_session):
        health = await integration.test_connection()

    assert health.status == IntegrationStatus.HEALTHY
    assert "testuser" in health.message
    assert integration.status == IntegrationStatus.CONNECTED


@pytest.mark.asyncio
async def test_test_connection_unauthorized() -> None:
    integration = _make_integration(token="bad_token")
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = MagicMock(return_value=mock_resp)

    with patch("integrations.github_integration.aiohttp.ClientSession", return_value=mock_session):
        health = await integration.test_connection()

    assert health.status == IntegrationStatus.UNHEALTHY
    assert integration.status == IntegrationStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_test_connection_network_error() -> None:
    import aiohttp as _aiohttp

    integration = _make_integration()

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = MagicMock(side_effect=_aiohttp.ClientConnectionError("refused"))

    with patch("integrations.github_integration.aiohttp.ClientSession", return_value=mock_session):
        health = await integration.test_connection()

    assert health.status == IntegrationStatus.UNHEALTHY
    assert integration.status == IntegrationStatus.ERROR


# ---------------------------------------------------------------------------
# get_available_actions
# ---------------------------------------------------------------------------


def test_get_available_actions_complete() -> None:
    integration = _make_integration()
    actions = integration.get_available_actions()
    names = {a.name for a in actions}
    expected = {
        "get_pull_request",
        "list_pull_requests",
        "get_pull_request_diff",
        "list_pr_review_comments",
        "post_pr_comment",
        "submit_pr_review",
        "get_issue",
        "list_issues",
        "get_repository",
        "list_commits",
        "get_commit",
        "get_repository_tree",
        "get_file_contents",
    }
    assert expected == names


# ---------------------------------------------------------------------------
# execute_action dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_action_unknown_raises() -> None:
    integration = _make_integration()
    with pytest.raises(ValueError, match="Unknown GitHub action"):
        await integration.execute_action("nonexistent", {})


@pytest.mark.asyncio
async def test_list_pull_requests() -> None:
    integration = _make_integration()
    pr_data = [{"number": 1, "title": "Fix bug"}]
    integration._get = AsyncMock(return_value=pr_data)

    result = await integration.execute_action(
        "list_pull_requests",
        {"owner": "mrveiss", "repo": "AutoBot-AI", "state": "open"},
    )

    assert result["count"] == 1
    assert result["pull_requests"] == pr_data
    integration._get.assert_called_once()


@pytest.mark.asyncio
async def test_get_pull_request() -> None:
    integration = _make_integration()
    pr_data = {"number": 42, "title": "Add feature"}
    integration._get = AsyncMock(return_value=pr_data)

    result = await integration.execute_action(
        "get_pull_request",
        {"owner": "mrveiss", "repo": "AutoBot-AI", "pull_number": 42},
    )

    assert result["pull_request"] == pr_data


@pytest.mark.asyncio
async def test_list_issues_filters_prs() -> None:
    integration = _make_integration()
    raw = [
        {"number": 1, "title": "Bug"},
        {"number": 2, "title": "PR", "pull_request": {"url": "..."}},
    ]
    integration._get = AsyncMock(return_value=raw)

    result = await integration.execute_action(
        "list_issues", {"owner": "mrveiss", "repo": "AutoBot-AI"}
    )

    assert result["count"] == 1
    assert result["issues"][0]["number"] == 1


@pytest.mark.asyncio
async def test_post_pr_comment() -> None:
    integration = _make_integration()
    comment_data = {"id": 99, "body": "Looks good"}
    integration._post = AsyncMock(return_value=comment_data)

    result = await integration.execute_action(
        "post_pr_comment",
        {
            "owner": "mrveiss",
            "repo": "AutoBot-AI",
            "pull_number": 10,
            "body": "Looks good",
        },
    )

    assert result["comment"] == comment_data
    integration._post.assert_called_once()


@pytest.mark.asyncio
async def test_submit_pr_review_defaults_to_comment_event() -> None:
    integration = _make_integration()
    review_data = {"id": 5, "state": "COMMENTED"}
    integration._post = AsyncMock(return_value=review_data)

    result = await integration.execute_action(
        "submit_pr_review",
        {
            "owner": "mrveiss",
            "repo": "AutoBot-AI",
            "pull_number": 10,
            "body": "review body",
        },
    )

    assert result["review"] == review_data
    call_kwargs = integration._post.call_args
    assert call_kwargs[0][1]["event"] == "COMMENT"


@pytest.mark.asyncio
async def test_get_repository_tree_recursive() -> None:
    integration = _make_integration()
    tree_data = {"sha": "abc", "tree": []}
    integration._get = AsyncMock(return_value=tree_data)

    await integration.execute_action(
        "get_repository_tree",
        {"owner": "mrveiss", "repo": "AutoBot-AI", "tree_sha": "HEAD", "recursive": True},
    )

    call_args = integration._get.call_args
    assert call_args[1]["query_params"]["recursive"] == "1"


@pytest.mark.asyncio
async def test_list_commits_default_per_page() -> None:
    integration = _make_integration()
    commits = [{"sha": "abc"}] * 30
    integration._get = AsyncMock(return_value=commits)

    result = await integration.execute_action(
        "list_commits", {"owner": "mrveiss", "repo": "AutoBot-AI"}
    )

    assert result["count"] == 30
    call_args = integration._get.call_args
    assert call_args[1]["query_params"]["per_page"] == 30


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------


def test_auth_header_uses_token_field() -> None:
    cfg = IntegrationConfig(name="github", provider="github", token="tok_abc")
    integration = GitHubIntegration(cfg)
    assert integration.headers["Authorization"] == "Bearer tok_abc"


def test_auth_header_falls_back_to_api_key() -> None:
    cfg = IntegrationConfig(name="github", provider="github", api_key="key_xyz")
    integration = GitHubIntegration(cfg)
    assert integration.headers["Authorization"] == "Bearer key_xyz"


def test_custom_base_url() -> None:
    cfg = IntegrationConfig(
        name="github",
        provider="github",
        token="tok",
        base_url="https://github.example.com/api/v3",
    )
    integration = GitHubIntegration(cfg)
    assert integration.base_url == "https://github.example.com/api/v3"
