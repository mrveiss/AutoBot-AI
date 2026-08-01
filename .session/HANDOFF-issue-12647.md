# Handoff: issue-12647

status: partial
pr: #13163
base_at_push: 3f343b346
gates: shared-tests=45 PASS · backend/user_management=37 PASS · slm/user_management=26 PASS · llc=1367 PASS · black/ruff=PASS · CI=pending
needs_rebase_before_merge: no
worktree: .worktrees/issue-12647  (safe to remove after merge)

## Delivered

Abstract-core extraction for the last two forked model files, per the owner's
2026-07-31 decision (asked and answered in-session):

- `autobot_shared/user_management/models/user.py` — `UserCore` (`__abstract__`)
- `autobot_shared/user_management/models/organization.py` — `OrganizationCore`
- both backends keep a thin concrete subclass with their own extras
- `models/core_test.py` pins both concrete schemas against the pre-move shape

Zero schema change on either side, measured before/after per class. Both full
model registries `configure_mappers()` cleanly.

Second commit repairs two test files that were red on `Dev_new_gui` itself,
left by this issue's own earlier slices (#13126, #13130).

## Remaining in #12647 (do not assume these are done)

| item | size | note |
|---|---|---|
| `middleware/rbac_middleware.py` | 316 diff lines | real semantic drift |
| `services/user_service.py` | 97 diff lines | real semantic drift |
| `services/team_service.py` | 701 lines, byte-identical | relocatable today — all runtime deps (`Team`, `TeamMembership`, `audit`, `base_service`) already live in `autobot_shared` |
| `services/organization_service.py` | 545 lines, byte-identical | blocked: imports the concrete `User`/`Organization` at runtime, and those stay backend-local by design |

`config.py` / `database.py` are confirmed **not** forks (single vs dual
Postgres engine by design) — do not re-open that thread.

## Traps for the next session

- The abstract cores must never gain a backend-only column or relationship.
  Promoting one changes the *other* backend's schema. `core_test.py`'s
  `test_backend_only_features_stay_out_of_the_shared_core` fails if you try.
- Backend's `User` and SLM's `User` map the same table name onto the same
  `Base.metadata`. Anything that imports both in one interpreter collides —
  `core_test.py` uses a subprocess per class for exactly this reason.
- `declared_attr` is required for foreign keys and relationships on the cores;
  a plain `mapped_column(..., ForeignKey(...))` or bare `relationship()` on an
  abstract base cannot be shared between mapped classes.
- **#13162**: the required check `Unit & Integration Tests` is the *frontend*
  job. The Python suite (`ci.yml` → `security-tests`) is not a required check,
  so red Python tests merge silently. Run the Python suite locally until that
  is fixed; do not read a green PR as proof the Python tests passed.
