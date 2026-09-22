# Handoff: issue-17271-loop-audit

status: complete
pr: #17296
base_at_push: aec5e09cfbbf0ff1101adbe72828f362598b4b67
base_branch: main  (NOT Dev_new_gui — renamed 2026-09-12; `release` is the release branch)
gates: docs-only branch. wiring=N/A duplication=N/A backend-tests=N/A (no code changed).
  RAN and passed: the doc-cross-link half of pre-commit repo-conventions (#13876); pre-push
  repo_tests 6/6 after fix. Distinguish these from the code gates, which were not run because
  nothing they measure was touched.
  DID NOT RUN, and an earlier revision of this line wrongly claimed it did: the third-party-name
  half of that same hook. scripts/lint-conventions.sh:141-146 takes a "SKIPPED (not passed)"
  branch when no denylist is readable, and on this machine CONVENTIONS_DENYLIST is unset and the
  documented default file does not exist; the CONVENTIONS_DENYLIST repo secret is unset too, so
  CI emits a ::warning:: and skips it as well (code-quality.yml:388-390). Anonymisation on this
  branch was verified by hand, not by a gate. Tracked at #15333. Reading aggregate hook output as
  covering a check that opted out of reporting is exactly what that script's wording exists to
  prevent.
needs_rebase_before_merge: no  (branch is up to date with origin/main at handoff)
worktree: /home/martins/AutoBot-Ai/.worktrees/issue-17271-loop-audit  (locked; safe to remove after merge)

## What this branch contains

Two files, no code: `docs/research/local-first-agent-runtime-context-frugal-loop.md` (new) and one
row in `docs/research/_index.md`. A comparative audit of AutoBot's agent turn against an external
local-first agent runtime.

## Constraint that outlives this branch

The source's name, vendor, repo and site must never appear in the doc, its filename, or any issue,
PR, branch or commit. Its *stack* was generalised for the same reason — inference runtime, grammar
format and GPU kernel names fingerprint a project as surely as its name. Our own stack (Ollama,
vLLM, Chroma, Redis, Postgres, Playwright, MCP, SQLite) is named freely, because naming our
dependencies discloses nothing about where we looked. All artifacts were swept clean; re-sweep
before any further push.

## Gate history worth knowing

First push was **blocked** by `repo_tests/doc_sync_hook_resolves_indexer_15845_test.py`: the main
checkout's `_index.md` carried another session's row for `durable-subagent-orchestration-controller-state`,
whose doc is untracked in their tree, and I had copied the file wholesale. Fixed by rebuilding
`_index.md` from `origin/main` with only this branch's row. **Do not re-introduce their row here** —
it belongs with their doc, in their PR.

## remaining

- Review and merge #17296. Nothing else on this branch.

## Filed from this work (not on this branch)

- Umbrella **#17271**; children **#17272** (identity-bearing GitHub publish crosses no approval
  seam, security/high), **#17273** (disconnected client leaves the LangGraph turn running; no total
  timeout, bug/high), **#17274** (cognifiers fork the shared JSON parser), **#17277** (no
  prompt-drift detection), **#17278** (volatile block prepended ahead of the stable prefix; native
  `blocked_by` #17277), **#17279** (eval scores drift, not task success). Native sub-issue edges set.
- **#17297** — a committed conflict block in a tracked file on `main`, found by this protocol's
  end-of-session marker grep. Pre-existing in base; not introduced here.
- Appends proposing children on existing threads: **#16116**, **#13587**, **#17217**, **#10603**.
  These still need converting into real child issues.
- Owner decisions pending: **#7420**, **#12652**, **#11221** — three closed threads whose condition
  is still live in the code. Recommendation on each is posted on its thread.
- Routed without duplication, do NOT re-file: **#16619**, **#17219**.

## Sequencing recommendation

Build **#17218** (CI guard: fail when a declared control has no production call path) before any of
the six children. This audit produced three independent pieces of evidence for it — #7420, #12652
and #11221 each closed while their condition stayed true. Within the six, **#17277 lands before
#17278**: once a prefix is deliberately held stable for cache reuse, nothing else notices when it
stops being stable.

## Not mine — do not sweep

- The main checkout holds another session's untracked `docs/research/durable-subagent-orchestration-controller-state.md`
  and its `_index.md` row. Left exactly as found.
- PR **#17187** (`remove-hardcoded-pricing`) was RED at handoff — 3 failures, 7 cancelled. Unowned
  by this session and unfixed.
