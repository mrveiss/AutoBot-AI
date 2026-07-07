# Task Report: Wire content_reach into research via search registry (#10932)

## Status
COMPLETE — all gates green.

## Changes

### Part 1 — `agent_loop/search/content_reach_provider.py` (new file)
`ContentReachSearchProvider(WebSearchProvider)`:
- `provider_name = "content_reach"`
- `is_available()` → True (keyless, always registers)
- `search()`: lazy-imports `get_content_source_registry`, `ContentRequest`; defensively calls `_ensure_registered`; maps `structured["results"]` `{title,href,body}` → `SearchResult(title,url=href,snippet=body[:300],source="content_reach")`; skips entries with no URL; caps at `count`; text-only fallback (url present) → single SearchResult; unsuccessful → `[]`

### Part 2 — `agent_loop/search/registry.py`
Added unconditional registration of `ContentReachSearchProvider()` at the end of `_populate_default_providers`, after the Brave block (lazy import, matches existing pattern).

### Part 3 — `agents/librarian_assistant.py`
- Removed `_execute_search_request` (dead code after repoint)
- `search_web` now calls `await get_search_registry().search(query, count=...)`, emits `research:result_found` per result, returns `[r.to_dict() for r in results]`
- `research_query`: moved `_check_playwright_service` gate from before `search_web` to before `_extract_and_process_results` (search no longer needs Playwright; extract still does)

## Tests

### New test files
- `tests/search/test_content_reach_provider.py` — 10 tests: structured map, skip-no-url, cap-at-count, text-only, text-no-url empty, unsuccessful empty, is_available, ensure_registered called/skipped, snippet truncation
- `tests/agents/test_librarian_assistant_search.py` — 7 tests: registry used not Playwright, result_found emitted per result, searching emitted, disabled returns [], exception returns [], returns dicts, extract_content uses /extract
- `tests/search/test_registry.py` — 1 new test: content_reach registered without creds

### Modified test infrastructure
- `tests/search/conftest.py`: added `content_reach_provider` to `_load_real` chain; added submodule-as-attribute attachment so `patch()` can resolve via `getattr`

## Test counts
- `tests/search/`: 30 passed
- `tests/content_reach/`: 119 passed
- `tests/agents/test_librarian_assistant_search.py`: 7 passed
- Combined (`tests/search/ tests/content_reach/ tests/agents/test_librarian_assistant_search.py`): **156 passed**

## Import smoke
`python3 -c "import agent_loop.search.registry, agent_loop.search.content_reach_provider, agents.librarian_assistant; print('ok')"` → `ok`

## Lint
- ruff: all checks passed
- black (26.3.1) --check: 7 files unchanged
- isort --check-only: clean (no output)

## Dead code
`_execute_search_request` removed (was dead after Part 3). Its previous test coverage was via `search_web` (no dedicated test existed).

## Concerns
None. Pre-existing cross-contamination between `tests/agents/` and `tests/search/` when run together without worktree isolation was diagnosed and fixed by using `patch.object(sys.modules[...])` and `setdefault` stubs that don't clobber real modules.
