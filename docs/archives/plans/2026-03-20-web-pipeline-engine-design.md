# Web Pipeline Engine — Design Document

> **Date:** 2026-03-20
> **Issue:** #1967
> **Status:** Approved
> **Inspired by:** [jackwener/opencli](https://github.com/jackwener/opencli) (reference only — no code dependency)

## Overview

Add a declarative web automation pipeline system to AutoBot. Agents, the knowledge system, and users can define web scraping/automation tasks as YAML pipelines with composable steps. The system includes XHR interception, accessibility snapshots, auth strategy detection, AI-powered API discovery, and self-extending adapter synthesis.

**Use cases:**
- Agent-driven web research (extending web_researcher)
- User-triggered web automation via chat UI
- Knowledge ingestion from structured web data (extending web_crawler_connector)

## Architecture

```
User/Agent Request
  ↓
Browser MCP (new tools: intercept_api, page_snapshot, run_pipeline, explore_site, etc.)
  ↓
Pipeline Engine (YAML parser → step executor)
  ├─ navigate, evaluate, fetch (existing Playwright service)
  ├─ intercept, snapshot (Phase 1)
  ├─ select, map, filter, sort, limit (Phase 2)
  └─ auth cascade (Phase 3)
  ↓
Playwright Service → Browser VM (.25)
  ↓
Results → Agent / Knowledge Base / Chat UI
```

**Key decisions:**
- Lives in `autobot-backend/services/web_pipeline/` as a new service package
- Exposed via existing `browser_mcp.py` as additional MCP tools (no new API router)
- YAML adapter files stored in `autobot-backend/services/web_pipeline/adapters/`
- Pipeline engine is reusable by web_researcher agent, web_crawler_connector, and browser_automation skill
- All Python-native — no Node.js dependencies

---

## Phase 1: XHR Interceptor + Accessibility Snapshot

**Goal:** Two standalone MCP tools that deliver immediate value to agents.

### Tool: `intercept_api`

Injects a fetch/XHR monkey-patch into the page that captures API responses matching a URL pattern. Returns structured JSON.

```python
# Usage by agent:
intercept_api(url="https://reddit.com", pattern="/api/hot", trigger="scroll", wait_seconds=5)
# Returns: [{"data": {"children": [...]}}]
```

How it works:
1. Navigate to URL (or use current page)
2. Inject JS that patches `window.fetch` and `XMLHttpRequest.prototype`
3. Execute trigger action (scroll, click, or wait)
4. Collect captured responses from `window.__autobot_intercepted`
5. Return parsed JSON array

### Tool: `page_snapshot`

Captures the page's accessibility tree — semantic structure (roles, names, values) instead of raw HTML. Token-efficient for LLM consumption.

```python
# Usage by agent:
page_snapshot(url="https://news.ycombinator.com", interactive_only=False)
# Returns: structured tree of {role, name, value, children}
```

How it works:
1. Navigate to URL (or use current page)
2. Call `page.accessibility.snapshot()` via Playwright
3. Optionally filter to interactive elements only
4. Return formatted tree

### Security
- Interceptor JS is generated server-side (not user-supplied) — only the URL pattern is parameterized
- URL whitelist from existing browser_mcp applies
- Rate limiting applies same as other browser tools

### Files
| File | Action |
|------|--------|
| `services/web_pipeline/__init__.py` | New — package init |
| `services/web_pipeline/interceptor.py` | New — JS interceptor generator + result collector |
| `services/web_pipeline/snapshot.py` | New — accessibility tree capture |
| `api/browser_mcp.py` | Modify — register 2 new MCP tools |
| `services/playwright_service.py` | Modify — add `inject_js()` and `get_accessibility_tree()` methods |

---

## Phase 2: Pipeline Engine + Step Library

**Goal:** YAML-driven pipeline executor with composable steps.

### Pipeline Engine

```python
class PipelineEngine:
    def __init__(self, playwright_service, config):
        self.steps = {
            "navigate": step_navigate,
            "fetch": step_fetch,
            "evaluate": step_evaluate,
            "intercept": step_intercept,    # from Phase 1
            "snapshot": step_snapshot,       # from Phase 1
            "select": step_select,
            "map": step_map,
            "filter": step_filter,
            "sort": step_sort,
            "limit": step_limit,
            "click": step_click,
            "type": step_type,
            "wait": step_wait,
        }

    async def execute(self, yaml_def: dict, args: dict) -> list[dict]:
        ctx = PipelineContext(args=args, data=None, page=None)
        for step in yaml_def["pipeline"]:
            step_name, step_config = next(iter(step.items()))
            handler = self.steps[step_name]
            ctx = await handler(ctx, step_config)
        return ctx.data
```

### YAML Adapter Format

```yaml
name: reddit-hot
description: Hot posts from Reddit
domain: www.reddit.com
strategy: cookie
browser: true

args:
  subreddit:
    type: str
    default: all
  limit:
    type: int
    default: 20

pipeline:
  - navigate: https://www.reddit.com/r/${{ args.subreddit }}
  - intercept:
      pattern: /svc/shreddit/community-more-posts
      trigger: scroll
      wait_seconds: 3
  - select: data.children
  - map:
      title: ${{ item.data.title }}
      score: ${{ item.data.score }}
      author: ${{ item.data.author }}
      url: ${{ item.data.permalink }}
  - sort: { by: score, order: desc }
  - limit: ${{ args.limit }}
```

### Template Expression Engine

Evaluates `${{ ... }}` expressions — safe subset only. No `eval()`, no arbitrary Python.

```python
# Supports:
${{ args.limit }}           # argument access
${{ item.title }}           # current item field
${{ index + 1 }}            # basic arithmetic
${{ item.score > 100 }}     # comparisons (for filter)

# Blocked:
${{ __import__('os') }}     # blocked
${{ eval(...) }}            # blocked
```

Implemented as a simple AST parser using Python's `ast.parse` in `ast.Expression` mode with a restricted node visitor.

### New MCP Tool: `run_pipeline`

```python
# Run a named adapter:
run_pipeline(adapter="reddit/hot", args={"subreddit": "programming", "limit": 10})

# Or inline pipeline (no adapter file):
run_pipeline(pipeline=[...steps...], args={...})
```

### Files
| File | Action |
|------|--------|
| `services/web_pipeline/engine.py` | New — PipelineEngine + PipelineContext |
| `services/web_pipeline/template.py` | New — safe expression evaluator |
| `services/web_pipeline/steps/` | New — package with one file per step type |
| `services/web_pipeline/loader.py` | New — YAML adapter discovery + loading |
| `services/web_pipeline/adapters/` | New — directory for YAML adapter files |
| `api/browser_mcp.py` | Modify — add `run_pipeline` tool |

---

## Phase 3: Auth Strategy Cascade

**Goal:** Auto-detect the right authentication approach per domain.

### 5-Tier Strategy

| Tier | Name | Method | Example |
|------|------|--------|---------|
| 1 | `public` | No auth — direct HTTP fetch | Hacker News, RSS |
| 2 | `cookie` | Browser fetch with `credentials: include` | Bilibili, Zhihu |
| 3 | `header` | Custom headers (Bearer, CSRF) | Twitter GraphQL |
| 4 | `intercept` | XHR intercept to extract auth from SPA state | SPAs with Pinia/Redux |
| 5 | `ui` | Full UI automation | Last resort |

### Cascade Logic

```python
class AuthCascade:
    async def detect_strategy(self, url: str, domain: str) -> AuthStrategy:
        # Tier 1: Try public fetch
        resp = await self.http_fetch(url)
        if resp.status == 200 and has_data(resp):
            return AuthStrategy.PUBLIC

        # Tier 2: Browser fetch with cookies
        resp = await self.browser_fetch(url, credentials="include")
        if resp.status == 200 and has_data(resp):
            return AuthStrategy.COOKIE

        # Tier 3: Custom headers
        headers = await self.detect_required_headers(domain)
        if headers:
            return AuthStrategy.HEADER

        # Tier 4: SPA state stores
        stores = await self.detect_spa_stores(domain)
        if stores:
            return AuthStrategy.INTERCEPT

        # Tier 5: Fallback
        return AuthStrategy.UI
```

Results cached in Redis (`knowledge` db) with 24h TTL keyed by domain.

### Files
| File | Action |
|------|--------|
| `services/web_pipeline/auth.py` | New — AuthStrategy enum + AuthCascade |
| `services/web_pipeline/engine.py` | Modify — strategy-aware step execution |
| `services/web_pipeline/steps/fetch.py` | Modify — use strategy for auth method |
| `services/web_pipeline/steps/intercept.py` | Modify — extract headers/tokens when strategy=HEADER |

---

## Phase 4: API Discovery (Explore)

**Goal:** Navigate to any URL, capture network traffic, analyze responses, infer capabilities.

### New MCP Tool: `explore_site`

```python
explore_site(url="https://www.reddit.com/r/programming", scroll=True, click_selectors=[])
# Returns structured report with endpoints, auth indicators, field analysis, inferred capabilities
```

### How It Works

1. Navigate to URL
2. Install XHR interceptor (from Phase 1)
3. Auto-scroll page (trigger lazy loading)
4. Optionally click provided selectors (trigger hidden APIs)
5. Collect all captured network requests
6. Analyze: deduplicate by URL pattern, score endpoints, detect auth, detect field roles, infer capabilities
7. Return structured report

### Field Role Detection

```python
FIELD_ROLES = {
    "text": ["title", "name", "description", "content", "body", "text", "summary"],
    "numeric": ["score", "count", "likes", "views", "upvotes", "karma", "price"],
    "url": ["url", "link", "href", "permalink", "src", "thumbnail"],
    "timestamp": ["created", "updated", "date", "time", "published", "timestamp"],
    "user": ["author", "user", "username", "creator", "poster"],
}
```

### Endpoint Scoring

| Signal | Score |
|--------|-------|
| Returns JSON | +0.3 |
| Response contains array | +0.2 |
| Array items have 3+ fields | +0.2 |
| Has pagination params | +0.1 |
| Status 200 | +0.1 |
| URL contains `/api/` or `/v1/` | +0.1 |

### Files
| File | Action |
|------|--------|
| `services/web_pipeline/explore.py` | New — site explorer + network analyzer |
| `services/web_pipeline/field_roles.py` | New — field heuristics + endpoint scoring |
| `api/browser_mcp.py` | Modify — register `explore_site` tool |

---

## Phase 5: Adapter Registry + Auto-Synthesis

**Goal:** Store adapters persistently, auto-generate from explore results, integrate with knowledge base.

### Adapter Registry

```python
class AdapterRegistry:
    async def list_adapters(self, domain=None) -> list[AdapterMeta]
    async def get_adapter(self, name: str) -> dict
    async def register_adapter(self, yaml_content: str, source: str) -> AdapterMeta
    async def delete_adapter(self, name: str) -> bool
    async def search_adapters(self, query: str) -> list[AdapterMeta]
```

**Storage layout:**
```
services/web_pipeline/adapters/
  ├─ builtin/              # shipped with AutoBot, version-controlled
  └─ discovered/           # auto-generated, gitignored
```

### Auto-Synthesizer

Takes `explore_site` results and generates working YAML adapters.

### New MCP Tools

- `synthesize_adapters(explore_result={...})` — Generate YAML adapters from explore results
- `register_adapter(yaml="...", source="auto-synthesized")` — Save adapter to registry
- `list_adapters(domain="reddit.com")` — Search available adapters

### Knowledge Base Integration

```python
run_pipeline(adapter="reddit/hot", args={...}, ingest_to_knowledge=True)
# Runs pipeline → returns results AND stores in knowledge base via web_crawler_connector
```

### Files
| File | Action |
|------|--------|
| `services/web_pipeline/registry.py` | New — AdapterRegistry |
| `services/web_pipeline/synthesizer.py` | New — AdapterSynthesizer |
| `services/web_pipeline/adapters/builtin/` | New — shipped adapters |
| `services/web_pipeline/adapters/discovered/` | New — gitignored auto-generated |
| `api/browser_mcp.py` | Modify — register 3 new tools |
| `knowledge/connectors/web_crawler.py` | Modify — accept pipeline results |
| `.gitignore` | Modify — add `adapters/discovered/` |

---

## Deliverables Summary

| Phase | New MCP Tools | New Files | Modifies |
|-------|--------------|-----------|----------|
| 1 | `intercept_api`, `page_snapshot` | 3 | 2 |
| 2 | `run_pipeline` | 8+ | 1 |
| 3 | — | 1 | 3 |
| 4 | `explore_site` | 2 | 1 |
| 5 | `synthesize_adapters`, `register_adapter`, `list_adapters` | 3+ | 3 |
| **Total** | **7 new tools** | **~17 files** | **~10 files** |

## Reference

- **opencli repo:** https://github.com/jackwener/opencli (patterns reference, not a dependency)
- **Key opencli files studied:** `engine.ts`, `interceptor.ts`, `explore.ts`, `pipeline/`, `SKILL.md`
- **AutoBot browser infra:** `services/playwright_service.py`, `api/browser_mcp.py`, `api/playwright.py`, `autobot-browser-worker/playwright-server.js`
