# Wire content_reach into research EXTRACTION + URL-aware source routing (#10932)

**Goal:** (a) route the research flow's content extraction through `content_reach` (`web_page`: trafilatura→Jina→browser), and (b) URL-aware routing so YouTube/Reddit result URLs use content_reach's `youtube`/`reddit` sources. Together this makes `LibrarianAssistant` fully content_reach-backed (search already is, from PR #11154) and removes its dependency on the external Playwright `/extract` service.

**Constraints:** async-first; preserve the `content_data` dict shape consumed by `assess_content_quality`/`store_in_knowledge_base`; lazy-import content_reach; no print(); no commit trailers (mrveiss); commit `feat(content-reach): ... (#10932)`; black 26.3.1/isort/ruff; TDD; no dead code; don't break startup-import-smoke.

## Given (verified)
- `agents/librarian_assistant.py`:
  - `extract_content(url) -> dict|None` (line 162): gates on `_check_playwright_service()`, POSTs Playwright `/extract`, maps via `_build_content_data(result)`.
  - `_build_content_data` (142) → `content_data = {url, title, description, content, domain, is_trusted, timestamp, content_length}`.
  - Consumers use: `content` (main text), `title`, `url`, `domain`, `is_trusted`, `timestamp`, `content_length`, `description`.
  - `_extract_and_process_results` calls `extract_content(result["url"])` (line 372).
  - `research_query` (476) has a Playwright gate at line 513 before `_extract_and_process_results` (added in #11154).
  - Playwright bits: `playwright_service_url` (41), `_check_playwright_service` (79) — after this change, used NOWHERE (search moved off in #11154; extract moves off here).
- `content_reach.registry.get_content_source_registry()` → async `fetch(source, ContentRequest) -> ContentResult(success, text, structured, url, backend_used, reliability, metadata)`. Sources: `web_page`, `youtube`, `reddit` (+ web_search/social). `content_reach.bootstrap.register_default_sources`.
- `content_reach` `web_page`/`youtube`/`reddit` use httpx + in-process `research_browser_manager` — NONE need the external Playwright `/extract` service.
- `security/domain_security.py` has a trusted-domain whitelist (reuse for `is_trusted` if cleanly importable; else default False).

## Part 1 — URL→source router
Add `_source_for_url(url: str) -> str` (module-level or method):
- host contains `youtube.com` or `youtu.be` → `"youtube"`
- host contains `reddit.com` (incl. `old.reddit.com`, `www.reddit.com`) → `"reddit"`
- else → `"web_page"`
Use `urllib.parse.urlparse(url).netloc.lower()`. Be robust to missing scheme.

## Part 2 — map ContentResult → content_data
Add `_content_data_from_result(result: ContentResult, url: str) -> dict`:
- `content` = `result.text or ""`
- `url` = `result.url or url`
- `title` = `result.structured.get("title")` if present else the netloc (fallback)
- `description` = `result.structured.get("description")` if present else `content[:200]`
- `domain` = `urlparse(result.url or url).netloc`
- `is_trusted` = trusted-domain check on `domain` (reuse `security/domain_security` helper if importable; else `False`)
- `timestamp` = `datetime.now(tz=timezone.utc).isoformat()`
- `content_length` = `len(content)`
Return exactly those 8 keys (same shape as `_build_content_data`).

## Part 3 — repoint `extract_content`
Rewrite `extract_content(url)`:
```python
async def extract_content(self, url: str) -> Dict[str, Any] | None:
    from content_reach.base import ContentRequest
    from content_reach.registry import get_content_source_registry
    reg = get_content_source_registry()
    # defensive: ensure sources registered regardless of boot order
    if reg.get_chain("web_page") is None:
        from content_reach.bootstrap import register_default_sources
        register_default_sources(reg)
    source = _source_for_url(url)
    try:
        result = await reg.fetch(source, ContentRequest(url=url, query=url, source=source))
    except Exception as e:
        logger.error("content_reach extract failed for %s (%s): %s", url, source, e)
        return None
    if not result.success or not (result.text or "").strip():
        logger.info("No content extracted for %s via %s", url, source)
        return None
    return self._content_data_from_result(result, url)
```
- Remove the `_check_playwright_service()` gate + the Playwright `/extract` POST. Keep `extract_content`'s `-> dict|None` contract (callers unchanged).
- Note: `youtube` source needs a YouTube `url`; `reddit` accepts a reddit url or falls back to query — passing both `url` and `query=url` is harmless.

## Part 4 — remove now-dead Playwright code
- Remove the Playwright gate in `research_query` (line ~513) — extraction now always proceeds via content_reach; keep the rest of the pipeline (extract→assess→store) intact. Preserve any "no results" graceful summary that isn't Playwright-specific.
- Remove `_check_playwright_service` and `playwright_service_url` (and `_build_content_data` if now unused) — VERIFY no remaining references first (grep). No dead code.
- If `self.http_client`/Playwright `/health` becomes unused, remove it too (verify).

## Tests (TDD) — `tests/agents/test_librarian_assistant_extract.py` (+ update existing)
- `_source_for_url`: youtube.com / youtu.be → "youtube"; reddit.com / old.reddit.com → "reddit"; example.com → "web_page"; no-scheme urls handled.
- `extract_content`: monkeypatch `get_content_source_registry().fetch` (AsyncMock) →
  - a YouTube url routes to source `"youtube"` and maps text→`content`, structured title→`title`; assert the fetch was called with source `"youtube"`.
  - a reddit url routes to `"reddit"`.
  - a generic url routes to `"web_page"`; maps domain/content_length/timestamp correctly.
  - `result.success=False` or empty text → `None`.
  - fetch raises → `None`.
- `content_data` shape has exactly the 8 keys the downstream expects.
- Update/replace any existing extract test that asserted the Playwright `/extract` POST (now removed).
- Assert `research_query` no longer calls `_check_playwright_service` (removed).

## Gate
- `cd autobot-backend && python3 -m pytest tests/agents/ tests/content_reach/ tests/search/ -q` → green.
- import smoke: `python3 -c "import agents.librarian_assistant"` (from backend dir).
- ruff + black(26.3.1) + isort clean on changed files.

## Out of scope
Frontend panel unchanged (same events/shape). web_search path already wired (#11154).
