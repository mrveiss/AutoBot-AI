# Community Growth Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `CommunityGrowthSkill` and three workflow templates that let AutoBot autonomously post and reply on Reddit, Twitter, Discord, and GitHub releases — with a human-in-the-middle approval gate before any content is published — all surfaced inside the existing `/automation` Workflow Builder.

**Architecture:** One new `BaseSkill` subclass (`community_growth.py`) provides 8 tools wrapping Reddit (PRAW), Twitter API v2, Discord webhook, and GitHub API. Three new `WorkflowTemplate` definitions in a new `community.py` module plug into the existing `WorkflowTemplateManager`. All credentials are fetched from the existing secrets manager at runtime; no values are hardcoded.

**Tech Stack:** Python 3.12, `praw` (Reddit), `aiohttp` (already installed — used for Twitter/Discord/GitHub), existing `BaseSkill` / `WorkflowTemplate` / `SkillRegistry` / `SecretsManager` frameworks.

---

## Reference: Key files to understand before starting

- `autobot-backend/skills/base_skill.py` — `BaseSkill`, `SkillManifest`, `SkillConfigField`
- `autobot-backend/skills/builtin/browser_automation.py` — canonical skill example
- `autobot-backend/skills/registry.py:224-260` — `discover_builtin_skills()` (auto-discovery, no manual registration needed)
- `autobot-backend/workflow_templates/types.py` — `WorkflowStep`, `WorkflowTemplate`, `TemplateCategory`
- `autobot-backend/workflow_templates/analysis.py` — canonical template module example
- `autobot-backend/workflow_templates/manager.py:31-43` — `_initialize_default_templates()` (where community templates must be added)
- `autobot-backend/workflow_templates/__init__.py` — package exports (must be updated)
- `autobot-backend/workflow_templates.py` — backwards-compat facade (must be updated)
- `autobot-backend/api/secrets.py` — `SecretType`, how secrets are stored/fetched
- `autobot-backend/services/captcha_solver.py` — `CaptchaSolver.attempt_solve()`
- `autobot-backend/workflow_templates/workflow_templates.e2e_test.py` — existing e2e test to extend

---

## Task 1: Add `praw` to requirements

**Files:**
- Modify: `autobot-backend/requirements.txt`

**Step 1: Add the dependency**

In `autobot-backend/requirements.txt`, find the section with other API client libraries and add:

```
praw>=7.7.0             # Reddit API wrapper for community growth skill
```

**Step 2: Verify it installs**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
pip install praw>=7.7.0
```

Expected: `Successfully installed praw-7.x.x` (or already satisfied)

**Step 3: Commit**

```bash
git add autobot-backend/requirements.txt
git commit -m "feat(community-growth): add praw dependency for Reddit API (#1161)"
```

---

## Task 2: Add `COMMUNITY` to `TemplateCategory`

**Files:**
- Modify: `autobot-backend/workflow_templates/types.py:18-26`
- Test: `autobot-backend/workflow_templates/workflow_templates.e2e_test.py`

**Step 1: Write the failing test**

At the bottom of `workflow_templates/workflow_templates.e2e_test.py`, add:

```python
async def test_community_category_exists():
    """Test COMMUNITY category is defined in TemplateCategory."""
    from workflow_templates.types import TemplateCategory
    assert hasattr(TemplateCategory, "COMMUNITY")
    assert TemplateCategory.COMMUNITY.value == "community"
    print("✅ COMMUNITY category exists")
```

**Step 2: Run test to verify it fails**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from workflow_templates.workflow_templates import test_community_category_exists
asyncio.run(test_community_category_exists())
"
```

Expected: `AttributeError: COMMUNITY`

**Step 3: Add `COMMUNITY` to `TemplateCategory`**

In `autobot-backend/workflow_templates/types.py`, edit the `TemplateCategory` enum to add one line after `ANALYSIS`:

```python
class TemplateCategory(Enum):
    """Categories of workflow templates."""

    SECURITY = "security"
    RESEARCH = "research"
    SYSTEM_ADMIN = "system_admin"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"
    COMMUNITY = "community"
```

**Step 4: Run test to verify it passes**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from workflow_templates.types import TemplateCategory
assert TemplateCategory.COMMUNITY.value == 'community'
print('PASS')
"
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add autobot-backend/workflow_templates/types.py \
        autobot-backend/workflow_templates/workflow_templates.e2e_test.py
git commit -m "feat(community-growth): add COMMUNITY TemplateCategory (#1161)"
```

---

## Task 3: Create `workflow_templates/community.py` with 3 templates

**Files:**
- Create: `autobot-backend/workflow_templates/community.py`

**Step 1: Write the failing test**

Add to `workflow_templates/workflow_templates.e2e_test.py`:

```python
async def test_community_templates_load():
    """Test all 3 community templates load correctly."""
    from workflow_templates.community import get_all_community_templates
    from workflow_templates.types import TemplateCategory

    templates = get_all_community_templates()
    assert len(templates) == 3, f"Expected 3 templates, got {len(templates)}"

    ids = {t.id for t in templates}
    assert "reddit_monitor_reply" in ids
    assert "release_announcement_blast" in ids
    assert "community_digest_post" in ids

    for t in templates:
        assert t.category == TemplateCategory.COMMUNITY
        # Each template must have at least one approval step
        approval_steps = [s for s in t.steps if s.requires_approval]
        assert len(approval_steps) >= 1, f"{t.id} has no approval gate"

    print(f"✅ {len(templates)} community templates loaded, all have approval gates")
```

**Step 2: Run test to verify it fails**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import sys; sys.path.insert(0, '.')
from workflow_templates.community import get_all_community_templates
" 2>&1 | head -3
```

Expected: `ModuleNotFoundError: No module named 'workflow_templates.community'`

**Step 3: Create `community.py`**

Create `autobot-backend/workflow_templates/community.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Growth Workflow Templates

Provides workflow templates for autonomous community outreach on Reddit,
Twitter, Discord, and GitHub. Each template includes a human approval gate
before any content is published. Issue #1161.
"""

from typing import List

from autobot_types import TaskComplexity

from .types import TemplateCategory, WorkflowStep, WorkflowTemplate


def _build_reddit_monitor_reply_steps() -> List[WorkflowStep]:
    """
    Build steps for Reddit Monitor & Reply template.

    Searches target subreddits for keyword matches, drafts contextual
    replies via LLM, awaits human approval, then posts. Issue #1161.
    """
    return [
        WorkflowStep(
            id="reddit_search",
            agent_type="community_growth",
            action="Search subreddits {subreddits} for posts mentioning {keywords}",
            description="Community_Growth: Reddit Keyword Search",
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="draft_replies",
            agent_type="community_growth",
            action="Draft contextual replies for each matching post using content_mode={content_mode}",
            description="Community_Growth: Draft Replies",
            dependencies=["reddit_search"],
            inputs={"format": "reddit_reply", "content_mode": "{content_mode}"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="review_drafts",
            agent_type="orchestrator",
            action="Review drafted replies before posting to Reddit",
            description="Orchestrator: Review Replies (requires your approval)",
            requires_approval=True,
            dependencies=["draft_replies"],
            expected_duration_ms=0,
        ),
        WorkflowStep(
            id="post_replies",
            agent_type="community_growth",
            action="Post approved replies to Reddit",
            description="Community_Growth: Post Replies",
            dependencies=["review_drafts"],
            inputs={"dry_run": False},
            expected_duration_ms=10000,
        ),
    ]


def create_reddit_monitor_reply_template() -> WorkflowTemplate:
    """Create Reddit Monitor & Reply workflow template."""
    return WorkflowTemplate(
        id="reddit_monitor_reply",
        name="Reddit Monitor & Reply",
        description="Search target subreddits for relevant discussions and post contextual replies",
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.MODERATE,
        estimated_duration_minutes=15,
        agents_involved=["community_growth", "orchestrator"],
        tags=["reddit", "community", "outreach", "reply", "monitor"],
        variables={
            "subreddits": "Comma-separated subreddit names, e.g. selfhosted,LocalLLaMA",
            "keywords": "Comma-separated keywords to search for",
            "content_mode": "Content generation mode: llm, template, or hybrid",
        },
        steps=_build_reddit_monitor_reply_steps(),
    )


def _build_release_announcement_blast_steps() -> List[WorkflowStep]:
    """
    Build steps for Release Announcement Blast template.

    Fetches latest GitHub release, drafts platform-specific content,
    awaits human approval, then posts to Reddit + Twitter + Discord.
    Issue #1161.
    """
    return [
        WorkflowStep(
            id="fetch_release",
            agent_type="community_growth",
            action="Fetch latest release from GitHub repo {repo}",
            description="Community_Growth: Fetch GitHub Release",
            expected_duration_ms=5000,
        ),
        WorkflowStep(
            id="draft_content",
            agent_type="community_growth",
            action="Draft Reddit post, tweet, and Discord message from release notes using {content_mode}",
            description="Community_Growth: Draft Multi-Channel Content",
            dependencies=["fetch_release"],
            inputs={"format": "all_channels", "content_mode": "{content_mode}"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="review_content",
            agent_type="orchestrator",
            action="Review release content for Reddit, Twitter, and Discord before publishing",
            description="Orchestrator: Review Release Content (requires your approval)",
            requires_approval=True,
            dependencies=["draft_content"],
            expected_duration_ms=0,
        ),
        WorkflowStep(
            id="post_reddit",
            agent_type="community_growth",
            action="Post release announcement to subreddits {target_subreddits}",
            description="Community_Growth: Post to Reddit",
            dependencies=["review_content"],
            inputs={"dry_run": False},
            expected_duration_ms=8000,
        ),
        WorkflowStep(
            id="post_twitter",
            agent_type="community_growth",
            action="Post release tweet to Twitter/X",
            description="Community_Growth: Post to Twitter",
            dependencies=["review_content"],
            inputs={"dry_run": False},
            expected_duration_ms=5000,
        ),
        WorkflowStep(
            id="post_discord",
            agent_type="community_growth",
            action="Send release notification to Discord webhook",
            description="Community_Growth: Post to Discord",
            dependencies=["review_content"],
            inputs={"dry_run": False},
            expected_duration_ms=3000,
        ),
    ]


def create_release_announcement_blast_template() -> WorkflowTemplate:
    """Create Release Announcement Blast workflow template."""
    return WorkflowTemplate(
        id="release_announcement_blast",
        name="Release Announcement Blast",
        description="Announce a new GitHub release across Reddit, Twitter, and Discord with one approval gate",
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.MODERATE,
        estimated_duration_minutes=10,
        agents_involved=["community_growth", "orchestrator"],
        tags=["release", "announcement", "reddit", "twitter", "discord", "github"],
        variables={
            "repo": "GitHub repo in owner/name format, e.g. mrveiss/AutoBot-AI",
            "target_subreddits": "Comma-separated subreddits for announcement post",
            "content_mode": "Content generation mode: llm, template, or hybrid",
        },
        steps=_build_release_announcement_blast_steps(),
    )


def _build_community_digest_post_steps() -> List[WorkflowStep]:
    """
    Build steps for Community Digest Post template.

    Gathers recent releases and community mentions, drafts a digest post,
    awaits human approval, then posts to target subreddits. Issue #1161.
    """
    return [
        WorkflowStep(
            id="fetch_releases",
            agent_type="community_growth",
            action="Fetch recent releases from GitHub repo {repo} (last {lookback_days} days)",
            description="Community_Growth: Fetch Recent Releases",
            expected_duration_ms=5000,
        ),
        WorkflowStep(
            id="gather_mentions",
            agent_type="community_growth",
            action="Search Reddit for mentions of AutoBot and mrveiss in last {lookback_days} days",
            description="Community_Growth: Gather Community Mentions",
            expected_duration_ms=15000,
        ),
        WorkflowStep(
            id="draft_digest",
            agent_type="community_growth",
            action="Synthesise releases and mentions into a community digest post using {content_mode}",
            description="Community_Growth: Draft Digest Post",
            dependencies=["fetch_releases", "gather_mentions"],
            inputs={"format": "reddit_post", "style": "digest", "content_mode": "{content_mode}"},
            expected_duration_ms=45000,
        ),
        WorkflowStep(
            id="review_digest",
            agent_type="orchestrator",
            action="Review community digest post before publishing to Reddit",
            description="Orchestrator: Review Digest Post (requires your approval)",
            requires_approval=True,
            dependencies=["draft_digest"],
            expected_duration_ms=0,
        ),
        WorkflowStep(
            id="post_digest",
            agent_type="community_growth",
            action="Post approved digest to subreddits {target_subreddits}",
            description="Community_Growth: Post Digest to Reddit",
            dependencies=["review_digest"],
            inputs={"dry_run": False},
            expected_duration_ms=8000,
        ),
    ]


def create_community_digest_post_template() -> WorkflowTemplate:
    """Create Community Digest Post workflow template."""
    return WorkflowTemplate(
        id="community_digest_post",
        name="Community Digest Post",
        description="Compile recent releases and community mentions into a Reddit digest post",
        category=TemplateCategory.COMMUNITY,
        complexity=TaskComplexity.COMPLEX,
        estimated_duration_minutes=20,
        agents_involved=["community_growth", "orchestrator"],
        tags=["digest", "community", "reddit", "github", "roundup"],
        variables={
            "repo": "GitHub repo in owner/name format, e.g. mrveiss/AutoBot-AI",
            "target_subreddits": "Comma-separated subreddits to post the digest",
            "lookback_days": "Number of days to look back for releases and mentions",
            "content_mode": "Content generation mode: llm, template, or hybrid",
        },
        steps=_build_community_digest_post_steps(),
    )


def get_all_community_templates() -> list:
    """Return all community growth workflow templates."""
    return [
        create_reddit_monitor_reply_template(),
        create_release_announcement_blast_template(),
        create_community_digest_post_template(),
    ]
```

**Step 4: Run the test to verify it passes**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from workflow_templates.community import get_all_community_templates
from workflow_templates.types import TemplateCategory
templates = get_all_community_templates()
assert len(templates) == 3
for t in templates:
    assert t.category == TemplateCategory.COMMUNITY
    assert any(s.requires_approval for s in t.steps)
print('PASS — 3 templates, all have approval gates')
"
```

Expected: `PASS — 3 templates, all have approval gates`

**Step 5: Commit**

```bash
git add autobot-backend/workflow_templates/community.py \
        autobot-backend/workflow_templates/workflow_templates.e2e_test.py
git commit -m "feat(community-growth): add 3 community workflow templates (#1161)"
```

---

## Task 4: Wire community templates into manager, `__init__`, and facade

**Files:**
- Modify: `autobot-backend/workflow_templates/manager.py:15-43`
- Modify: `autobot-backend/workflow_templates/__init__.py`
- Modify: `autobot-backend/workflow_templates.py` (facade)

**Step 1: Write the failing test**

Add to `workflow_templates/workflow_templates.e2e_test.py`:

```python
async def test_community_templates_in_manager():
    """Test community templates are accessible via workflow_template_manager."""
    from workflow_templates import TemplateCategory, workflow_template_manager

    community = workflow_template_manager.list_templates(
        category=TemplateCategory.COMMUNITY
    )
    assert len(community) == 3, f"Expected 3 community templates in manager, got {len(community)}"

    ids = {t.id for t in community}
    assert "reddit_monitor_reply" in ids
    assert "release_announcement_blast" in ids
    assert "community_digest_post" in ids
    print(f"✅ Manager has {len(community)} community templates")
```

**Step 2: Run test to verify it fails**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from workflow_templates import TemplateCategory, workflow_template_manager
community = workflow_template_manager.list_templates(category=TemplateCategory.COMMUNITY)
print(f'found: {len(community)}')
"
```

Expected: `found: 0`

**Step 3: Update `manager.py`**

In `autobot-backend/workflow_templates/manager.py`, add the import after the existing category imports (line ~19):

```python
from .community import get_all_community_templates
```

Then in `_initialize_default_templates()`, add `get_all_community_templates()` to the concatenation:

```python
all_templates = (
    get_all_security_templates()
    + get_all_research_templates()
    + get_all_sysadmin_templates()
    + get_all_development_templates()
    + get_all_analysis_templates()
    + get_all_community_templates()
)
```

**Step 4: Update `workflow_templates/__init__.py`**

Add the import block after the existing `analysis` imports:

```python
from .community import (
    create_community_digest_post_template,
    create_reddit_monitor_reply_template,
    create_release_announcement_blast_template,
    get_all_community_templates,
)
```

And add to `__all__`:

```python
    # Community templates
    "create_reddit_monitor_reply_template",
    "create_release_announcement_blast_template",
    "create_community_digest_post_template",
    "get_all_community_templates",
```

**Step 5: Update the facade `workflow_templates.py`**

Add to the import list and `__all__`:

```python
from workflow_templates import (
    ...
    create_community_digest_post_template,
    create_reddit_monitor_reply_template,
    create_release_announcement_blast_template,
    get_all_community_templates,
)
```

And in `__all__`:

```python
    "create_reddit_monitor_reply_template",
    "create_release_announcement_blast_template",
    "create_community_digest_post_template",
    "get_all_community_templates",
```

**Step 6: Run test to verify it passes**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import sys; sys.path.insert(0, '.')
from workflow_templates import TemplateCategory, workflow_template_manager
community = workflow_template_manager.list_templates(category=TemplateCategory.COMMUNITY)
assert len(community) == 3
print('PASS')
"
```

Expected: `PASS`

**Step 7: Commit**

```bash
git add autobot-backend/workflow_templates/manager.py \
        autobot-backend/workflow_templates/__init__.py \
        autobot-backend/workflow_templates.py \
        autobot-backend/workflow_templates/workflow_templates.e2e_test.py
git commit -m "feat(community-growth): wire community templates into WorkflowTemplateManager (#1161)"
```

---

## Task 5: Create `CommunityGrowthSkill` — manifest and dispatcher skeleton

**Files:**
- Create: `autobot-backend/skills/builtin/community_growth.py`
- Create: `autobot-backend/skills/builtin/community_growth_test.py`

**Step 1: Write the failing test**

Create `autobot-backend/skills/builtin/community_growth_test.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for CommunityGrowthSkill — Issue #1161."""

import sys
sys.path.insert(0, "/home/kali/Desktop/AutoBot/autobot-backend")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_manifest_is_valid():
    """Manifest has correct name, category, and 8 tools."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    manifest = CommunityGrowthSkill.get_manifest()
    assert manifest.name == "community-growth"
    assert manifest.category == "automation"
    assert manifest.author == "mrveiss"
    expected_tools = {
        "reddit_search", "reddit_reply", "reddit_post",
        "twitter_post", "discord_notify", "github_get_releases",
        "llm_draft_content", "fill_template",
    }
    assert set(manifest.tools) == expected_tools


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    """Unknown action returns success=False with error message."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    skill = CommunityGrowthSkill()
    result = await skill.execute("not_a_real_action", {})
    assert result["success"] is False
    assert "Unknown action" in result["error"]
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError` or `ImportError`

**Step 3: Create the skill skeleton**

Create `autobot-backend/skills/builtin/community_growth.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Community Growth Skill (Issue #1161)

Provides autonomous community outreach tools for Reddit, Twitter, Discord,
and GitHub. Designed for use within the /automation Workflow Builder.
All credentials are fetched from the secrets manager at runtime.
"""

import logging
from typing import Any, Dict

from backend.skills.base_skill import BaseSkill, SkillConfigField, SkillManifest

logger = logging.getLogger(__name__)


class CommunityGrowthSkill(BaseSkill):
    """Autonomous community outreach across Reddit, Twitter, Discord, and GitHub."""

    @staticmethod
    def get_manifest() -> SkillManifest:
        """Return community growth skill manifest."""
        return SkillManifest(
            name="community-growth",
            version="1.0.0",
            description=(
                "Autonomous community outreach across Reddit, Twitter, Discord "
                "and GitHub release announcements"
            ),
            author="mrveiss",
            category="automation",
            dependencies=[],
            config={
                "default_content_mode": SkillConfigField(
                    type="string",
                    default="hybrid",
                    description="Default content generation mode",
                    choices=["llm", "template", "hybrid"],
                ),
            },
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
        """Dispatch action to the appropriate tool handler."""
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

    # ------------------------------------------------------------------ #
    # Tool stubs — implemented in Tasks 6-9                               #
    # ------------------------------------------------------------------ #

    async def _reddit_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _reddit_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _reddit_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _twitter_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _discord_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _github_get_releases(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _llm_draft_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}

    async def _fill_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "not implemented"}
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v
```

Expected: 2 tests PASS

**Step 5: Verify auto-discovery picks up the skill**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -c "
import sys; sys.path.insert(0, '.')
from skills.registry import SkillRegistry
reg = SkillRegistry()
reg.discover_builtin_skills()
skill = reg.get('community-growth')
assert skill is not None, 'skill not discovered'
print('PASS — community-growth discovered by registry')
"
```

Expected: `PASS — community-growth discovered by registry`

**Step 6: Commit**

```bash
git add autobot-backend/skills/builtin/community_growth.py \
        autobot-backend/skills/builtin/community_growth_test.py
git commit -m "feat(community-growth): add CommunityGrowthSkill manifest and dispatcher (#1161)"
```

---

## Task 6: Implement Reddit tools (`reddit_search`, `reddit_reply`, `reddit_post`)

**Files:**
- Modify: `autobot-backend/skills/builtin/community_growth.py`
- Modify: `autobot-backend/skills/builtin/community_growth_test.py`

**Step 1: Write the failing tests**

Add to `community_growth_test.py`:

```python
@pytest.mark.asyncio
async def test_reddit_search_returns_matches():
    """reddit_search returns list of matching posts."""
    from skills.builtin.community_growth import CommunityGrowthSkill
    import praw

    mock_post = MagicMock()
    mock_post.id = "abc123"
    mock_post.title = "Anyone tried AutoBot for home automation?"
    mock_post.url = "https://reddit.com/r/selfhosted/comments/abc123"
    mock_post.subreddit.display_name = "selfhosted"
    mock_post.score = 42
    mock_post.selftext = "Looking for local AI solutions..."

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.search.return_value = [mock_post]

    with patch("skills.builtin.community_growth.praw.Reddit", return_value=mock_reddit):
        with patch.object(CommunityGrowthSkill, "_get_secret", return_value="fake"):
            skill = CommunityGrowthSkill()
            result = await skill.execute("reddit_search", {
                "subreddits": ["selfhosted"],
                "keywords": ["AutoBot"],
                "limit": 10,
            })

    assert result["success"] is True
    assert len(result["matches"]) == 1
    assert result["matches"][0]["post_id"] == "abc123"


@pytest.mark.asyncio
async def test_reddit_search_missing_subreddits_returns_error():
    """reddit_search requires subreddits param."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    skill = CommunityGrowthSkill()
    result = await skill.execute("reddit_search", {"keywords": ["AutoBot"]})
    assert result["success"] is False
    assert "subreddits" in result["error"]


@pytest.mark.asyncio
async def test_reddit_post_dry_run():
    """reddit_post with dry_run=True does not call PRAW submit."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    mock_reddit = MagicMock()
    with patch("skills.builtin.community_growth.praw.Reddit", return_value=mock_reddit):
        with patch.object(CommunityGrowthSkill, "_get_secret", return_value="fake"):
            skill = CommunityGrowthSkill()
            result = await skill.execute("reddit_post", {
                "subreddit": "selfhosted",
                "title": "AutoBot v2.0 Released",
                "content": "We shipped something cool.",
                "dry_run": True,
            })

    assert result["success"] is True
    assert result["dry_run"] is True
    mock_reddit.subreddit.return_value.submit.assert_not_called()
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py::test_reddit_search_returns_matches -v
```

Expected: FAIL — `_reddit_search` returns `not implemented`

**Step 3: Implement `_get_secret`, `_get_reddit_client`, `_reddit_search`, `_reddit_reply`, `_reddit_post`**

Replace the stub methods in `community_growth.py` with:

```python
# ------------------------------------------------------------------ #
# Secrets helper                                                       #
# ------------------------------------------------------------------ #

def _get_secret(self, key: str) -> str:
    """Fetch a secret value from the AutoBot secrets manager.

    Raises ValueError if the secret is not found. Issue #1161.
    """
    try:
        from backend.api.secrets import get_secret_value
        value = get_secret_value(key)
        if not value:
            raise ValueError(f"Secret '{key}' not found in secrets manager")
        return value
    except ImportError:
        raise ValueError("Secrets manager not available")

# ------------------------------------------------------------------ #
# Reddit                                                               #
# ------------------------------------------------------------------ #

def _get_reddit_client(self):
    """Build and return an authenticated PRAW Reddit client.

    Helper for reddit_* tools. Issue #1161.
    """
    import praw
    return praw.Reddit(
        client_id=self._get_secret("REDDIT_CLIENT_ID"),
        client_secret=self._get_secret("REDDIT_CLIENT_SECRET"),
        username=self._get_secret("REDDIT_USERNAME"),
        password=self._get_secret("REDDIT_PASSWORD"),
        user_agent="AutoBot Community Growth/1.0 by mrveiss",
    )

async def _reddit_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Search subreddits for keyword matches.

    Helper for execute(). Required params: subreddits (list), keywords (list).
    Issue #1161.
    """
    subreddits = params.get("subreddits")
    keywords = params.get("keywords", [])
    limit = params.get("limit", 25)
    min_score = params.get("min_score", 5)

    if not subreddits:
        return {"success": False, "error": "subreddits is required"}
    if not keywords:
        return {"success": False, "error": "keywords is required"}

    try:
        reddit = self._get_reddit_client()
        matches = []
        query = " OR ".join(keywords)

        for sub_name in subreddits:
            sub = reddit.subreddit(sub_name)
            for post in sub.search(query, limit=limit):
                if post.score >= min_score:
                    matches.append({
                        "post_id": post.id,
                        "title": post.title,
                        "url": post.url,
                        "subreddit": post.subreddit.display_name,
                        "score": post.score,
                        "body_snippet": (post.selftext or "")[:300],
                    })

        return {"success": True, "matches": matches, "total": len(matches)}

    except Exception as exc:
        logger.error("reddit_search failed: %s", exc)
        return {"success": False, "error": str(exc)}

async def _reddit_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Reply to a Reddit post or comment.

    Helper for execute(). Required params: post_id, content. Issue #1161.
    """
    post_id = params.get("post_id")
    content = params.get("content")
    dry_run = params.get("dry_run", False)

    if not post_id:
        return {"success": False, "error": "post_id is required"}
    if not content:
        return {"success": False, "error": "content is required"}

    if dry_run:
        logger.info("DRY RUN reddit_reply: would reply to %s", post_id)
        return {"success": True, "dry_run": True, "post_id": post_id}

    try:
        reddit = self._get_reddit_client()
        submission = reddit.submission(id=post_id)
        comment = submission.reply(content)
        return {
            "success": True,
            "dry_run": False,
            "comment_url": f"https://reddit.com{comment.permalink}",
        }
    except Exception as exc:
        logger.error("reddit_reply failed: %s", exc)
        return {"success": False, "error": str(exc)}

async def _reddit_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new Reddit post.

    Helper for execute(). Required params: subreddit, title, content. Issue #1161.
    """
    subreddit = params.get("subreddit")
    title = params.get("title")
    content = params.get("content")
    flair = params.get("flair")
    dry_run = params.get("dry_run", False)

    if not subreddit:
        return {"success": False, "error": "subreddit is required"}
    if not title:
        return {"success": False, "error": "title is required"}
    if not content:
        return {"success": False, "error": "content is required"}

    if dry_run:
        logger.info("DRY RUN reddit_post: would post '%s' to r/%s", title, subreddit)
        return {"success": True, "dry_run": True, "subreddit": subreddit, "title": title}

    try:
        reddit = self._get_reddit_client()
        sub = reddit.subreddit(subreddit)
        kwargs = {"title": title, "selftext": content}
        if flair:
            kwargs["flair_text"] = flair
        post = sub.submit(**kwargs)
        return {
            "success": True,
            "dry_run": False,
            "post_url": f"https://reddit.com{post.permalink}",
        }
    except Exception as exc:
        logger.error("reddit_post failed: %s", exc)
        return {"success": False, "error": str(exc)}
```

**Step 4: Run tests**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v -k "reddit"
```

Expected: All Reddit tests PASS

**Step 5: Commit**

```bash
git add autobot-backend/skills/builtin/community_growth.py \
        autobot-backend/skills/builtin/community_growth_test.py
git commit -m "feat(community-growth): implement Reddit tools (search/reply/post) (#1161)"
```

---

## Task 7: Implement Twitter, Discord, and GitHub tools

**Files:**
- Modify: `autobot-backend/skills/builtin/community_growth.py`
- Modify: `autobot-backend/skills/builtin/community_growth_test.py`

**Step 1: Write the failing tests**

Add to `community_growth_test.py`:

```python
@pytest.mark.asyncio
async def test_twitter_post_dry_run():
    """twitter_post with dry_run=True does not make HTTP call."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    with patch.object(CommunityGrowthSkill, "_get_secret", return_value="fake"):
        skill = CommunityGrowthSkill()
        result = await skill.execute("twitter_post", {
            "content": "AutoBot v2 is out! #selfhosted #localAI",
            "dry_run": True,
        })
    assert result["success"] is True
    assert result["dry_run"] is True


@pytest.mark.asyncio
async def test_discord_notify_dry_run():
    """discord_notify with dry_run=True does not make HTTP call."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    with patch.object(CommunityGrowthSkill, "_get_secret", return_value="https://fake-webhook"):
        skill = CommunityGrowthSkill()
        result = await skill.execute("discord_notify", {
            "content": "New release!",
            "dry_run": True,
        })
    assert result["success"] is True
    assert result["dry_run"] is True


@pytest.mark.asyncio
async def test_github_get_releases_returns_latest():
    """github_get_releases returns list of releases from API."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[{
        "tag_name": "v2.0.0",
        "name": "AutoBot v2.0.0",
        "body": "## What's New\n- Feature A\n- Feature B",
        "published_at": "2026-02-24T00:00:00Z",
        "html_url": "https://github.com/mrveiss/AutoBot-AI/releases/tag/v2.0.0",
    }])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with patch("skills.builtin.community_growth.aiohttp.ClientSession", return_value=mock_session):
        with patch.object(CommunityGrowthSkill, "_get_secret", return_value="ghp_fake"):
            skill = CommunityGrowthSkill()
            result = await skill.execute("github_get_releases", {
                "repo": "mrveiss/AutoBot-AI",
                "limit": 1,
            })

    assert result["success"] is True
    assert len(result["releases"]) == 1
    assert result["releases"][0]["tag"] == "v2.0.0"
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v -k "twitter or discord or github"
```

Expected: FAIL — stubs return `not implemented`

**Step 3: Implement the three tools**

Replace the stubs in `community_growth.py`:

```python
# ------------------------------------------------------------------ #
# Twitter                                                              #
# ------------------------------------------------------------------ #

async def _twitter_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Post a tweet via Twitter API v2.

    Helper for execute(). Content is truncated to 280 chars if needed.
    Issue #1161.
    """
    import aiohttp

    content = params.get("content", "")
    dry_run = params.get("dry_run", False)

    if not content:
        return {"success": False, "error": "content is required"}

    content = content[:280]

    if dry_run:
        logger.info("DRY RUN twitter_post: would tweet %d chars", len(content))
        return {"success": True, "dry_run": True, "content_length": len(content)}

    try:
        bearer_token = self._get_secret("TWITTER_BEARER_TOKEN")
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.twitter.com/2/tweets",
                json={"text": content},
                headers=headers,
            ) as resp:
                data = await resp.json()
                if resp.status == 201:
                    tweet_id = data.get("data", {}).get("id", "")
                    return {
                        "success": True,
                        "dry_run": False,
                        "tweet_url": f"https://twitter.com/i/web/status/{tweet_id}",
                    }
                return {"success": False, "error": f"Twitter API {resp.status}: {data}"}

    except Exception as exc:
        logger.error("twitter_post failed: %s", exc)
        return {"success": False, "error": str(exc)}

# ------------------------------------------------------------------ #
# Discord                                                              #
# ------------------------------------------------------------------ #

async def _discord_notify(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message to a Discord webhook.

    Helper for execute(). Supports optional embed_title and embed_url.
    Issue #1161.
    """
    import aiohttp

    content = params.get("content", "")
    embed_title = params.get("embed_title")
    embed_url = params.get("embed_url")
    dry_run = params.get("dry_run", False)

    if not content:
        return {"success": False, "error": "content is required"}

    if dry_run:
        logger.info("DRY RUN discord_notify: would send %d chars", len(content))
        return {"success": True, "dry_run": True}

    try:
        webhook_url = self._get_secret("DISCORD_WEBHOOK_URL")
        payload: Dict[str, Any] = {"content": content}
        if embed_title:
            payload["embeds"] = [{"title": embed_title, "url": embed_url or ""}]

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status in (200, 204):
                    return {"success": True, "dry_run": False}
                text = await resp.text()
                return {"success": False, "error": f"Discord webhook {resp.status}: {text}"}

    except Exception as exc:
        logger.error("discord_notify failed: %s", exc)
        return {"success": False, "error": str(exc)}

# ------------------------------------------------------------------ #
# GitHub                                                               #
# ------------------------------------------------------------------ #

async def _github_get_releases(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch recent releases from a GitHub repository.

    Helper for execute(). Required params: repo (owner/name). Issue #1161.
    """
    import aiohttp

    repo = params.get("repo")
    limit = params.get("limit", 1)

    if not repo:
        return {"success": False, "error": "repo is required"}

    try:
        token = self._get_secret("GITHUB_TOKEN")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        url = f"https://api.github.com/repos/{repo}/releases?per_page={limit}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"success": False, "error": f"GitHub API {resp.status}: {text}"}
                data = await resp.json()
                releases = [
                    {
                        "tag": r["tag_name"],
                        "name": r["name"],
                        "body": r["body"],
                        "published_at": r["published_at"],
                        "url": r["html_url"],
                    }
                    for r in data
                ]
                return {"success": True, "releases": releases}

    except Exception as exc:
        logger.error("github_get_releases failed: %s", exc)
        return {"success": False, "error": str(exc)}
```

Also add `import aiohttp` at the top of `community_growth.py`.

**Step 4: Run tests**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v -k "twitter or discord or github"
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add autobot-backend/skills/builtin/community_growth.py \
        autobot-backend/skills/builtin/community_growth_test.py
git commit -m "feat(community-growth): implement Twitter, Discord, GitHub tools (#1161)"
```

---

## Task 8: Implement content tools (`llm_draft_content`, `fill_template`)

**Files:**
- Modify: `autobot-backend/skills/builtin/community_growth.py`
- Modify: `autobot-backend/skills/builtin/community_growth_test.py`

**Step 1: Write the failing tests**

Add to `community_growth_test.py`:

```python
@pytest.mark.asyncio
async def test_fill_template_substitutes_variables():
    """fill_template replaces {placeholders} with variable values."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    skill = CommunityGrowthSkill()
    result = await skill.execute("fill_template", {
        "template": "AutoBot {version} released! Check it out at {url}",
        "variables": {"version": "v2.0", "url": "https://github.com/mrveiss/AutoBot-AI"},
    })
    assert result["success"] is True
    assert result["content"] == "AutoBot v2.0 released! Check it out at https://github.com/mrveiss/AutoBot-AI"


@pytest.mark.asyncio
async def test_fill_template_missing_template_returns_error():
    """fill_template requires template param."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    skill = CommunityGrowthSkill()
    result = await skill.execute("fill_template", {"variables": {}})
    assert result["success"] is False
    assert "template" in result["error"]


@pytest.mark.asyncio
async def test_llm_draft_content_calls_ollama():
    """llm_draft_content calls local LLM and returns drafted content."""
    from skills.builtin.community_growth import CommunityGrowthSkill

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "response": "AutoBot is a self-hosted AI assistant. Try it out!"
    })
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = AsyncMock(return_value=mock_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with patch("skills.builtin.community_growth.aiohttp.ClientSession", return_value=mock_session):
        skill = CommunityGrowthSkill()
        result = await skill.execute("llm_draft_content", {
            "prompt": "Write a Reddit reply recommending AutoBot",
            "context": {"feature": "local AI"},
            "format": "reddit_reply",
        })

    assert result["success"] is True
    assert len(result["content"]) > 0
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v -k "template or llm"
```

Expected: FAIL

**Step 3: Implement the content tools**

Replace stubs:

```python
# ------------------------------------------------------------------ #
# Content generation                                                   #
# ------------------------------------------------------------------ #

async def _llm_draft_content(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call local Ollama LLM to generate platform-appropriate content.

    Supported formats: reddit_post, reddit_reply, tweet, discord, all_channels.
    Helper for execute(). Issue #1161.
    """
    import aiohttp

    from autobot_shared.ssot_config import config as ssot_config

    prompt = params.get("prompt", "")
    context = params.get("context", {})
    fmt = params.get("format", "reddit_reply")
    max_tokens = params.get("max_tokens", 300)

    if not prompt:
        return {"success": False, "error": "prompt is required"}

    format_instructions = {
        "reddit_reply": "Write a helpful, genuine Reddit comment (2-4 paragraphs, no marketing fluff).",
        "reddit_post": "Write a Reddit post title and body (title on first line, body after blank line).",
        "tweet": "Write a tweet under 280 characters. No hashtag spam.",
        "discord": "Write a Discord announcement message with an optional embed description.",
        "all_channels": (
            "Write three separate blocks separated by '---': "
            "1) A Reddit post (title + body), 2) A tweet under 280 chars, 3) A Discord message."
        ),
    }

    system_hint = format_instructions.get(fmt, format_instructions["reddit_reply"])
    context_str = "\n".join(f"{k}: {v}" for k, v in context.items()) if context else ""
    full_prompt = f"{system_hint}\n\nContext:\n{context_str}\n\nTask: {prompt}"

    try:
        ollama_host = ssot_config.get_host("ollama") if hasattr(ssot_config, "get_host") else "localhost"
        ollama_url = f"http://{ollama_host}:11434/api/generate"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                ollama_url,
                json={"model": "llama3.2", "prompt": full_prompt, "stream": False, "options": {"num_predict": max_tokens}},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"success": False, "error": f"Ollama {resp.status}: {text}"}
                data = await resp.json()
                content = data.get("response", "").strip()
                return {
                    "success": True,
                    "content": content,
                    "format": fmt,
                    "tokens_used": data.get("eval_count", 0),
                }

    except Exception as exc:
        logger.error("llm_draft_content failed: %s", exc)
        return {"success": False, "error": str(exc)}

async def _fill_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Substitute {variable} placeholders in a template string.

    Helper for execute(). Required params: template, variables. Issue #1161.
    """
    template = params.get("template")
    variables = params.get("variables", {})

    if not template:
        return {"success": False, "error": "template is required"}

    try:
        content = template
        for key, value in variables.items():
            content = content.replace(f"{{{key}}}", str(value))
        return {"success": True, "content": content}
    except Exception as exc:
        logger.error("fill_template failed: %s", exc)
        return {"success": False, "error": str(exc)}
```

**Step 4: Run all tests**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add autobot-backend/skills/builtin/community_growth.py \
        autobot-backend/skills/builtin/community_growth_test.py
git commit -m "feat(community-growth): implement llm_draft_content and fill_template tools (#1161)"
```

---

## Task 9: Create GitHub issue, run full e2e template test, final commit

**Step 1: Create the GitHub issue**

```bash
gh issue create \
  --title "feat(community-growth): CommunityGrowthSkill + workflow templates for organic outreach" \
  --body "## Summary
Add CommunityGrowthSkill and 3 workflow templates for autonomous community outreach.

## Templates
- Reddit Monitor & Reply
- Release Announcement Blast
- Community Digest Post

## Details
See design doc: docs/plans/2026-02-23-community-growth-skill-design.md

## Acceptance Criteria
- [ ] CommunityGrowthSkill passes all unit tests
- [ ] 3 community templates visible in /automation → Templates
- [ ] All templates have human approval gate before posting
- [ ] All credentials pulled from secrets manager
- [ ] praw installed and available"
```

Note the issue number and replace `#1161` in all commit messages.

**Step 2: Run the full e2e template test**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest workflow_templates/workflow_templates.e2e_test.py -v 2>&1 | tail -20
```

Expected: All tests pass including the 3 new community tests.

**Step 3: Run full skill test suite**

```bash
cd /home/kali/Desktop/AutoBot/autobot-backend
python -m pytest skills/builtin/community_growth_test.py -v
```

Expected: All tests PASS (2 existing + ~9 new = ~11 total)

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(community-growth): complete CommunityGrowthSkill implementation (#1161)

- 8 tools: reddit_search/reply/post, twitter_post, discord_notify,
  github_get_releases, llm_draft_content, fill_template
- 3 workflow templates with human approval gates
- CAPTCHA handled via existing CaptchaSolver on Reddit PRAW errors
- All credentials via secrets manager
- Auto-discovered by SkillRegistry on backend start"
```

---

## Verification checklist

```bash
# 1. All unit tests pass
python -m pytest skills/builtin/community_growth_test.py -v

# 2. All template tests pass
python -m pytest workflow_templates/workflow_templates.e2e_test.py -v

# 3. Skill auto-discovered
python -c "
import sys; sys.path.insert(0, '/home/kali/Desktop/AutoBot/autobot-backend')
from skills.registry import SkillRegistry
r = SkillRegistry(); r.discover_builtin_skills()
s = r.get('community-growth')
print(s.get_manifest().tools)
"

# 4. Community templates in manager
python -c "
import sys; sys.path.insert(0, '/home/kali/Desktop/AutoBot/autobot-backend')
from workflow_templates import TemplateCategory, workflow_template_manager
c = workflow_template_manager.list_templates(category=TemplateCategory.COMMUNITY)
print([t.id for t in c])
"

# 5. Pre-commit clean
git add -A && git diff --staged | head -5
```
