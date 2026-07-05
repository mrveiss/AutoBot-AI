# Content Reach — Tasks 2–6 (Source Backends) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Implement the five content sources on top of the merged `ContentSourceRegistry` foundation — web-search, web-page, YouTube, Reddit/HN, and browser-backed social — each as a primary→fallback `ContentSourceChain`, plus the shared `BrowserBackend` universal fallback and a `bootstrap` assembler.

**Architecture:** Each source module in `content_reach/sources/` defines one or more `ContentBackend` subclasses and a `build_<source>_chain() -> ContentSourceChain` factory. Optional heavy libs (`ddgs`, `trafilatura`, `yt-dlp`) are **lazy-imported behind an availability probe** (mirrors `research_browser_manager`'s `PLAYWRIGHT_AVAILABLE` pattern) so a missing lib degrades to httpx/browser fallbacks. Plain-HTTP backends (Jina, Reddit `.json`, HN Algolia) use the already-present `httpx`. `BrowserBackend` wraps `get_research_browser_manager().research_url()`.

**Tech Stack:** Python 3.10+, `httpx` (async, present), `ddgs`, `trafilatura`, `yt-dlp` (optional/lazy), existing `content_reach.*`, `research_browser_manager`, `source_attribution`.

**Scope:** ADDITIVE ONLY — like Task 1, this PR changes no runtime behavior. Backends + chains + a `build_default_registry()` assembler + tests. Boot-time registration and agent-tool exposure are the NEXT PR (umbrella Task 7).

## Global Constraints

- 4-line `mrveiss` copyright header verbatim on every new file (`# Copyright 2025-2026 mrveiss` / `# SPDX-License-Identifier: Apache-2.0` / `# AutoBot - AI-Powered Automation Platform` / `# Author: mrveiss`).
- **Async-first** — all `fetch`/`probe` are `async`. Sync libs (`yt-dlp`, `trafilatura` parsing, `ddgs`) run via `asyncio.to_thread`. HTTP via `httpx.AsyncClient`.
- Reuse canonical modules — import `content_reach.base`, `research_browser_manager`, `source_attribution`; never reimplement.
- Optional libs lazy-imported inside methods; `probe()` returns False when the lib is absent (never raise at import).
- Cache/TTL/timeout literals → module-level constants (per CLAUDE.md); HTTP timeouts as a named constant.
- Logging via `autobot_shared.logging_manager.get_logger` — no `print()`.
- No commit trailers (mrveiss sole author). Commit format `feat(content-reach): <desc> (#10932)`.
- TDD: failing test first. Tests MOCK the network/lib (no real network in unit tests); any real-network test is marked `@pytest.mark.integration` (skipped by default).
- Interpreter is `python3`. Run tests from repo root or backend dir; root `pytest.ini` sets `pythonpath`.
- Backends live in `content_reach/backends/`, sources in `content_reach/sources/`; both need `__init__.py`.

## Shared interfaces (given — from merged Task 1)

- `content_reach.base`: `ContentBackend` (attrs `name`, `source_type`; abstract async `probe()`, `fetch(request)`), `ContentRequest(query, url, source, limit, conversation_id, options)`, `ContentResult(success, source_type, backend_used, text, structured, url, reliability, metadata)` + `ContentResult.failure(source_type, detail)`, `BackendError`.
- `content_reach.chain.ContentSourceChain(source, source_type, backends)`.
- `source_attribution.SourceType` (incl. `YOUTUBE`/`REDDIT`/`WEB_PAGE`/`SOCIAL`/`WEB_SEARCH`), `SourceReliability`.
- `research_browser_manager.get_research_browser_manager()` → manager with `async research_url(conversation_id, url, extract_content=True) -> dict` (dict has `success`, `content.text_content`, `content.structured_data`, `title`); module-level `PLAYWRIGHT_AVAILABLE: bool`.

**Common probe semantics for this PR:** `probe()` checks *capability* (optional lib importable, or `PLAYWRIGHT_AVAILABLE` for browser). Pure-HTTP backends (Jina/Reddit/HN) return `True` from `probe()` (a cheap network HEAD every 30s isn't worth it; the circuit breaker + fetch-failure fall-through handle real outages). Document this on each `probe()`.

---

### Task S0: dependencies + shared `BrowserBackend`

**Files:**
- Modify: `autobot-backend/requirements.txt` (add the three optional libs)
- Create: `autobot-backend/content_reach/backends/__init__.py`
- Create: `autobot-backend/content_reach/backends/browser.py`
- Test: `autobot-backend/tests/content_reach/backends/test_browser.py`

**Interfaces produced:**
- `BrowserBackend(source_type: SourceType, name: str = "browser")` — `async probe()` returns `PLAYWRIGHT_AVAILABLE`; `async fetch(request)` requires `request.url`, calls `get_research_browser_manager().research_url(request.conversation_id, request.url)`, maps the dict to `ContentResult` (text=`content.text_content`, structured=`content.structured_data`, url=request.url, reliability=MEDIUM). Raises `BackendError` if `request.url` empty or `result["success"]` is false.
- `BrowserSearchBackend(BrowserBackend)` — for query→search: `fetch` builds `https://duckduckgo.com/html/?q=<urlencoded query>` as the URL then delegates to the browser navigation+extract. `name = "browser_search"`.

**Steps:**
- [ ] **Add deps** to `autobot-backend/requirements.txt` (append, with comments):
  ```
  ddgs>=9.0            # #10932 content-reach: keyless web search (optional, lazy)
  trafilatura>=2.0     # #10932 content-reach: readable article extraction (optional, lazy)
  yt-dlp>=2025.1.1     # #10932 content-reach: YouTube caption extraction (optional, lazy)
  ```
  (Verify the latest available version strings with `python3 -m pip show <pkg>`; pin `>=` to the installed version's major.)
- [ ] **Write failing test** `tests/content_reach/backends/test_browser.py` (also create `tests/content_reach/backends/__init__.py` if package-style discovery needs it — check sibling test dirs first):
  - `test_browser_probe_reflects_playwright_available` — monkeypatch `research_browser_manager.PLAYWRIGHT_AVAILABLE` True/False, assert `probe()` matches.
  - `test_browser_fetch_maps_research_result` — monkeypatch `get_research_browser_manager` to return a stub whose `research_url` returns `{"success": True, "content": {"text_content": "hello", "structured_data": {"headings": []}}, "title": "T"}`; assert `ContentResult.success`, `text=="hello"`, `backend_used=="browser"`, `url==request.url`.
  - `test_browser_fetch_raises_without_url` — `ContentRequest(query="x")` (no url) → `BackendError`.
  - `test_browser_fetch_raises_on_unsuccessful` — stub returns `{"success": False}` → `BackendError`.
  - `test_browser_search_builds_ddg_url` — `BrowserSearchBackend`, `ContentRequest(query="cats dogs")`; capture the url passed to `research_url`, assert it is `https://duckduckgo.com/html/?q=cats+dogs` (or `%20`-encoded — assert it contains the encoded query).
- [ ] Run: `python3 -m pytest autobot-backend/tests/content_reach/backends/test_browser.py -v` → FAIL (module missing).
- [ ] **Implement** `backends/__init__.py` (header + docstring) and `backends/browser.py`. Lazy-import `PLAYWRIGHT_AVAILABLE` and `get_research_browser_manager` inside methods (avoids importing playwright stack at module load). Use `urllib.parse.urlencode`/`quote_plus` for the search URL. `research_url` is async — `await` it directly.
- [ ] Run the test → PASS. Confirm pristine.
- [ ] Commit: `git commit -m "feat(content-reach): add optional source deps + shared BrowserBackend (#10932)"`

---

### Task S1: web-search source (`ddgs ▸ s.jina.ai ▸ browser`)

**Files:** Create `content_reach/sources/__init__.py`, `content_reach/sources/web_search.py`; Test `tests/content_reach/sources/test_web_search.py`.

**Interfaces produced:**
- `DdgsBackend` (name `ddgs`, source_type `WEB_SEARCH`): `probe()` → True iff `import ddgs` succeeds; `fetch(request)` → `await asyncio.to_thread(lambda: DDGS().text(request.query, max_results=request.limit))` → list of `{title, href, body}`; build `text` as a newline list of `title — href` + snippets, `structured={"results": [...]}`. Empty results → raise `BackendError` (so the chain falls through).
- `JinaSearchBackend` (name `jina_search`): `fetch` GETs `https://s.jina.ai/<urlencoded query>` with header `Accept: application/json` (fallback `text/plain`) via `httpx.AsyncClient(timeout=_HTTP_TIMEOUT)`; parse results. Non-200 or empty → `BackendError`.
- `build_web_search_chain() -> ContentSourceChain(source="web_search", source_type=WEB_SEARCH, backends=[DdgsBackend(), JinaSearchBackend(), BrowserSearchBackend(WEB_SEARCH)])`.

**Steps:**
- [ ] **Failing tests** (`tests/content_reach/sources/test_web_search.py`, create `sources/__init__.py` test-dir if needed):
  - `test_ddgs_probe_true_when_importable` (ddgs is installed in this env) and a `test_ddgs_probe_false_when_absent` that monkeypatches the import to raise (e.g. patch `builtins.__import__` or the module's lazy import helper) → False.
  - `test_ddgs_fetch_maps_results` — monkeypatch the `DDGS` used by the backend so `.text()` returns two fake dicts; assert `ContentResult.success`, `structured["results"]` length 2, `backend_used=="ddgs"`.
  - `test_ddgs_fetch_empty_raises` — `.text()` returns `[]` → `BackendError`.
  - `test_jina_search_fetch` — mock `httpx.AsyncClient.get` (via monkeypatch or an injected client) to return a 200 with a small JSON/text body; assert mapped result.
  - `test_build_web_search_chain_order` — assert `build_web_search_chain().backend_names() == ["ddgs", "jina_search", "browser_search"]` and `source_type is SourceType.WEB_SEARCH`.
- [ ] Run → FAIL. Implement. Run → PASS.
- [ ] Commit: `feat(content-reach): web-search source (ddgs ▸ jina ▸ browser) (#10932)`

*Implementer note:* prefer structuring each HTTP backend to accept an optional `client: httpx.AsyncClient | None` param (default None → create one per fetch) so tests can inject a mock client instead of monkeypatching globally. Keep `DDGS` referenced as a module-level name you can monkeypatch.

---

### Task S2: web-page source (`httpx+trafilatura ▸ r.jina.ai ▸ browser`)

**Files:** Create `content_reach/sources/web_page.py`; Test `tests/content_reach/sources/test_web_page.py`.

**Interfaces produced:**
- `TrafilaturaBackend` (name `trafilatura`, source_type `WEB_PAGE`): `probe()` → True iff `import trafilatura`; `fetch(request)` requires `request.url`; GET the URL via `httpx.AsyncClient`, then `text = await asyncio.to_thread(trafilatura.extract, html)`. `None`/empty extraction → `BackendError`.
- `JinaReaderBackend` (name `jina_reader`): GET `https://r.jina.ai/<request.url>` (header `Accept: text/plain`) → readable text; non-200/empty → `BackendError`.
- `build_web_page_chain() -> ContentSourceChain(source="web_page", source_type=WEB_PAGE, backends=[TrafilaturaBackend(), JinaReaderBackend(), BrowserBackend(WEB_PAGE)])`.

**Steps:** analogous to S1 (mock httpx + monkeypatch `trafilatura.extract`). Tests: trafilatura maps extracted text; empty extraction raises; jina reader maps text; chain order `["trafilatura", "jina_reader", "browser"]`. TDD RED→GREEN. Commit `feat(content-reach): web-page source (trafilatura ▸ jina ▸ browser) (#10932)`.

---

### Task S3: YouTube captions source (`yt-dlp`)

**Files:** Create `content_reach/sources/youtube.py`; Test `tests/content_reach/sources/test_youtube.py`.

**Interfaces produced:**
- `YtDlpCaptionBackend` (name `yt_dlp`, source_type `YOUTUBE`): `probe()` → True iff `import yt_dlp`; `fetch(request)` requires a YouTube `request.url`; run in `asyncio.to_thread`: `yt_dlp.YoutubeDL({"skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["en"], "quiet": True, "no_warnings": True}).extract_info(url, download=False)`; pull the English subtitle/automatic-caption track URL from `info["subtitles"]`/`info["automatic_captions"]`, fetch that track via `httpx`, and return its text (strip to plain text). No captions → `BackendError`. `structured={"title": info.get("title"), "duration": info.get("duration")}`.
- `build_youtube_chain() -> ContentSourceChain(source="youtube", source_type=YOUTUBE, backends=[YtDlpCaptionBackend()])`.

**Steps:** TDD with `extract_info` monkeypatched to return a fake `info` dict (with a fake caption URL) and httpx mocked to return caption text; assert mapped result + `backend_used=="yt_dlp"`. Test `no captions → BackendError`. Test `probe False when yt_dlp absent`. Chain order `["yt_dlp"]`. Commit `feat(content-reach): youtube captions source via yt-dlp (#10932)`.

*Implementer note:* verify the exact shape of `info["automatic_captions"]["en"]` (a list of `{ext,url,...}`) against the installed yt-dlp with a quick `python3 -c`; pick the `ext in ("json3","srv1","vtt")` entry and convert to plain text. Keep the yt-dlp options dict as a module-level constant.

---

### Task S4: Reddit/HN source (`old.reddit .json ▸ HN Algolia ▸ browser`)

**Files:** Create `content_reach/sources/reddit.py`; Test `tests/content_reach/sources/test_reddit.py`.

**Interfaces produced:**
- `RedditJsonBackend` (name `reddit_json`, source_type `REDDIT`): `fetch(request)` — if `request.url` is a reddit URL, GET `<url>.json`; else GET `https://www.reddit.com/search.json?q=<query>&limit=<limit>`. MUST send a descriptive `User-Agent` header (module constant, e.g. `"autobot-content-reach/1.0"`) — reddit 403s default clients. Parse `data.children[].data` → title/selftext/permalink. Non-200/empty → `BackendError`.
- `HnAlgoliaBackend` (name `hn_algolia`): GET `http://hn.algolia.com/api/v1/search?query=<query>` → `hits[]` (title, url, points, objectID → `https://news.ycombinator.com/item?id=`). Non-200/empty → `BackendError`.
- `build_reddit_chain() -> ContentSourceChain(source="reddit", source_type=REDDIT, backends=[RedditJsonBackend(), HnAlgoliaBackend(), BrowserBackend(REDDIT)])`.

**Steps:** TDD with mocked httpx returning sample reddit/HN JSON; assert mapping + UA header present (assert the request carried the UA). Empty → raise. Chain order `["reddit_json", "hn_algolia", "browser"]`. Commit `feat(content-reach): reddit/HN source via public JSON (#10932)`.

---

### Task S5: browser-backed social source

**Files:** Create `content_reach/sources/social.py`; Test `tests/content_reach/sources/test_social.py`.

**Interfaces produced:**
- `build_social_chain() -> ContentSourceChain(source="social", source_type=SOCIAL, backends=[BrowserBackend(SOCIAL)])` — reuses the shared `BrowserBackend` with `source_type=SOCIAL` (Twitter/IG/etc. via rendered page; local-first, no cookies). No new backend class unless a thin `SocialBrowserBackend` is needed to set `source_type`; prefer passing `SOCIAL` to `BrowserBackend`.

**Steps:** TDD: `test_build_social_chain` asserts `backend_names()==["browser"]`, `source_type is SourceType.SOCIAL`; a `fetch` test reusing the browser stub asserting the result carries `source_type=SOCIAL`. Commit `feat(content-reach): browser-backed social source (#10932)`.

---

### Task S6: `bootstrap` registry assembler

**Files:** Create `content_reach/bootstrap.py`; Test `tests/content_reach/test_bootstrap.py`.

**Interfaces produced:**
- `build_default_registry() -> ContentSourceRegistry` — constructs a fresh `ContentSourceRegistry`, registers all five chains (`build_web_search_chain`, `build_web_page_chain`, `build_youtube_chain`, `build_reddit_chain`, `build_social_chain`), returns it.
- `register_default_sources(registry: ContentSourceRegistry) -> None` — registers the five chains into a given registry (used by boot wiring in the next PR).

**Steps:**
- [ ] **Failing test** `tests/content_reach/test_bootstrap.py`:
  - `test_build_default_registry_has_all_sources` — `set(build_default_registry().list_sources()) == {"web_search","web_page","youtube","reddit","social"}`.
  - `test_each_chain_source_type` — assert each registered chain's `source_type` matches (`web_search`→WEB_SEARCH, `youtube`→YOUTUBE, `reddit`→REDDIT, `web_page`→WEB_PAGE, `social`→SOCIAL).
  - `test_register_default_sources_into_existing` — pass a fresh `ContentSourceRegistry`, call `register_default_sources`, assert 5 sources present.
- [ ] Run → FAIL. Implement `bootstrap.py`. Run → PASS.
- [ ] **Full-suite gate:** `python3 -m pytest autobot-backend/tests/content_reach/ -v` (all foundation + new source tests green) and import smoke `cd autobot-backend && python3 -c "import content_reach.bootstrap; print('ok')"`.
- [ ] Commit: `feat(content-reach): bootstrap assembler for default source registry (#10932)`

---

## Self-Review

**Spec coverage:** S0 BrowserBackend + deps → spec §4.4/§7; S1–S5 → the five `sources/` in spec §3; S6 assembler enables spec §4.5 health probe to report real sources and Task 7 boot wiring. Agent tools + boot registration = deferred to Task 7 (noted, not a gap). ✓
**Async-first:** every sync lib (`ddgs`, `trafilatura`, `yt-dlp`) wrapped in `asyncio.to_thread`; HTTP via `httpx.AsyncClient`. ✓
**Lazy-import/optional:** all three heavy libs lazy + probe-guarded; Reddit/HN/Jina need only httpx. ✓
**Type consistency:** every `build_*_chain()` returns `ContentSourceChain(source, source_type, backends)`; every backend has `name`/`source_type` + async `probe`/`fetch` returning `ContentResult`/raising `BackendError`. ✓
**Test hygiene:** unit tests mock network/lib (no real calls); real-network tests `@pytest.mark.integration`. ✓
