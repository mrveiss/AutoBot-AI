# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Growth Skill (Issue #1161)

Autonomous community outreach across Reddit (PRAW), Twitter API v2,
Discord webhooks, and GitHub releases — with dry_run support on all
posting operations. Credentials are read from skill config at runtime.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Tuple

import aiohttp
from skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

try:
    import praw
except ImportError:
    praw = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _build_reddit_config() -> Dict[str, SkillConfigField]:
    """Build Reddit OAuth config fields for the skill manifest. Issue #1161."""
    return {
        "reddit_client_id": SkillConfigField(
            type="string",
            description="PRAW OAuth client ID (REDDIT_CLIENT_ID secret)",
            required=False,
        ),
        "reddit_client_secret": SkillConfigField(
            type="string",
            description="PRAW OAuth client secret (REDDIT_CLIENT_SECRET secret)",
            required=False,
        ),
        "reddit_username": SkillConfigField(
            type="string",
            description="Reddit account username (REDDIT_USERNAME secret)",
            required=False,
        ),
        "reddit_password": SkillConfigField(
            type="string",
            description="Reddit account password (REDDIT_PASSWORD secret)",
            required=False,
        ),
    }


def _build_platform_config() -> Dict[str, SkillConfigField]:
    """Build Twitter/Discord/GitHub/LLM config fields for the manifest. Issue #1161."""
    return {
        "twitter_bearer_token": SkillConfigField(
            type="string",
            description="Twitter API v2 user access token (TWITTER_BEARER_TOKEN secret)",
            required=False,
        ),
        "discord_webhook_url": SkillConfigField(
            type="string",
            description="Discord channel webhook URL (DISCORD_WEBHOOK_URL secret)",
            required=False,
        ),
        "github_token": SkillConfigField(
            type="string",
            description="GitHub personal access token (GITHUB_TOKEN secret)",
            required=False,
        ),
        "default_content_mode": SkillConfigField(
            type="string",
            default="hybrid",
            description="Content generation mode: llm / template / hybrid",
            choices=["llm", "template", "hybrid"],
        ),
        "ollama_host": SkillConfigField(
            type="string",
            default="http://localhost:11434",
            description="Ollama API host for llm_draft_content",
            required=False,
        ),
        "ollama_model": SkillConfigField(
            type="string",
            default="mistral",
            description="Ollama model name for llm_draft_content",
            required=False,
        ),
    }


class CommunityGrowthSkill(BaseSkill):
    """Autonomous community outreach skill for Reddit, Twitter, Discord, and GitHub."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return community growth skill manifest."""
        config: Dict[str, SkillConfigField] = {}
        config.update(_build_reddit_config())
        config.update(_build_platform_config())
        return SkillManifest(
            name="community-growth",
            version="1.0.0",
            description=(
                "Autonomous community outreach across Reddit, Twitter, Discord, "
                "and GitHub"
            ),
            author="mrveiss",
            category="automation",
            dependencies=[],
            config=config,
            tools=[
                "reddit_search",
                "reddit_reply",
                "reddit_post",
                "twitter_post",
                "discord_notify",
                "github_get_releases",
                "llm_draft_content",
                "fill_template",
            ],
            triggers=["scheduled", "github_release"],
            tags=["community", "reddit", "twitter", "discord", "github", "outreach"],
        )

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a community growth action."""
        handlers = {
            "reddit_search": self._reddit_search,
            "reddit_reply": self._reddit_reply,
            "reddit_post": self._reddit_post,
            "twitter_post": self._twitter_post,
            "discord_notify": self._discord_notify,
            "github_get_releases": self._github_get_releases,
            "llm_draft_content": self._llm_draft_content,
            "fill_template": self._fill_template,
        }
        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}
        return await handler(params)

    # ------------------------------------------------------------------
    # Reddit helpers
    # ------------------------------------------------------------------

    def _get_reddit_instance(self) -> Tuple[Any, Any]:
        """Create authenticated PRAW Reddit instance. Issue #1161.

        Returns (reddit, None) on success or (None, error_str) on failure.
        """
        if praw is None:
            return None, "praw package not installed; add praw>=7.7.0 to requirements"

        client_id = self._config.get("reddit_client_id")
        client_secret = self._config.get("reddit_client_secret")
        if not client_id or not client_secret:
            return None, "Reddit credentials not configured (reddit_client_id/secret)"

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=self._config.get("reddit_username"),
            password=self._config.get("reddit_password"),
            user_agent="AutoBot/1.0 (community-growth-skill; by u/AutoBotAI)",
        )
        return reddit, None

    async def _reddit_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search subreddits for posts matching keywords. Issue #1161."""
        subreddits: List[str] = params.get("subreddits", [])
        keywords: List[str] = params.get("keywords", [])
        limit: int = params.get("limit", 25)
        min_score: int = params.get("min_score", 5)

        if not subreddits or not keywords:
            return {"success": False, "error": "subreddits and keywords are required"}

        reddit, error = self._get_reddit_instance()
        if error:
            return {"success": False, "error": error}

        query = " ".join(keywords)

        def _sync_search() -> List[Dict[str, Any]]:
            results = []
            for sub_name in subreddits:
                for post in reddit.subreddit(sub_name).search(query, limit=limit):
                    if post.score >= min_score:
                        results.append(
                            {
                                "post_id": post.id,
                                "title": post.title,
                                "url": f"https://reddit.com{post.permalink}",
                                "subreddit": sub_name,
                                "score": post.score,
                                "body_snippet": post.selftext[:200]
                                if post.selftext
                                else "",
                            }
                        )
            return results

        loop = asyncio.get_event_loop()
        matches = await loop.run_in_executor(None, _sync_search)
        return {"success": True, "matches": matches}

    async def _reddit_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a reply to a Reddit submission. Issue #1161."""
        post_id = params.get("post_id")
        content = params.get("content")
        dry_run: bool = params.get("dry_run", False)

        if not post_id or not content:
            return {"success": False, "error": "post_id and content are required"}

        if dry_run:
            logger.info("dry_run: would reply to Reddit post %s", post_id)
            return {"success": True, "comment_url": None, "dry_run": True}

        reddit, error = self._get_reddit_instance()
        if error:
            return {"success": False, "error": error}

        def _sync_reply() -> str:
            submission = reddit.submission(id=post_id)
            comment = submission.reply(content)
            return f"https://reddit.com{comment.permalink}"

        loop = asyncio.get_event_loop()
        try:
            comment_url = await loop.run_in_executor(None, _sync_reply)
            return {"success": True, "comment_url": comment_url}
        except Exception as exc:
            logger.exception("reddit_reply failed for post %s", post_id)
            return {"success": False, "error": str(exc)}

    async def _reddit_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a new post to a subreddit. Issue #1161."""
        subreddit = params.get("subreddit")
        title = params.get("title")
        content: str = params.get("content", "")
        flair: Any = params.get("flair")
        dry_run: bool = params.get("dry_run", False)

        if not subreddit or not title:
            return {"success": False, "error": "subreddit and title are required"}

        if dry_run:
            logger.info("dry_run: would post '%s' to r/%s", title, subreddit)
            return {"success": True, "post_url": None, "dry_run": True}

        reddit, error = self._get_reddit_instance()
        if error:
            return {"success": False, "error": error}

        def _sync_post() -> str:
            sub = reddit.subreddit(subreddit)
            post = sub.submit(title=title, selftext=content)
            if flair:
                post.flair.select(flair)
            return f"https://reddit.com{post.permalink}"

        loop = asyncio.get_event_loop()
        try:
            post_url = await loop.run_in_executor(None, _sync_post)
            return {"success": True, "post_url": post_url}
        except Exception as exc:
            logger.exception("reddit_post failed to r/%s", subreddit)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Twitter / Discord / GitHub
    # ------------------------------------------------------------------

    async def _twitter_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Post a tweet via Twitter API v2. Issue #1161."""
        content: str = params.get("content", "")
        dry_run: bool = params.get("dry_run", False)

        if len(content) > 280:
            content = content[:277] + "..."

        if dry_run:
            logger.info("dry_run: would tweet: %.50s", content)
            return {"success": True, "tweet_url": None, "dry_run": True}

        token = self._config.get("twitter_bearer_token")
        if not token:
            return {"success": False, "error": "Twitter token not configured"}

        url = "https://api.twitter.com/2/tweets"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json={"text": content}
            ) as resp:
                data = await resp.json()
                if resp.status == 201:
                    tweet_id = data.get("data", {}).get("id", "")
                    tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
                    return {"success": True, "tweet_url": tweet_url}
                error_msg = data.get("detail", f"HTTP {resp.status}")
                return {"success": False, "error": error_msg}

    async def _discord_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a notification to a Discord webhook. Issue #1161."""
        content: str = params.get("content", "")
        embed_title = params.get("embed_title")
        embed_url = params.get("embed_url")
        dry_run: bool = params.get("dry_run", False)

        if dry_run:
            logger.info("dry_run: would notify Discord: %.50s", content)
            return {"success": True, "dry_run": True}

        webhook_url = self._config.get("discord_webhook_url")
        if not webhook_url:
            return {"success": False, "error": "Discord webhook URL not configured"}

        payload: Dict[str, Any] = {"content": content}
        if embed_title:
            payload["embeds"] = [{"title": embed_title, "url": embed_url or ""}]

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status in (200, 204):
                    return {"success": True}
                text = await resp.text()
                return {"success": False, "error": f"HTTP {resp.status}: {text[:200]}"}

    async def _github_get_releases(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch releases from a GitHub repository. Issue #1161."""
        repo: str = params.get("repo", "")
        limit: int = params.get("limit", 1)

        if not repo:
            return {
                "success": False,
                "error": "repo is required (e.g. mrveiss/AutoBot-AI)",
            }

        token = self._config.get("github_token")
        headers: Dict[str, str] = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"https://api.github.com/repos/{repo}/releases"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params={"per_page": limit}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}: {text[:200]}",
                    }
                data = await resp.json()
                releases = [
                    {
                        "tag": r["tag_name"],
                        "name": r["name"],
                        "body": r.get("body", ""),
                        "published_at": r["published_at"],
                        "url": r["html_url"],
                    }
                    for r in data[:limit]
                ]
                return {"success": True, "releases": releases}

    # ------------------------------------------------------------------
    # LLM / template content generation
    # ------------------------------------------------------------------

    async def _llm_draft_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate content via local Ollama LLM. Issue #1161."""
        prompt: str = params.get("prompt", "")
        context: Any = params.get("context", {})
        fmt: str = params.get("format", "reddit_post")
        max_tokens: int = params.get("max_tokens", 300)

        if not prompt:
            return {"success": False, "error": "prompt is required"}

        format_hints = {
            "reddit_post": "Write an informative, conversational Reddit post.",
            "reddit_reply": "Write a concise, helpful Reddit reply (2-4 sentences).",
            "tweet": "Write a tweet under 280 characters. Be engaging and use hashtags.",
            "discord": "Write a friendly Discord message with key highlights.",
            "all_channels": (
                "Draft three separate messages: one Reddit post, one tweet "
                "(≤280 chars), and one Discord message."
            ),
        }
        hint = format_hints.get(fmt, "")
        full_prompt = f"{hint}\n\nContext: {json.dumps(context)}\n\n{prompt}"

        ollama_host = self._config.get("ollama_host", "http://localhost:11434")
        ollama_model = self._config.get("ollama_model", "mistral")
        ollama_url = f"{ollama_host}/api/generate"
        payload = {
            "model": ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(ollama_url, json=payload) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"Ollama HTTP {resp.status}"}
                data = await resp.json()
                return {
                    "success": True,
                    "content": data.get("response", ""),
                    "tokens_used": data.get("eval_count", 0),
                }

    async def _fill_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Substitute variables into a template string. Issue #1161."""
        template: str = params.get("template", "")
        variables: Dict[str, Any] = params.get("variables", {})

        if not template:
            return {"success": False, "error": "template is required"}

        try:
            content = template.format(**variables)
            return {"success": True, "content": content}
        except KeyError as exc:
            return {"success": False, "error": f"Missing template variable: {exc}"}
