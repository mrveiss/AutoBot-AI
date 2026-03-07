# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Growth Workflow Templates

Issue #1161: Autonomous community outreach templates for Reddit, Twitter,
Discord, and GitHub — each with a human-approval gate before posting.
Issue #1415: User-friendly step descriptions and required_secrets metadata.
"""

from typing import Dict, List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _build_reddit_monitor_gather_steps() -> List[WorkflowStep]:
    """Build search and draft steps for Reddit Monitor & Reply. Issue #1161."""
    return [
        WorkflowStep(
            id="reddit_search",
            agent_type="community_growth",
            action="reddit_search",
            description=(
                "Search target subreddits for posts matching your keywords. "
                "Uses Reddit API (read-only, app credentials only) to find "
                "relevant discussions, filtering by minimum score."
            ),
            inputs={
                "subreddits": "{subreddits}",
                "keywords": "{keywords}",
                "limit": 25,
                "min_score": 5,
            },
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="draft_replies",
            agent_type="community_growth",
            action="llm_draft_content",
            description=(
                "AutoBot sends each matching post to the local LLM (Ollama) "
                "and drafts a helpful, contextual reply for every result. "
                "Replies mention the AutoBot project where relevant."
            ),
            dependencies=["reddit_search"],
            inputs={
                "format": "reddit_reply",
                "prompt": (
                    "Draft helpful replies for each matching Reddit post. "
                    "Mention AutoBot at {autobot_url} where relevant."
                ),
            },
            expected_duration_ms=45000,
        ),
    ]


def _build_reddit_monitor_post_steps() -> List[WorkflowStep]:
    """Build approval and post steps for Reddit Monitor & Reply. Issue #1161."""
    return [
        WorkflowStep(
            id="review_drafts",
            agent_type="orchestrator",
            action="human_review",
            description=(
                "All drafted replies are presented for your review. "
                "You can edit, approve, or reject each reply before "
                "anything is posted. Nothing goes live without your OK."
            ),
            requires_approval=True,
            dependencies=["draft_replies"],
            expected_duration_ms=0,
        ),
        WorkflowStep(
            id="reddit_reply",
            agent_type="community_growth",
            action="reddit_reply",
            description=(
                "Post the approved replies to their respective Reddit "
                "threads. Requires full Reddit OAuth credentials "
                "(username + password). Only replies you approved in "
                "the previous step are posted."
            ),
            dependencies=["review_drafts"],
            inputs={"dry_run": False},
            expected_duration_ms=20000,
        ),
    ]


def _get_reddit_monitor_variables() -> Dict[str, str]:
    """Get variable definitions for Reddit Monitor & Reply template. Issue #1161."""
    return {
        "subreddits": "Comma-separated subreddits to monitor (e.g. selfhosted,LocalLLaMA)",
        "keywords": "Keywords to search for (e.g. local AI assistant,self-hosted automation)",
        "autobot_url": "AutoBot project URL to mention in replies",
    }


def create_reddit_monitor_reply_template() -> WorkflowTemplate:
    """Create Reddit Monitor & Reply workflow template."""
    steps = _build_reddit_monitor_gather_steps() + _build_reddit_monitor_post_steps()
    return WorkflowTemplate(
        id="reddit_monitor_reply",
        name="Reddit Monitor & Reply",
        description=(
            "Search subreddits for relevant posts, draft replies with the local LLM, "
            "and post after human approval."
        ),
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=15,
        agents_involved=["community_growth", "orchestrator"],
        tags=["community", "reddit", "outreach", "monitor", "reply"],
        variables=_get_reddit_monitor_variables(),
        steps=steps,
        required_secrets={
            "REDDIT_CLIENT_ID": {
                "description": "Reddit OAuth app client ID",
                "required": True,
                "scope": "read",
            },
            "REDDIT_CLIENT_SECRET": {
                "description": "Reddit OAuth app client secret",
                "required": True,
                "scope": "read",
            },
            "REDDIT_USERNAME": {
                "description": "Reddit account username (required for posting)",
                "required": True,
                "scope": "write",
            },
            "REDDIT_PASSWORD": {
                "description": "Reddit account password (required for posting)",
                "required": True,
                "scope": "write",
            },
        },
    )


def _build_blast_fetch_draft_steps() -> List[WorkflowStep]:
    """Build fetch and draft steps for Release Announcement Blast. Issue #1161."""
    return [
        WorkflowStep(
            id="fetch_release",
            agent_type="community_growth",
            action="github_get_releases",
            description=(
                "Fetch the latest release from the GitHub repository, "
                "including tag name, release notes, and highlights. "
                "Uses GitHub API (public repos need no token; private "
                "repos require a GITHUB_TOKEN)."
            ),
            inputs={"repo": "{repo}", "limit": 1},
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="draft_content",
            agent_type="community_growth",
            action="llm_draft_content",
            description=(
                "AutoBot sends the release notes to the local LLM and "
                "drafts three separate announcements: a Reddit post, a "
                "tweet (<=280 chars), and a Discord message — each "
                "tailored for its platform."
            ),
            dependencies=["fetch_release"],
            inputs={
                "format": "all_channels",
                "prompt": (
                    "Draft a release announcement for Reddit, Twitter, and Discord. "
                    "Include the release tag, key highlights, and a link."
                ),
            },
            expected_duration_ms=60000,
        ),
    ]


def _build_blast_review_step() -> List[WorkflowStep]:
    """Build human review step for Release Announcement Blast. Issue #1161."""
    return [
        WorkflowStep(
            id="review_content",
            agent_type="orchestrator",
            action="human_review",
            description=(
                "All three drafted announcements (Reddit, Twitter, "
                "Discord) are presented for your review. Edit wording, "
                "approve or reject each one individually. Nothing is "
                "posted without your approval."
            ),
            requires_approval=True,
            dependencies=["draft_content"],
            expected_duration_ms=0,
        ),
    ]


def _build_blast_posting_steps() -> List[WorkflowStep]:
    """Build parallel posting steps for Release Announcement Blast. Issue #1161."""
    return [
        WorkflowStep(
            id="reddit_post",
            agent_type="community_growth",
            action="reddit_post",
            description=(
                "Submit the approved announcement as a new post to "
                "the target subreddit. Requires full Reddit OAuth "
                "credentials."
            ),
            dependencies=["review_content"],
            inputs={"subreddit": "{target_subreddits}", "dry_run": False},
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="twitter_post",
            agent_type="community_growth",
            action="twitter_post",
            description=(
                "Publish the approved tweet via Twitter API v2. "
                "Requires a TWITTER_BEARER_TOKEN with write access."
            ),
            dependencies=["review_content"],
            inputs={"dry_run": False},
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="discord_notify",
            agent_type="community_growth",
            action="discord_notify",
            description=(
                "Send the approved announcement to the configured "
                "Discord channel via webhook. Requires a "
                "DISCORD_WEBHOOK_URL."
            ),
            dependencies=["review_content"],
            inputs={"dry_run": False},
            expected_duration_ms=5000,
        ),
    ]


def _get_blast_variables() -> Dict[str, str]:
    """Get variable definitions for Release Announcement Blast template. Issue #1161."""
    return {
        "repo": "GitHub repository (e.g. mrveiss/AutoBot-AI)",
        "target_subreddits": "Target subreddit for the Reddit post (e.g. selfhosted)",
        "discord_webhook_url": "Discord webhook URL for the announcement channel",
    }


def create_release_announcement_blast_template() -> WorkflowTemplate:
    """Create Release Announcement Blast workflow template."""
    steps = (
        _build_blast_fetch_draft_steps()
        + _build_blast_review_step()
        + _build_blast_posting_steps()
    )
    return WorkflowTemplate(
        id="release_announcement_blast",
        name="Release Announcement Blast",
        description=(
            "Fetch the latest GitHub release, draft announcements for Reddit, Twitter, "
            "and Discord, then post after human approval."
        ),
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=10,
        agents_involved=["community_growth", "orchestrator"],
        tags=["community", "release", "reddit", "twitter", "discord", "announcement"],
        variables=_get_blast_variables(),
        steps=steps,
        required_secrets={
            "GITHUB_TOKEN": {
                "description": "GitHub token (only needed for private repos)",
                "required": False,
                "scope": "read",
            },
            "REDDIT_CLIENT_ID": {
                "description": "Reddit OAuth app client ID",
                "required": True,
                "scope": "write",
            },
            "REDDIT_CLIENT_SECRET": {
                "description": "Reddit OAuth app client secret",
                "required": True,
                "scope": "write",
            },
            "REDDIT_USERNAME": {
                "description": "Reddit account username",
                "required": True,
                "scope": "write",
            },
            "REDDIT_PASSWORD": {
                "description": "Reddit account password",
                "required": True,
                "scope": "write",
            },
            "TWITTER_BEARER_TOKEN": {
                "description": "Twitter API v2 bearer token with write access",
                "required": True,
                "scope": "write",
            },
            "DISCORD_WEBHOOK_URL": {
                "description": "Discord channel webhook URL",
                "required": True,
                "scope": "write",
            },
        },
    )


def _build_digest_gather_steps() -> List[WorkflowStep]:
    """Build parallel gather steps for Community Digest Post. Issue #1161."""
    return [
        WorkflowStep(
            id="fetch_releases",
            agent_type="community_growth",
            action="github_get_releases",
            description=(
                "Fetch the 5 most recent releases from the GitHub "
                "repository. Runs in parallel with the Reddit search "
                "step. Public repos need no token."
            ),
            inputs={"repo": "{repo}", "limit": 5},
            expected_duration_ms=10000,
        ),
        WorkflowStep(
            id="search_mentions",
            agent_type="community_growth",
            action="reddit_search",
            description=(
                "Search target subreddits for mentions of AutoBot and "
                "mrveiss. Runs in parallel with the GitHub releases "
                "fetch. Uses read-only Reddit app credentials."
            ),
            inputs={
                "subreddits": "{target_subreddits}",
                "keywords": ["autobot", "mrveiss"],
                "limit": 10,
                "min_score": 1,
            },
            expected_duration_ms=20000,
        ),
    ]


def _build_digest_draft_review_post_steps() -> List[WorkflowStep]:
    """Build draft, review, and post steps for Community Digest Post. Issue #1161."""
    return [
        WorkflowStep(
            id="draft_digest",
            agent_type="community_growth",
            action="llm_draft_content",
            description=(
                "AutoBot combines the GitHub releases and Reddit "
                "mentions, then sends them to the local LLM to draft "
                "a community digest post summarising activity over "
                "the lookback period."
            ),
            dependencies=["fetch_releases", "search_mentions"],
            inputs={
                "format": "reddit_post",
                "prompt": (
                    "Write a community digest post summarising recent AutoBot releases "
                    "and notable Reddit mentions from the past {lookback_days} days."
                ),
            },
            expected_duration_ms=60000,
        ),
        WorkflowStep(
            id="review_digest",
            agent_type="orchestrator",
            action="human_review",
            description=(
                "The drafted digest is presented for your review. "
                "Edit, approve, or reject before it goes live. "
                "Nothing is posted without your approval."
            ),
            requires_approval=True,
            dependencies=["draft_digest"],
            expected_duration_ms=0,
        ),
        WorkflowStep(
            id="post_digest",
            agent_type="community_growth",
            action="reddit_post",
            description=(
                "Submit the approved digest as a new post to the "
                "target subreddit. Requires full Reddit OAuth "
                "credentials."
            ),
            dependencies=["review_digest"],
            inputs={"subreddit": "{target_subreddits}", "dry_run": False},
            expected_duration_ms=15000,
        ),
    ]


def _get_digest_variables() -> Dict[str, str]:
    """Get variable definitions for Community Digest Post template. Issue #1161."""
    return {
        "repo": "GitHub repository to fetch releases from (e.g. mrveiss/AutoBot-AI)",
        "target_subreddits": "Target subreddit(s) for the digest post (e.g. selfhosted)",
        "lookback_days": "Number of days to include in the digest (e.g. 7)",
    }


def create_community_digest_post_template() -> WorkflowTemplate:
    """Create Community Digest Post workflow template."""
    steps = _build_digest_gather_steps() + _build_digest_draft_review_post_steps()
    return WorkflowTemplate(
        id="community_digest_post",
        name="Community Digest Post",
        description=(
            "Gather recent GitHub releases and Reddit mentions, draft a community digest, "
            "then post to Reddit after human approval."
        ),
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=20,
        agents_involved=["community_growth", "orchestrator"],
        tags=["community", "digest", "reddit", "github", "releases", "weekly"],
        variables=_get_digest_variables(),
        steps=steps,
        required_secrets={
            "GITHUB_TOKEN": {
                "description": "GitHub token (only needed for private repos)",
                "required": False,
                "scope": "read",
            },
            "REDDIT_CLIENT_ID": {
                "description": "Reddit OAuth app client ID",
                "required": True,
                "scope": "read+write",
            },
            "REDDIT_CLIENT_SECRET": {
                "description": "Reddit OAuth app client secret",
                "required": True,
                "scope": "read+write",
            },
            "REDDIT_USERNAME": {
                "description": "Reddit account username (required for posting)",
                "required": True,
                "scope": "write",
            },
            "REDDIT_PASSWORD": {
                "description": "Reddit account password (required for posting)",
                "required": True,
                "scope": "write",
            },
        },
    )


def get_all_community_templates() -> List[WorkflowTemplate]:
    """Get all community growth workflow templates."""
    return [
        create_reddit_monitor_reply_template(),
        create_release_announcement_blast_template(),
        create_community_digest_post_template(),
    ]
