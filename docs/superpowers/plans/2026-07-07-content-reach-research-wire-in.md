# Wire content_reach into the /knowledge/research flow (registry-canonical)

**Goal:** Make the Observable Research Panel (`/knowledge/research` → `LibrarianAssistant`) search via the `agent_loop/search` registry, with `content_reach`'s web_search chain registered as a keyless provider — so research search becomes Brave → SearXNG → content_reach (resilient, degrades gracefully) instead of the current direct-Playwright-only search. Extract stays on Playwright (out of scope this round).

**Constraints:** async-first; no print(); logging via existing logger; behavior-preserving for the result SHAPE consumed downstream (`extract_content` reads `url` from each search dict); no commit trailers (mrveiss); commit `feat(content-reach): wire content_reach web_search into research via search registry (#10932)`; black 26.3.1 + isort + ruff; TDD; python3. Must not break startup-import-smoke (lazy imports) or existing LibrarianAssistant tests.

## Given (verified interfaces)
- `agent_loop/search/base.py`: `WebSearchProvider(ABC)` — `provider_name: str`, `__init__(settings=None)`, abstract `async search(query, *, category=None, count=DEFAULT_RESULT_COUNT) -> List[SearchResult]` (RAISE on unreachable/error so registry falls back; `[]` = reachable-no-results), abstract `async is_available() -> bool`. `SearchResult(title, url, snippet="", freshness=None, source=None, extra={})` + `.to_dict()` → `{title,url,snippet[,freshness,source]}`.
- `agent_loop/search/registry.py`: `_populate_default_providers(registry)` registers SearXNG (if url) + Brave (if key), credential-gated. `get_search_registry()` lazy singleton. `registry.search(query, *, provider=None, category=None, count=10)` tries preferred then fallback chain.
- `content_reach.registry.get_content_source_registry()` → async `fetch(source, ContentRequest) -> ContentResult`. `content_reach.base.ContentRequest(query, url, source, limit, ...)`, `ContentResult(success, text, structured, url, backend_used, ...)`.
- `content_reach.bootstrap.register_default_sources(registry)` (sync) registers the 5 chains incl. `web_search`.
- **content_reach `web_search` result shape** — READ `content_reach/sources/web_search.py` to confirm: `DdgsBackend` sets `structured={"results": [{"title","href","body"}...]}`; `JinaSearchBackend`/`BrowserSearchBackend` may return `text` with sparse `structured`. Handle both.
- `agents/librarian_assistant.py`: `search_web(query, search_engine="duckduckgo", progress_callback=None) -> List[Dict]` (each dict has `url`/`title`/`snippet`); currently gates on `_check_playwright_service()` then `_execute_search_request()` POSTs Playwright `/search` and emits `research:result_found` per result. `_emit(cb, {...})` sends events.

## Part 1 — `ContentReachSearchProvider`
Create `autobot-backend/agent_loop/search/content_reach_provider.py`:
- `class ContentReachSearchProvider(WebSearchProvider)`, `provider_name = "content_reach"`.
- `async def search(self, query, *, category=None, count=DEFAULT_RESULT_COUNT) -> List[SearchResult]`:
  - Lazy import `get_content_source_registry`, `ContentRequest`, and `register_default_sources` (from content_reach).
  - Ensure the web_search chain is registered: `reg = get_content_source_registry(); if reg.get_chain("web_search") is None: register_default_sources(reg)` (defensive — works regardless of boot order / in tests).
  - `result = await reg.fetch("web_search", ContentRequest(query=query, source="web_search", limit=count))`.
  - If `not result.success`: return `[]` (content_reach is the last-resort provider; graceful empty rather than raising — but if the fetch itself raises unexpectedly, let it propagate so the registry treats it as provider error).
  - Map to `List[SearchResult]`: prefer `result.structured.get("results")` (list of dicts) → `SearchResult(title=r.get("title",""), url=r.get("href") or r.get("url",""), snippet=(r.get("body") or r.get("snippet") or "")[:300], source="content_reach")`, skipping entries with no url; if no structured results but `result.text`/`result.url`, emit a single `SearchResult(title=..., url=result.url, snippet=result.text[:300], source="content_reach")` when a url exists. Cap at `count`.
- `async def is_available(self) -> bool`: return True (web_search chain is keyless and self-degrading; optionally `get_content_source_registry().get_chain("web_search") is not None or True`).

## Part 2 — register it in the search registry
In `agent_loop/search/registry.py` `_populate_default_providers`, AFTER the Brave/SearXNG blocks, unconditionally register content_reach as the final fallback:
```python
from agent_loop.search.content_reach_provider import ContentReachSearchProvider
registry.register(ContentReachSearchProvider())
logger.debug("Registered content_reach as fallback web-search provider")
```
(Lazy import inside the function — matches the existing pattern; keyless so always registers.)

## Part 3 — repoint LibrarianAssistant search
In `agents/librarian_assistant.py`, change `search_web` to use the registry instead of the Playwright POST:
- Keep the `if not self.enabled: return []` guard and the `research:searching` emit.
- Replace the `_check_playwright_service()` gate + `_execute_search_request()` call with:
  ```python
  from agent_loop.search.registry import get_search_registry
  results = await get_search_registry().search(query, count=self.max_search_results)
  dicts = [r.to_dict() for r in results][: self.max_search_results]
  for item in dicts:
      await self._emit(progress_callback, {"event": "research:result_found", "url": item.get("url",""), "title": item.get("title",""), "snippet": (item.get("snippet") or "")[:300]})
  return dicts
  ```
  On exception → log + return `[]` (as today).
- Keep `search_engine` param in the signature (now advisory/unused — optionally pass as `category`); do NOT break callers.
- Leave `_execute_search_request`/`_check_playwright_service` in place if still used by extract; if `_execute_search_request` becomes dead, remove it (and its Playwright-search test) rather than leave dead code. `extract_content` (Playwright `/extract`) is UNCHANGED.

## Tests (TDD)
- `tests/agent_loop/search/test_content_reach_provider.py`: search maps structured `results` → SearchResult list (mock `get_content_source_registry().fetch` AsyncMock → a successful ContentResult with `structured={"results":[...]}`); text-only result → single SearchResult; unsuccessful result → `[]`; `is_available()` True; ensures-registered path (chain missing → register_default_sources called).
- `tests/agent_loop/search/test_registry.py` (or wherever registry tests live): assert `content_reach` provider is registered by `_populate_default_providers` even with no Brave/SearXNG creds.
- `tests/.../test_librarian_assistant*.py`: `search_web` now calls `get_search_registry().search` (monkeypatch it → SearchResults), emits `research:result_found` per result, returns the `{url,title,snippet}` dicts; does NOT call Playwright `/search`. Update/replace any existing test that asserted the Playwright-search POST. Confirm `extract_content` path untouched.

## Gate
- `cd autobot-backend && python3 -m pytest tests/agent_loop/search/ tests/content_reach/ -q` + the librarian/research tests → all green.
- `python3 -c "import agent_loop.search.registry, agent_loop.search.content_reach_provider, agents.librarian_assistant; print('ok')"` (from backend dir) import-clean.
- ruff + black(26.3.1) + isort clean on changed files.

## Out of scope
Extract via content_reach web_page (deferred); the frontend panel is unchanged (same events/shape).
