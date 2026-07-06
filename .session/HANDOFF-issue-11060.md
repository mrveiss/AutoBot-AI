# Handoff: issue-11060

status: complete
pr: #11068
base_at_push: rebased onto origin/Dev_new_gui (superseded #11022 IndexError guard with str.replace)
gates: tests=PASS (8 new + 16 existing wiring); api-wiring=PRE-EXISTING-FAIL (Redis-refused + other-file duplicate op-ids, not this change); SAST=PRE-EXISTING-FAIL (4 findings/3009 files repo-wide baseline, neither changed file implicated)
needs_rebase_before_merge: no
remaining:
  - Tenant-scope learned-strategy Redis keys + fail-closed → spun out to #11071 (higher-risk, own PR)
  - Sibling P0s in umbrella #11058 still open: #11059 ProcessAdapter shell RCE, #11061 OAuth state/PKCE, #11062 eval DoS
blocked_on:
worktree: .worktrees/issue-11060  (safe to remove after PR #11068 merges)

## What this branch does

Hardens the self-improvement / learned-planning path (part of July-6 autonomy
hardening umbrella #11058):

- `api/agents_self_improvement.py`: was unauthenticated → reads require
  `get_current_user`, destructive `reset-learning` requires `check_admin_permission`.
- `orchestration/orchestrator_prompts.py`: learned template now substituted with
  `str.replace` (not `str.format` — closes `{goal.__class__...}` traversal; also
  supersedes the #11022 `{0}` IndexError guard), sanitized, and `<<<BEGIN/END_LEARNED_APPROACH>>>`
  data-framed. `_sanitize_injected` now strips `<<<`/`>>>` so injected content
  cannot forge markers (hardens the trajectory leg too).

## Merge notes

- Base is Dev_new_gui → `Closes #11060` will NOT auto-close on merge; close manually.
- The two red checks (api-wiring, SAST) are pre-existing repo-wide baseline
  failures, not introduced here → admin-merge (`gh pr merge --squash --admin`)
  per repo convention once required checks are green.
