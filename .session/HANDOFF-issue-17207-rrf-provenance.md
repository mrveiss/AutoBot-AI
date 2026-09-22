# Handoff: issue-17207-rrf-provenance
status: complete
pr: #17216
base_at_push: 2323edc58f069cae7772c7a5b8ee97d5bd0dbb3a
gates: lint=PASS (ruff, flake8, black) · size=PASS (254/238 vs MAX_LINES 600) · ratchet=PASS (search.py untouched at 1102) · trailers=PASS (0) · tests=CI-only, never run locally per owner rule
needs_rebase_before_merge: no
owner: autobot-ai-78 (transferred from autobot-ai-e9 at user request; recorded in ledger)
remaining: (none for #17207 — tree children #17208-#17214 are separate issues)
worktree: .worktrees/issue-17207-rrf-provenance (safe to remove after #17216 merges)

## done
RRF fusion now preserves per-view provenance. `process_rrf_results` accumulated every
retrieval leg into one float, so an item found by one view at rank 0 and an item found by
three views at rank 5 were indistinguishable — the strongest label-free relevance signal
was destroyed at the only place it could be captured.

Three losses fixed in `autobot-backend/knowledge/search_components/hybrid_search.py`:
- one scalar per item -> per-view `{rank, contribution}`, surfaced as `view_contributions`
  and `view_count`
- `prefix` carried the view identity but was only an id fallback -> now the provenance key
- later views' result objects were discarded outright -> merged via `setdefault`, first
  view still wins on conflict so existing keys are untouched

Also splits "found nothing" from "did not look": `asyncio.gather` now uses
`return_exceptions=True`, so one failing leg no longer silently degrades to a semantic-only
re-run. New `search_with_provenance()` returns `(results, status)`; `search()` delegates and
returns the list, contract unchanged. Total failure still propagates as before.

New `hybrid_search_test.py` (238 lines) — first test for this component, 13 tests.
Ranking behaviour deliberately unchanged, pinned by a regression test asserting against the
RRF definition `1/(k+rank+1)` rather than against the implementation.

## notes
- **`knowledge/search.py` deliberately untouched.** It sits at exactly its ratchet ceiling
  of 1102 (`repo_tests/python_file_size_ratchet_baseline.py:246`). Threading the new param
  through its two facade wrappers took it to 1113; that was tried and reverted. Raising a
  ceiling is forbidden, splitting is #5060's campaign. Because `contributions` is optional
  the facade keeps working untouched.
- **Those two wrappers (`_process_rrf_results`, `_build_rrf_results`) are UNWIRED** — nothing
  calls them. Not deleted, flagged in the PR body. Wiring belongs with #17208, which needs a
  caller for them anyway.
- **CI was red on the first push for a cause outside this PR** — a pre-existing
  `autobot-slm-backend` conftest failure. Fixed by #17206, which merged as `2323edc58f`;
  this branch is rebased onto it.
- **Measurement trap worth knowing:** grepping shard logs for a test filename proves nothing
  — the suite runs quiet and never names test files, so an existing collected test greps to
  zero exactly like an uncollected one. Verify collection via `testpaths` (pytest.ini:75)
  and `python_files` (pytest.ini:153) instead.

## tree context
This is child 1 of umbrella #17215 (multi-view retrieval cover), all on milestone v0.9.0:
#17207 (this) · #17208 cover-multiplicity scoring (blocked_by #17207, highest-leverage next)
· #17209 clause-aware chunking · #17210 lineage/supersession DAG (blocked_by #17209, #17213)
· #17211 bridge-term graph · #17212 token sensitivity (blocked_by #17207) · #17213
document-level entity resolution · #17214 disagreement reading queue (blocked_by #17208, #17210).
