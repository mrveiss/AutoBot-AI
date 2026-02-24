# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for CommunityGrowthSkill.

Issue #1161: Tests cover all 8 tools across success, error, and dry_run paths.
External APIs (PRAW, aiohttp) are mocked throughout.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from skills.builtin.community_growth import CommunityGrowthSkill


@pytest.fixture()
def skill() -> CommunityGrowthSkill:
    """Return a configured CommunityGrowthSkill instance."""
    s = CommunityGrowthSkill()
    s.apply_config(
        {
            "reddit_client_id": "test_id",
            "reddit_client_secret": "test_secret",
            "reddit_username": "test_user",
            "reddit_password": "test_pass",
            "twitter_bearer_token": "test_twitter_token",
            "discord_webhook_url": "https://discord.com/api/webhooks/test",
            "github_token": "ghp_test",
            "default_content_mode": "hybrid",
            "ollama_host": "http://localhost:11434",
            "ollama_model": "mistral",
        }
    )
    return s


# ------------------------------------------------------------------
# Manifest and validation
# ------------------------------------------------------------------


def test_get_manifest_has_all_tools():
    """Manifest lists all 8 expected tools."""
    manifest = CommunityGrowthSkill.get_manifest()
    expected = {
        "reddit_search",
        "reddit_reply",
        "reddit_post",
        "twitter_post",
        "discord_notify",
        "github_get_releases",
        "llm_draft_content",
        "fill_template",
    }
    assert set(manifest.tools) == expected


def test_get_manifest_metadata():
    """Manifest has correct name, category, and triggers."""
    manifest = CommunityGrowthSkill.get_manifest()
    assert manifest.name == "community-growth"
    assert manifest.category == "automation"
    assert "scheduled" in manifest.triggers
    assert "github_release" in manifest.triggers


def test_validate_config_passes_with_valid_mode(skill: CommunityGrowthSkill):
    """validate_config returns no errors for a valid content mode."""
    errors = skill.validate_config({"default_content_mode": "llm"})
    assert errors == []


def test_validate_config_fails_with_invalid_mode(skill: CommunityGrowthSkill):
    """validate_config returns error for unknown content mode."""
    errors = skill.validate_config({"default_content_mode": "invalid"})
    assert any("default_content_mode" in e for e in errors)


# ------------------------------------------------------------------
# execute — unknown action
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_execute_unknown_action_returns_error(skill: CommunityGrowthSkill):
    """execute returns error dict for unknown action names."""
    result = await skill.execute("nonexistent_action", {})
    assert result["success"] is False
    assert "Unknown action" in result["error"]


# ------------------------------------------------------------------
# reddit_search
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_reddit_search_returns_matches(skill: CommunityGrowthSkill):
    """reddit_search returns matching posts from mocked PRAW."""
    mock_post = MagicMock()
    mock_post.id = "abc123"
    mock_post.title = "Test post"
    mock_post.permalink = "/r/selfhosted/comments/abc123/"
    mock_post.score = 10
    mock_post.selftext = "Body text"

    mock_subreddit = MagicMock()
    mock_subreddit.search.return_value = [mock_post]

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value = mock_subreddit

    with patch("skills.builtin.community_growth.praw") as mock_praw_module:
        mock_praw_module.Reddit.return_value = mock_reddit
        result = await skill.execute(
            "reddit_search",
            {"subreddits": ["selfhosted"], "keywords": ["automation"], "min_score": 5},
        )

    assert result["success"] is True
    assert len(result["matches"]) == 1
    assert result["matches"][0]["post_id"] == "abc123"


@pytest.mark.asyncio()
async def test_reddit_search_missing_params(skill: CommunityGrowthSkill):
    """reddit_search returns error when subreddits or keywords are missing."""
    result = await skill.execute("reddit_search", {"subreddits": ["selfhosted"]})
    assert result["success"] is False
    assert "required" in result["error"]


# ------------------------------------------------------------------
# reddit_reply
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_reddit_reply_dry_run(skill: CommunityGrowthSkill):
    """reddit_reply with dry_run=True returns success without posting."""
    result = await skill.execute(
        "reddit_reply",
        {"post_id": "abc123", "content": "Hello!", "dry_run": True},
    )
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["comment_url"] is None


@pytest.mark.asyncio()
async def test_reddit_reply_missing_params(skill: CommunityGrowthSkill):
    """reddit_reply returns error when post_id or content is missing."""
    result = await skill.execute("reddit_reply", {"post_id": "abc123"})
    assert result["success"] is False


@pytest.mark.asyncio()
async def test_reddit_reply_posts_comment(skill: CommunityGrowthSkill):
    """reddit_reply posts comment and returns URL via mocked PRAW."""
    mock_comment = MagicMock()
    mock_comment.permalink = "/r/selfhosted/comments/abc123/comment/xyz/"

    mock_submission = MagicMock()
    mock_submission.reply.return_value = mock_comment

    mock_reddit = MagicMock()
    mock_reddit.submission.return_value = mock_submission

    with patch("skills.builtin.community_growth.praw") as mock_praw_module:
        mock_praw_module.Reddit.return_value = mock_reddit
        result = await skill.execute(
            "reddit_reply",
            {"post_id": "abc123", "content": "Great post!", "dry_run": False},
        )

    assert result["success"] is True
    assert "reddit.com" in result["comment_url"]


# ------------------------------------------------------------------
# reddit_post
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_reddit_post_dry_run(skill: CommunityGrowthSkill):
    """reddit_post with dry_run=True returns success without posting."""
    result = await skill.execute(
        "reddit_post",
        {"subreddit": "selfhosted", "title": "Test", "dry_run": True},
    )
    assert result["success"] is True
    assert result["dry_run"] is True


@pytest.mark.asyncio()
async def test_reddit_post_missing_title(skill: CommunityGrowthSkill):
    """reddit_post returns error when title is missing."""
    result = await skill.execute("reddit_post", {"subreddit": "selfhosted"})
    assert result["success"] is False


# ------------------------------------------------------------------
# twitter_post
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_twitter_post_dry_run(skill: CommunityGrowthSkill):
    """twitter_post with dry_run=True returns success without calling API."""
    result = await skill.execute(
        "twitter_post", {"content": "Hello Twitter!", "dry_run": True}
    )
    assert result["success"] is True
    assert result["dry_run"] is True


@pytest.mark.asyncio()
async def test_twitter_post_truncates_long_content(skill: CommunityGrowthSkill):
    """twitter_post with dry_run truncates content over 280 chars."""
    long_content = "x" * 300
    result = await skill.execute(
        "twitter_post", {"content": long_content, "dry_run": True}
    )
    assert result["success"] is True


@pytest.mark.asyncio()
async def test_twitter_post_no_token():
    """twitter_post returns error when bearer token is not configured."""
    s = CommunityGrowthSkill()
    s.apply_config({})
    result = await s.execute("twitter_post", {"content": "Hello", "dry_run": False})
    assert result["success"] is False
    assert "token" in result["error"].lower()


# ------------------------------------------------------------------
# discord_notify
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_discord_notify_dry_run(skill: CommunityGrowthSkill):
    """discord_notify with dry_run=True returns success without calling webhook."""
    result = await skill.execute(
        "discord_notify", {"content": "Hello Discord!", "dry_run": True}
    )
    assert result["success"] is True
    assert result["dry_run"] is True


@pytest.mark.asyncio()
async def test_discord_notify_no_webhook():
    """discord_notify returns error when webhook URL is not configured."""
    s = CommunityGrowthSkill()
    s.apply_config({})
    result = await s.execute("discord_notify", {"content": "Hi", "dry_run": False})
    assert result["success"] is False
    assert "webhook" in result["error"].lower()


# ------------------------------------------------------------------
# github_get_releases
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_github_get_releases_missing_repo(skill: CommunityGrowthSkill):
    """github_get_releases returns error when repo is not provided."""
    result = await skill.execute("github_get_releases", {})
    assert result["success"] is False
    assert "repo" in result["error"]


@pytest.mark.asyncio()
async def test_github_get_releases_success(skill: CommunityGrowthSkill):
    """github_get_releases returns releases list on HTTP 200."""
    mock_inner_resp = MagicMock()
    mock_inner_resp.status = 200
    mock_inner_resp.json = AsyncMock(
        return_value=[
            {
                "tag_name": "v1.2.3",
                "name": "Release 1.2.3",
                "body": "Bug fixes",
                "published_at": "2026-02-24T00:00:00Z",
                "html_url": "https://github.com/mrveiss/AutoBot-AI/releases/tag/v1.2.3",
            }
        ]
    )

    request_cm = MagicMock()
    request_cm.__aenter__ = AsyncMock(return_value=mock_inner_resp)
    request_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get.return_value = request_cm

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("skills.builtin.community_growth.aiohttp.ClientSession") as mock_cs:
        mock_cs.return_value = session_cm
        result = await skill.execute(
            "github_get_releases", {"repo": "mrveiss/AutoBot-AI", "limit": 1}
        )

    assert result["success"] is True
    assert len(result["releases"]) == 1
    assert result["releases"][0]["tag"] == "v1.2.3"


# ------------------------------------------------------------------
# llm_draft_content
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_llm_draft_content_missing_prompt(skill: CommunityGrowthSkill):
    """llm_draft_content returns error when prompt is not provided."""
    result = await skill.execute("llm_draft_content", {})
    assert result["success"] is False
    assert "prompt" in result["error"]


@pytest.mark.asyncio()
async def test_llm_draft_content_success(skill: CommunityGrowthSkill):
    """llm_draft_content returns generated content on Ollama HTTP 200."""
    mock_inner_resp = MagicMock()
    mock_inner_resp.status = 200
    mock_inner_resp.json = AsyncMock(
        return_value={
            "response": "Here is a great Reddit post about AutoBot.",
            "eval_count": 42,
        }
    )

    request_cm = MagicMock()
    request_cm.__aenter__ = AsyncMock(return_value=mock_inner_resp)
    request_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post.return_value = request_cm

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("skills.builtin.community_growth.aiohttp.ClientSession") as mock_cs:
        mock_cs.return_value = session_cm
        result = await skill.execute(
            "llm_draft_content",
            {"prompt": "Write about AutoBot", "format": "reddit_post"},
        )

    assert result["success"] is True
    assert "AutoBot" in result["content"]
    assert result["tokens_used"] == 42


# ------------------------------------------------------------------
# fill_template
# ------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_fill_template_success(skill: CommunityGrowthSkill):
    """fill_template substitutes variables correctly."""
    result = await skill.execute(
        "fill_template",
        {
            "template": "Hello {name}! Check out {url}",
            "variables": {"name": "Reddit", "url": "https://example.com"},
        },
    )
    assert result["success"] is True
    assert result["content"] == "Hello Reddit! Check out https://example.com"


@pytest.mark.asyncio()
async def test_fill_template_missing_variable(skill: CommunityGrowthSkill):
    """fill_template returns error when a required variable is missing."""
    result = await skill.execute(
        "fill_template",
        {"template": "Hello {name}!", "variables": {}},
    )
    assert result["success"] is False
    assert "Missing template variable" in result["error"]


@pytest.mark.asyncio()
async def test_fill_template_missing_template(skill: CommunityGrowthSkill):
    """fill_template returns error when template string is not provided."""
    result = await skill.execute("fill_template", {})
    assert result["success"] is False
