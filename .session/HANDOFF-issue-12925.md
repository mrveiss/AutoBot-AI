# Handoff: issue-12925

status: complete (all three steps)
gates: backend/user_management=37 PASS · slm/user_management=26 PASS · import smoke both PASS · isort/black/flake8 PASS
worktree: .worktrees/issue-12925  (safe to remove after merge)

## Delivered

`rbac_middleware.py` is now **byte-identical** across both backends.

Steps 1 and 2 of this issue were already done on `Dev_new_gui` before this
session (backend denial auditing exists with 9 green tests; `TTL_5_MINUTES`
already comes from `autobot_shared.ssot_constants`). Only step 3 remained.

## Step 3's premise was wrong — record this

The issue says backend is "L1 + pubsub" and SLM is "L2 Redis", two designs
needing a decision. **Both were already L1 -> L2 -> DB with pub/sub.** The
316-line diff was ~85 lines of *dead* SLM cache helpers against a second key
prefix (`slm:perm:`), plus logger/TTL drift and docstrings.

Owner's decision (2026-08-01): keep L1->L2 as it runs; do **not** drop L1.

## Wired in, not deleted

Per the repo's absolute "never delete code — wire it in" rule, the unused
`_cache_get` / `_cache_set` / `_cache_delete` / `_redis_key` are now the single
cache path used by `get_user_permissions`, against the canonical
`_REDIS_KEY_PREFIX`. Only `_get_redis` went — a one-line alias for
`get_async_redis_client()` with zero callers, whose target every accessor still
calls directly.

## Bearing on #12647

This closes one of the two files blocking #12647's "no divergent twin files".
The other is `user_service.py` -> **#12924**.

**Relocating `rbac_middleware.py` to `autobot_shared` is NOT possible yet** — it
imports `UserService` and `TenantContext` from `user_management.services`, and
`user_service.py` is still forked (backend-only session + memory features). Once
#12924 converges `user_service`, this file becomes movable. Identical-twin now,
single-copy later.
