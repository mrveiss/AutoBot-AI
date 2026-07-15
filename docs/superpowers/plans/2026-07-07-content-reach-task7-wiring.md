# Content Reach — Task 7 (Hardening + Boot Wiring + Agent Tool) Plan

**Goal:** Make Content Reach live end-to-end *safely*: add SSRF + robots.txt guards to the URL-fetching backends, register default sources at boot, surface the `CONTENT_REACH` health probe, and expose ONE unified `content_reach` agent tool. Umbrella #10932.

**Design decisions:**

- **Anti-duplication:** existing `web_search`/`scrape_url` tools overlap content_reach's web_search/web_page — so expose a single `content_reach(source, query, url)` gateway (all 5 sources incl. new youtube/reddit/social), NOT duplicate per-source tools.
- **SSRF (required):** content_reach currently has NO URL guard while `web_fetch` enforces `autobot_shared.url_safety.is_public_url_async`. Add the same inline defense-in-depth before exposing the tool.
- **robots.txt (configurable):** respect robots.txt by default (like `web_fetch`), with an env override `AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS` (default `1`/true; set `0` to fetch regardless). Applies to the generic web-content backends.

**Global constraints:** async-first (no blocking on async paths); no `print()`; logging via `get_logger`/`logging.getLogger`; no commit trailers (mrveiss sole author); commit `feat(content-reach): <desc> (#10932)`; Black 26.3.1 + isort + ruff clean; markdown-clean docs; TDD; python3.

## Given (already on Dev_new_gui)

- `content_reach.registry.get_content_source_registry()` → singleton with async `fetch(source, request) -> ContentResult`, `list_sources()`.
- `content_reach.bootstrap.register_default_sources(registry) -> None` (SYNC).
- `content_reach.base.ContentRequest`, `ContentResult`, `BackendError`.
- `content_reach.health` already defines `@register_health_probe(KnownProbes.CONTENT_REACH)` — needs to be IMPORTED at boot.
- `autobot_shared.url_safety.is_public_url_async(url) -> bool` — canonical SSRF guard (blocks private/link-local/localhost).
- `web_fetch/robots.py` — robots.txt fetch + Redis-cached compliance check (reuse if its public API allows; else `urllib.robotparser`). `ERR_ROBOTS_BLOCKED` in `web_fetch.types`.
- `api/system_health.list_registered_probes()`.

## Part C (do FIRST) — SSRF + robots guards

**C1. Shared guard module** — new `content_reach/_url_guard.py`:

```python
import os

from content_reach.base import BackendError

_RESPECT_ROBOTS = os.environ.get("AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS", "1").strip().lower() not in ("0", "false", "no")


async def ensure_public_url(url: str) -> None:
    """Raise BackendError if url is not a public address (SSRF guard, #10932)."""
    from autobot_shared.url_safety import is_public_url_async

    if not url or not await is_public_url_async(url):
        raise BackendError(f"blocked non-public or invalid url: {url!r}")


async def ensure_robots_allowed(url: str) -> None:
    """Raise BackendError if robots.txt disallows fetching url (respect-by-default, #10932).

    No-op when AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS is 0/false. Reuse web_fetch's
    robots checker if its public API allows; otherwise urllib.robotparser with the
    content_reach user-agent. Fail-open on robots-fetch errors (log, allow) — a broken
    robots endpoint must not block content, matching web_fetch behavior.
    """
    if not _RESPECT_ROBOTS:
        return
    # Implementer: read web_fetch/robots.py for a reusable `is_allowed(url, ua)`-style
    # helper. If none is cleanly importable, use urllib.robotparser (cache per-domain).
    ...
```

Confirm the exact `web_fetch/robots.py` public surface before choosing reuse vs urllib. Keep the robots UA = the reddit UA constant style (`autobot-content-reach/1.0`).

**C2. Enforce inline in every URL-fetching backend**, immediately before the httpx/browser/caption call — `await ensure_public_url(url)` (always) and `await ensure_robots_allowed(url)` (generic web pages only):

- `sources/web_page.py` — `TrafilaturaBackend.fetch` + `JinaReaderBackend.fetch`: guard `request.url` (SSRF **and** robots) before fetching.
- `backends/browser.py` — `BrowserBackend.fetch`: guard `request.url` (SSRF + robots) before `research_url`. `BrowserSearchBackend` builds a fixed DuckDuckGo host — SSRF-guard the final url (robots N/A for a search-results page; skip robots there).
- `sources/reddit.py` — `RedditJsonBackend.fetch` url-mode: SSRF-guard `request.url` (robots N/A — reddit `.json` is an API endpoint, skip robots). Search-mode hits a fixed host — no guard.
- `sources/youtube.py` — SSRF-guard `request.url` before `extract_info`, AND SSRF-guard the extracted caption-track URL before fetching it (untrusted external url). robots N/A (yt-dlp/API).
- `sources/web_search.py` — `DdgsBackend`/`JinaSearchBackend` hit fixed API hosts; no per-url guard needed.

**C3. Tests** — `tests/content_reach/test_url_guard.py`:

- SSRF: `TrafilaturaBackend`, `RedditJsonBackend` url-mode, `BrowserBackend`, and youtube caption-url each raise `BackendError` on a private/link-local url (`169.254.169.254`, `127.0.0.1`, `10.0.0.1`) and make NO underlying fetch/browser call. Monkeypatch `is_public_url_async`→False (and one test with the real util to prove link-local is blocked).
- robots: with `AUTOBOT_CONTENT_REACH_RESPECT_ROBOTS` unset (default), a disallowed url → `BackendError`, no fetch; with it `=0`, the same url proceeds (monkeypatch the robots checker + a mocked httpx). A public+allowed url passes both guards and reaches the mocked fetch.

## Part A — Boot wiring

**A1.** `initialization/router_registry/core_routers.py` (~line 13, next to `import api.pricing_health`): add
`import content_reach.health  # noqa: F401 — registers KnownProbes.CONTENT_REACH probe (#10932)`

**A2.** `initialization/lifespan.py`: add a Phase-2 (non-critical) helper mirroring `_init_heartbeat_scheduler`, and call it from `initialize_background_services(app)`:

```python
async def _init_content_reach_registry(app: FastAPI) -> None:
    """Register default Content Reach sources (#10932). NON-CRITICAL."""
    try:
        from content_reach.bootstrap import register_default_sources
        from content_reach.registry import get_content_source_registry

        registry = get_content_source_registry()
        register_default_sources(registry)  # SYNC — do NOT await
        app.state.content_reach_registry = registry
        logger.info("Content Reach: registered %d default sources", len(registry.list_sources()))
    except Exception as exc:
        logger.warning("Content Reach registry init failed (non-critical): %s", exc)
        app.state.content_reach_registry = None
```

## Part B — Unified `content_reach` agent tool

**B1.** `tools/tool_registry.py` — add after `scrape_url`, mirroring its return shape (`{tool_name, tool_args, result, status}`):

```python
async def content_reach(self, source: str, query: str = "", url: str = "", limit: int = 5) -> Dict[str, Any]:
    """Fetch external content via a Content Reach source chain (#10932)."""
    from content_reach.base import ContentRequest
    from content_reach.registry import get_content_source_registry

    args = {"source": source, "query": query, "url": url}
    try:
        req = ContentRequest(query=query, url=url, source=source, limit=limit)
        result = await get_content_source_registry().fetch(source, req)
        if not result.success:
            return {"tool_name": "content_reach", "tool_args": args,
                    "result": f"No content: {result.metadata.get('error', 'unknown')}", "status": "error"}
        header = f"## {source} via {result.backend_used}" + (f" ({result.url})" if result.url else "")
        return {"tool_name": "content_reach", "tool_args": args,
                "result": f"{header}\n\n{result.text or '*(no content)*'}", "status": "success"}
    except Exception as exc:
        self.logger.error("content_reach failed for %s: %s", source, exc)
        return {"tool_name": "content_reach", "tool_args": args, "result": f"Error: {exc}", "status": "error"}
```

**B2.** `_get_tool_handler()` dispatch dict (keys are normalized lowercase, no underscores), near the Issue #7509 web-research entries:

```python
"contentreach": lambda args: self.content_reach(
    args.get("source", ""), args.get("query", ""), args.get("url", ""), args.get("limit", 5)
),
```

**B3.** Add `"content_reach"` to the list returned by `get_available_tools()`.

**B4.** `chat_workflow/tool_handler.py` — add `CONTENT_REACH_SCHEMA` near the other web schemas and register `"content_reach": CONTENT_REACH_SCHEMA` in `_BUILTIN_TOOL_SCHEMAS`:

```python
CONTENT_REACH_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "enum": ["web_search", "web_page", "youtube", "reddit", "social"],
                    "description": "Which content source chain to use."},
        "query": {"type": "string", "description": "Search query (web_search, reddit, youtube search)."},
        "url": {"type": "string", "description": "Target URL (web_page, youtube, reddit, social)."},
        "limit": {"type": "integer", "default": 5, "description": "Max results for search sources."},
    },
    "required": ["source"],
}
```

## Tests (wiring)

- `tests/content_reach/test_boot_wiring.py`: `import content_reach.health` → `"content_reach" in list_registered_probes()`; `register_default_sources(get_content_source_registry())` populates 5 sources (clear the singleton in a fixture).
- `tests/tools/test_content_reach_tool.py`: tool success (mock `get_content_source_registry().fetch` AsyncMock → successful `ContentResult`, assert `status=="success"`); tool unsuccessful (`ContentResult.failure` → `status=="error"`); `"content_reach" in get_available_tools()`; `"content_reach"` in `_BUILTIN_TOOL_SCHEMAS` with the 5-source enum. (Mirror existing `tests/tools/` setup.)

## Verification gate

- `python3 -m pytest autobot-backend/tests/content_reach/ autobot-backend/tests/tools/test_content_reach_tool.py -v` all green.
- `cd autobot-backend && python3 -c "import initialization.router_registry.core_routers"` clean AND registers the probe.
- black/isort/ruff clean on changed files.

## Out of scope (follow-ups)

- Routing existing `web_search`/`scrape_url` through content_reach's resilient chains (bigger consolidation → discovery).
- Frontend doctor panel = Task 8.
