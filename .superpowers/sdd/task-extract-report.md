# Task Report: research extract via content_reach (#10932)

## Status
COMPLETE — all parts implemented, tests green, linting clean, committed.

## Commit
`ec72a2760` — `feat(content-reach): research extract via content_reach + URL-aware youtube/reddit routing (#10932)`

## What changed
- `autobot-backend/agents/librarian_assistant.py`
  - Added module-level `_source_for_url(url) -> str` — routes youtube.com/youtu.be → "youtube", reddit.com → "reddit", else → "web_page"; robust to missing scheme.
  - Added `_content_data_from_result(result, url) -> dict` — maps ContentResult to the 8-key content_data shape (url/title/description/content/domain/is_trusted/timestamp/content_length); title falls back to netloc, description to content[:200], is_trusted via `self.trusted_domains` suffix check.
  - Rewrote `extract_content(url)` — fetches via `get_content_source_registry().fetch(source, ContentRequest(...))` with lazy bootstrap guard; returns None on failure, empty text, or exception.
  - Removed `_check_playwright_service`, `playwright_service_url`, `_build_content_data`, the Playwright gate in `research_query`, `http_client` attribute, and imports of `get_http_client`/`get_service_url`.
- `autobot-backend/tests/agents/test_librarian_assistant_extract.py` (new) — 19 tests covering all plan cases.
- `autobot-backend/tests/agents/test_librarian_assistant_search.py` (updated) — removed stale Playwright `/extract` test and dead stubs.

## Test summary
```
25 passed in 0.36s   (19 new extract tests + 6 search tests)
```
Full gate (`tests/agents/ tests/content_reach/ tests/search/` minus pre-existing broken `test_subagent_spawning.py`): 215 passed, 7 pre-existing failures (test_causal_reasoning × 5, test_ledger_vs_executor × 2) — same count as base branch, zero regressions introduced.

## Import smoke
`python3 -c "import agents.librarian_assistant"` → OK (Redis/Ollama warnings are expected in dev; no import errors).

## Linting
- `ruff check` → All checks passed
- `black --check --fast` → 3 files would be left unchanged
- `isort --check-only` → clean (no output)

## Playwright members removed (confirmed zero dangling refs)
Grep on `agents/librarian_assistant.py` after change returns empty:
- `playwright_service_url` — removed from `__init__`
- `_check_playwright_service` — method deleted
- `_build_content_data` — method replaced by `_content_data_from_result`
- `http_client` — attribute removed; `get_http_client`/`get_service_url` imports removed
- Playwright gate in `research_query` (lines ~513-516) — deleted

## Concerns / notes
- `is_trusted` now uses `self.trusted_domains` suffix check (same domains the class already held in `__init__`). This avoids importing `DomainSecurityManager` which has heavy deps (aiohttp, yaml, threat intel network calls) making it unsuitable for sync/lazy use. The effect is identical for the domains listed; the plan's "else False" fallback is effectively the non-matching path.
- Pre-existing `test_subagent_spawning` collection error (`ModuleNotFoundError: services.agents`) and 7 `test_causal_reasoning`/`test_ledger_vs_executor` failures are confirmed pre-existing on base branch; not introduced by this PR.

---

## Code-review fixes: commit `768d69647`

`fix(content-reach): guard on routed source + subdomain-safe is_trusted + degraded-extract summary (#10932)`

### Fix 1 — Bootstrap guard checks routed source (not hardcoded "web_page")
- `extract_content`: `source = _source_for_url(url)` moved BEFORE the guard; guard now checks `reg.get_chain(source)` so a registry missing only "youtube" will still bootstrap when a YouTube URL is requested.

### Fix 2 — Subdomain-safe `is_trusted` (no more partial-suffix exploitation)
- New module-level helper `_host_matches(host, domain) → bool`: `host == domain or host.endswith("." + domain)`.
- `_content_data_from_result`: `netloc` lowercased at parse time; `is_trusted` rewritten as `any(_host_matches(netloc, td) for td in self.trusted_domains)`. `evilgithub.com` → False; `github.com` and `sub.github.com` → True.

### Fix 3 — Degraded summary on total extraction failure
- `_finalize_research_results`: added `elif research_results.get("search_results"):` branch that sets `summary = "Found N result(s) but could not extract content."` when search produced hits but extraction yielded nothing.

### Fix 4 — Readability cleanups
- `result.structured if result.structured else {}` → `result.structured or {}`.
- Dropped `domain = netloc` alias; `netloc` used directly (lowercased).
- `text = result.text or ""` bound once in `extract_content`; reused for `.strip()` guard and `len()` log.

### Fix 5 — Domain-boundary routing in `_source_for_url`
- Old naive `"youtube.com" in host` substring test misrouted `notyoutube.com` → "youtube".
- Replaced with `_host_matches` calls: `_host_matches(host, "youtube.com") or _host_matches(host, "youtu.be")` → "youtube"; `_host_matches(host, "reddit.com")` → "reddit".
- `_host_matches` reused by both `_source_for_url` and `is_trusted` (DRY).

### Tests added (13 new, total 32 in file)
- Fix 5 routing: `www.youtube.com`, `m.youtube.com`, `old.youtube.com`, `youtu.be` → "youtube"; `www.reddit.com`, `old.reddit.com` → "reddit"; `notyoutube.com`, `fakeyoutube.com`, `notyoutu.be`, `myreddit.com`, `example.com` → "web_page".
- Fix 1 bootstrap-on-source: registry with only "youtube" missing → `register_default_sources` called on YouTube URL.
- Fix 2 is_trusted: exact match, subdomain match, partial-suffix attack (evilgithub.com → False).
- Fix 3 degraded summary: search_results non-empty + extracted_content empty → non-empty summary string.

### Gate result
```
157 passed in 2.68s  (tests/agents/test_librarian_assistant_extract.py + test_librarian_assistant_search.py + tests/content_reach/)
```
Pre-existing failures: test_ledger_vs_executor × 2 — unchanged from base.

### Linting
- `ruff check` → All checks passed
- `black --check --fast` → 2 files unchanged
- `isort --check-only` → clean
