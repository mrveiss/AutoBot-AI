# Handoff: issue-12647-user

status: complete (for its slice)
pr: (see below)
base_at_push: origin/Dev_new_gui at push time
gates: backend/user_management=37 PASS · slm/user_management=26 PASS · isort/black/flake8=PASS · CI=pending
needs_rebase_before_merge: no
worktree: .worktrees/issue-12647-user  (safe to remove after merge)

## Delivered

`services/user_service.py` incidental drift converged, 97 -> 48 diff lines.
SLM adopts `get_logger` / `now_utc`; backend adopts SLM's
`_build_user_list_base_query` decomposition (#576) and keeps its fuller
docstring.

## What is deliberately NOT converged

The remaining 48 lines are two backend-only features whose dependencies are
absent from SLM entirely:

- `SessionService` (password-change session invalidation) — tracked as
  **#12924**. A security gap, not fork residue; do not try to fold it in here.
- `memory.ownership_reassign` (delete-user memory reassignment) — SLM has no
  `memory/` package. Not applicable rather than missing.

## State of #12647 after this

Merged already: `base_service` (#12972), `schemas.user` (#13007),
`models.base` (#13126), six models (#13130), `UserCore`/`OrganizationCore`
(#13163), `team_service` (#13164).

Still open:
- `middleware/rbac_middleware.py` — 316 diff lines, but that is **#12925's**
  territory: two deliberate cache designs (Redis-backed SLM vs in-process
  backend) plus the denial-audit gap. Not plain fork residue.
- `services/organization_service.py` — 545 lines, byte-identical, blocked: it
  imports the concrete `User`/`Organization` at runtime and those stay
  backend-local by design (#13163). Needs its own decision (injected model
  set / registry lookup), not a copy of the `team_service` move.

`config.py` / `database.py` confirmed **not** forks.

## Trap

**#13162** — the required check `Unit & Integration Tests` is the *frontend*
job; the Python suite is not a required check. A green PR is not evidence the
Python tests passed. Run them locally.
