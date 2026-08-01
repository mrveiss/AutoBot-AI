# Handoff: issue-12647-team

status: complete (for its slice)
pr: #13164
base_at_push: 0441614d2
gates: shared-tests=40 PASS (8 new) · slm/user_management=26 PASS · backend/user_management=34 PASS +3 pre-existing FAIL · isort/black/flake8=PASS · CI=pending
needs_rebase_before_merge: no
worktree: .worktrees/issue-12647-team  (safe to remove after merge)

## Delivered

`team_service.py` (701 lines, byte-identical across both backends) moved to
`autobot_shared/user_management/team_service.py`, re-export shim in each
backend, 8 identity tests.

Placed **flat**, matching `base_service.py`, rather than creating a second
`services/` location for the same category of file.

## Sibling PR

**#13163** (branch `issue-12647`) — the `UserCore`/`OrganizationCore` abstract
cores. No file overlap with this branch; merge order does not matter.

The 3 `rbac_denial_audit_test.py` failures and the 5 `models/base_test.py`
failures seen on this branch are **pre-existing on `Dev_new_gui`** and are
fixed by #13163, not here.

## Why organization_service.py is NOT in this PR

It is byte-identical too (545 lines), but it does
`from user_management.models import Organization, Team, User` at **runtime**.
The concrete `User`/`Organization` stay backend-local by design (#13163), so
moving this service would make `autobot_shared` import a backend-local
package — an inverted dependency. It needs its own resolution: either a
registry lookup, a constructor-injected model set, or accepting the concrete
classes as parameters. Do not copy this PR's approach onto it blindly.

## Remaining in #12647 after both PRs merge

| item | size | note |
|---|---|---|
| `middleware/rbac_middleware.py` | 316 diff lines | real semantic drift |
| `services/user_service.py` | 97 diff lines | real semantic drift |
| `services/organization_service.py` | 545 lines, identical | blocked as above |

`config.py` / `database.py` are confirmed **not** forks.
