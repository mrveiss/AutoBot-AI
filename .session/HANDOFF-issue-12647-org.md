# Handoff: issue-12647-org

status: complete (for its slice — this is the LAST de-fork file in #12647)
pr: (see PR)
gates: shared=66 PASS (11 new) · backend/user_management=37 PASS · slm/user_management=26 PASS · backend org API import smoke PASS · isort/black/flake8 PASS
needs_rebase_before_merge: no
worktree: .worktrees/issue-12647-org  (safe to remove after merge)

## Delivered

`organization_service.py` (545 lines, byte-identical) converged via **injected
model classes**, per the owner's decision:

- canonical impl in `autobot_shared/user_management/organization_service.py`
  names neither `Organization` nor `User`;
- each backend subclasses it and binds `organization_model` / `user_model`;
- unbound subclass raises `TypeError` at construction.

## After this merges, #12647's de-fork work is DONE

Every shared-but-divergent file is resolved:
`base_service` (#12972) · `schemas.user` (#13007) · `models.base` (#13126) ·
six models (#13130) · `UserCore`/`OrganizationCore` (#13163) ·
`team_service` (#13164) · `user_service` incidental drift (#13178) ·
`organization_service` (this PR).

**What is NOT in #12647 and must not be pulled in:**
- `middleware/rbac_middleware.py` — 316 diff lines, but that is **#12925**:
  two deliberate cache designs (Redis-backed SLM vs in-process backend) plus
  the denial-audit gap. A design + security-port decision, not fork residue.
- `user_service`'s remaining 48 diff lines — **#12924** (session invalidation
  on password change; `session_service.py` is backend-only) and memory
  ownership reassignment (SLM has no `memory/` package — not applicable).
- `config.py` / `database.py` — confirmed **not** forks (single vs dual
  Postgres engine by design).

So #12647 can be closed once this merges, with #12924 / #12925 carrying the
two genuine feature gaps.

## Next in umbrella #12645

Owner picked **#12651** (two Playwright stacks) as the next child. It is
design-first: deliverable is one canonical browser interface with in-process
and Docker as pluggable strategies, plus the migration plan for
`content_reach/backends/browser.py` and the `chat_workflow/tool_handler.py`
fallbacks (`_web_search_via_playwright`, `_web_search_via_browser_vm`).
Coordinate with #12756 (pinchtab browser convergence).

Remaining after that: #12652 (chat-workflow scope doc), #12653 (frontend ADR).

## Trap

**#13162** — `Unit & Integration Tests` is the *frontend* job; the Python
suite is not a required check. A green PR is not evidence Python tests passed.
