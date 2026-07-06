# Content Reach Sources (#10932, Tasks 2-6) — SDD Progress
Plan: docs/superpowers/plans/2026-07-05-content-reach-sources.md
BASE (pre-S0): e767cbfc58b07f316cfc18281ee610eeefb7fac7
Branch: issue-10932-sources → PR to Dev_new_gui (NOT local merge — auto-sync pushes main tree)
REMINDER: run `black --check` on all files (ruff != Black) before PR.

## Tasks
- S0 deps + BrowserBackend: complete (96fc088, review clean, 3 minor/polish)
- S1 web_search: complete (abab3d7, review approved, 4 minor → consolidated cleanup)
- S1 web_search: pending
- S2 web_page: pending
- S3 youtube: pending
- S4 reddit/HN: pending
- S5 social: pending
- S6 bootstrap: pending
- [Minor][S0] browser.py:64 `pragma: no cover` on _get_manager hides lazy-import from coverage; consider a smoke test in Task 7 wiring.
- [Minor][S0] test_browser.py match="url" is broad; tighten in a cleanup pass.
- [Minor][S1→cleanup] web_search.py: logger declared but unused — add logger.warning on ddgs-absent + logger.debug on empty results.
- [Minor][S1→cleanup] web_search.py:95 fetch() leaks ImportError if ddgs absent & DDGS unpatched — guard lazy import → BackendError.
- [Minor][S1→cleanup] Jina: Accept:application/json but consumes response.text; add header assertion in test.
- S2 web_page: complete (f12ec1a, hardening applied)
- S2 web_page: complete (f12ec1a, approved)
- [Cleanup][S1/S2/S4] wrap httpx client.get() in try/except httpx.HTTPError -> BackendError across all HTTP backends (registry falls through anyway, but BackendError is the contract type).
- [Cleanup][S1/S2/S3] use pytest.importorskip for "probe true when importable" tests (optional libs may be absent in CI image).
- S3 youtube: complete (f7afe54)
- S3 youtube: complete (f7afe54 + e9ea713 srv1 fix, re-review clean)
- [Minor][S3→cleanup] _vtt_to_text docstring still mentions SRV1 (stale, cosmetic).
- S4 reddit/HN: complete (069898e + 19d668b async/https/enum fix, re-review clean)
- [Minor][S1/S2/S4→cleanup] injected-client vs async-with branching repeats across httpx backends — extract a small `_http_get` helper (DRY).
- S5 social: complete (50cb48a, approved no issues)
- S6 bootstrap: complete (a188e34, approved no issues). ALL S0-S6 DONE.
- S1-S3 cleanup pass: complete. Changes: logger.warning in DdgsBackend.probe() + logger.debug before empty-results BackendError; ImportError guard in DdgsBackend.fetch() → BackendError; httpx.HTTPError wrapping in JinaSearchBackend.fetch(), TrafilaturaBackend.fetch(), JinaReaderBackend.fetch(); _vtt_to_text docstring cleaned (removed stale SRV1 reference); pytest.importorskip added to ddgs and trafilatura "probe true" tests; Accept header assertion added to JinaSearchBackend test; httpx.HTTPError → BackendError tests added for all three backends. Suite: 84 passed (was 80). ruff + black clean.
