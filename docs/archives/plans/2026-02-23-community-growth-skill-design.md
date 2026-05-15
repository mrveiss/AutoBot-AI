# Community Growth Skill — Design Document

**Date:** 2026-02-23
**Author:** mrveiss
**Status:** Approved

---

## Problem

AutoBot has no mechanism to grow awareness of the project organically. Manual posting
is unsustainable. We need autonomous, multi-channel community outreach that fits inside
the existing workflow infrastructure at `/automation`.

---

## Goals

- Post and reply autonomously on Reddit, Twitter/X, Discord, and GitHub release feeds
- Human-in-the-middle approval before any content is published
- Use AutoBot's local LLM (Ollama), pre-written templates, or a hybrid — configurable per step
- Integrate CAPTCHA solving via existing `CaptchaSolver` + `captcha_human_loop.py`
- Pull all credentials from the existing secrets manager — no hardcoding
- Surface entirely inside `/automation → Templates` — no new UI pages

---

## Non-Goals

- Paid advertising or sponsored content
- Hacker News automation (manual only — community detects bots)
- Managing social media profiles (follows, DMs, etc.)

---

## Architecture

```
/automation (Workflow Builder)
    └── Templates tab
            ├── "Reddit Monitor & Reply"        ← community.py template
            ├── "Release Announcement Blast"    ← community.py template
            └── "Community Digest Post"         ← community.py template

autobot-backend/
    skills/builtin/community_growth.py          ← new BaseSkill
    workflow_templates/community.py             ← new template module
    workflow_templates/types.py                 ← +COMMUNITY category (1 line)
    workflow_templates/manager.py               ← register 3 templates
    workflow_templates/__init__.py              ← re-export new functions
    workflow_templates.py (facade)              ← re-export new functions
```

---

## Component 1: `CommunityGrowthSkill`

**File:** `autobot-backend/skills/builtin/community_growth.py`

Extends `BaseSkill`. Registered in `skills/builtin/__init__.py`.

### Manifest

```python
SkillManifest(
    name="community-growth",
    version="1.0.0",
    description="Autonomous community outreach across Reddit, Twitter, Discord and GitHub",
    author="mrveiss",
    category="automation",
    dependencies=[],
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
```

### Config fields (all sourced from secrets manager at runtime)

| Field | Secret key | Description |
|-------|-----------|-------------|
| `reddit_client_id` | `REDDIT_CLIENT_ID` | PRAW OAuth client ID |
| `reddit_client_secret` | `REDDIT_CLIENT_SECRET` | PRAW OAuth client secret |
| `reddit_username` | `REDDIT_USERNAME` | Reddit account username |
| `reddit_password` | `REDDIT_PASSWORD` | Reddit account password |
| `twitter_bearer_token` | `TWITTER_BEARER_TOKEN` | Twitter API v2 bearer token |
| `discord_webhook_url` | `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |
| `github_token` | `GITHUB_TOKEN` | GitHub personal access token |
| `default_content_mode` | — | `llm` / `template` / `hybrid` (default: `hybrid`) |

### Tools

#### `reddit_search`
```
params:
  subreddits: list[str]   # e.g. ["selfhosted", "LocalLLaMA", "homelab"]
  keywords: list[str]     # e.g. ["local AI assistant", "self-hosted automation"]
  limit: int              # posts to scan per subreddit (default: 25)
  min_score: int          # ignore posts below this score (default: 5)
returns:
  matches: list[{post_id, title, url, subreddit, score, body_snippet}]
```

#### `reddit_reply`
```
params:
  post_id: str
  content: str
  dry_run: bool           # default false; if true, logs but does not post
returns:
  success: bool
  comment_url: str
```

#### `reddit_post`
```
params:
  subreddit: str
  title: str
  content: str
  flair: str | None
  dry_run: bool
returns:
  success: bool
  post_url: str
```

#### `twitter_post`
```
params:
  content: str            # max 280 chars; skill truncates if over
  dry_run: bool
returns:
  success: bool
  tweet_url: str
```

#### `discord_notify`
```
params:
  content: str
  embed_title: str | None
  embed_url: str | None
  dry_run: bool
returns:
  success: bool
```

#### `github_get_releases`
```
params:
  repo: str               # e.g. "mrveiss/AutoBot-AI"
  limit: int              # default 1 (latest only)
returns:
  releases: list[{tag, name, body, published_at, url}]
```

#### `llm_draft_content`
```
params:
  prompt: str             # instruction for the LLM
  context: dict           # variables injected into the prompt
  format: str             # "reddit_post" | "tweet" | "discord" | "reddit_reply"
  max_tokens: int         # default 300
returns:
  content: str
  tokens_used: int
```

#### `fill_template`
```
params:
  template: str           # string with {variable} placeholders
  variables: dict         # values to substitute
returns:
  content: str
```

### Content modes

Each tool that produces content accepts an optional `content_mode` override:

| Mode | Behaviour |
|------|-----------|
| `llm` | Calls `llm_draft_content` to generate fresh content |
| `template` | Uses a pre-written template string with `{variable}` substitution |
| `hybrid` | Template provides the scaffold; LLM fills in context-specific detail |

### CAPTCHA handling

PRAW uses OAuth — no CAPTCHA required for normal API operation. If Reddit returns a
challenge (new account, rate limit trigger, or IP block):

1. Skill calls `CaptchaSolver.attempt_solve(page, captcha_type)` (OCR auto-solve)
2. On failure → delegates to `captcha_human_loop.py` (human-in-the-loop fallback)
3. On repeated failures → step returns `{"success": False, "error": "captcha_blocked"}`,
   workflow pauses and notifies operator

---

## Component 2: Workflow Templates

**File:** `autobot-backend/workflow_templates/community.py`

### Template 1 — "Reddit Monitor & Reply"

**ID:** `reddit_monitor_reply`
**Category:** `COMMUNITY`
**Estimated duration:** 15 min
**Variables:** `subreddits`, `keywords`, `autobot_url`

```
Step 1: reddit_search        agent_type=community_growth   requires_approval=False
Step 2: llm_draft_content    agent_type=community_growth   requires_approval=False
         inputs: {format: "reddit_reply", context: step1.matches}
Step 3: review_drafts        agent_type=orchestrator       requires_approval=True
         description: "Review drafted replies before posting"
Step 4: reddit_reply         agent_type=community_growth   requires_approval=False
         dependencies: [review_drafts]
```

### Template 2 — "Release Announcement Blast"

**ID:** `release_announcement_blast`
**Category:** `COMMUNITY`
**Estimated duration:** 10 min
**Variables:** `repo`, `target_subreddits`, `discord_webhook_url`

```
Step 1: github_get_releases  agent_type=community_growth   requires_approval=False
Step 2: llm_draft_content    agent_type=community_growth   requires_approval=False
         inputs: {format: "all_channels", context: step1.releases[0]}
Step 3: review_content       agent_type=orchestrator       requires_approval=True
         description: "Review release content for Reddit, Twitter and Discord"
Step 4a: reddit_post         agent_type=community_growth   dependencies: [review_content]
Step 4b: twitter_post        agent_type=community_growth   dependencies: [review_content]
Step 4c: discord_notify      agent_type=community_growth   dependencies: [review_content]
```

### Template 3 — "Community Digest Post"

**ID:** `community_digest_post`
**Category:** `COMMUNITY`
**Estimated duration:** 20 min
**Variables:** `repo`, `target_subreddits`, `lookback_days`

```
Step 1a: github_get_releases agent_type=community_growth   requires_approval=False
Step 1b: reddit_search       agent_type=community_growth   requires_approval=False
          inputs: {keywords: ["autobot", "mrveiss"]}
Step 2:  llm_draft_content   agent_type=community_growth   requires_approval=False
          dependencies: [step1a, step1b]
          inputs: {format: "reddit_post", style: "digest"}
Step 3:  review_digest       agent_type=orchestrator       requires_approval=True
          description: "Review community digest post before publishing"
Step 4:  reddit_post         agent_type=community_growth   dependencies: [review_digest]
```

---

## Component 3: Wiring Changes

### `workflow_templates/types.py`
Add one value to `TemplateCategory`:
```python
COMMUNITY = "community"
```

### `workflow_templates/manager.py`
Import and register community templates in `_load_builtin_templates()`:
```python
from .community import get_all_community_templates
templates.extend(get_all_community_templates())
```

### `workflow_templates/__init__.py` and `workflow_templates.py` (facade)
Re-export:
```python
from .community import (
    create_reddit_monitor_reply_template,
    create_release_announcement_blast_template,
    create_community_digest_post_template,
    get_all_community_templates,
)
```

### `skills/builtin/__init__.py`
Register `CommunityGrowthSkill` alongside existing builtin skills.

---

## Human-in-the-Middle Flow

The existing workflow runner at `/automation → Runner` already handles
`requires_approval=True` steps by:
1. Pausing execution
2. Displaying the step output (drafted content) in the UI
3. Waiting for operator approval or rejection before proceeding

No UI changes needed. The approval gate is purely a template-level concern.

---

## Dependencies

| Package | Use | Already installed? |
|---------|-----|--------------------|
| `praw` | Reddit OAuth API | Check requirements.txt |
| `tweepy` or `httpx` | Twitter API v2 | `httpx` already present |
| `httpx` | Discord webhook, GitHub API | Already present |

---

## Testing

- Unit tests: `skills/builtin/community_growth_test.py`
  - Mock PRAW, Twitter, Discord, GitHub responses
  - Test all 8 tools with success + error paths
  - Test each content mode: `llm`, `template`, `hybrid`
- Template tests: extend `workflow_templates/workflow_templates.e2e_test.py`
  - Verify 3 templates load, step counts, approval step counts, variable substitution
- Integration: manual run with `dry_run=True` on all posting tools

---

## Implementation Order

1. `workflow_templates/types.py` — add `COMMUNITY` (1 line)
2. `workflow_templates/community.py` — 3 templates
3. `workflow_templates/manager.py` + `__init__.py` + facade — wiring
4. `skills/builtin/community_growth.py` — skill + all 8 tools
5. `skills/builtin/__init__.py` — register skill
6. Tests
7. Verify `praw` in requirements; add if missing
