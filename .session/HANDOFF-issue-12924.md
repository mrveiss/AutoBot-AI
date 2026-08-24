# Handoff: issue-12924

status: complete
gates: shared/user_management=79 PASS (13 new) · backend=65 PASS +1 pre-existing FAIL · slm=35 PASS +1 pre-existing FAIL · isort/black/flake8 PASS
worktree: .worktrees/issue-12924  (safe to remove after merge)

## The issue's premise was backwards — read this before touching it again

It said "backend invalidates sessions, SLM does not". In effect **neither did**:

- backend wrote a blacklist **nothing reads** — `is_token_blacklisted` has zero
  production callers, and `_extract_user_from_jwt` is sync so it cannot await
  Redis at all;
- SLM had a **working** jti denylist (honoured in `decode_token_async`) that
  password change never triggered, and no user→jti index to revoke "all other
  sessions" with.

## Delivered — password epoch (owner's 2026-08-01 decision)

`autobot_shared/user_management/password_epoch.py`: per-**token-subject**
epoch. One write revokes every outstanding token for that subject.

- `encode_jwt` now stamps `iat` — the epoch check is meaningless without it.
- Check runs where an await is reachable: backend `get_current_user`
  (sync extraction now carries `iat` through) and SLM `decode_token_async`.
- **Three** password-change paths set it, including the backend's config-backed
  `api/auth.py` self-service endpoint, which never went through
  `UserService.change_password` and had no revocation whatsoever.

Fails open, loudly, on Redis failure (matches `token_denylist.is_jti_revoked`).
Pre-#12924 tokens have no `iat` → not revoked, so deploying does not sign
everyone out.

## Two traps for the next session

1. **`password_epoch.py` deliberately uses stdlib `logging`, not `get_logger`.**
   `autobot-slm-backend/services/auth.py` imports it at module scope, and that
   file's test harness (`tests/api/test_auth_logout.py`) loads it with most of
   the config stack MagicMock'd. `get_logger` builds a RotatingFileHandler from
   config and raises under that harness — it broke collection until switched.
   Its sibling `services/token_denylist.py` uses stdlib logging for the same
   reason. Do not "fix" it back.
2. **`SessionService` was kept, not removed.** It is still the only mechanism
   that can spare the caller's *current* token. The epoch is what actually
   stops the old sessions.

## Pre-existing failures — not from this work, verified on base

- `autobot-backend/api/user_management/users_password_change_test.py::TestPasswordChangeRateLimiting::test_rate_limit_exceeded_returns_429`
- `autobot-slm-backend/tests/api/test_auth_logout.py::TestRevokeTtlFromToken::test_revoke_called_with_positive_ttl`
- `autobot_shared/auth/test_slm_permission_parity.py` — collection error on base

## Bearing on #12647

With #12925 (PR #13213) this clears the second of the two files blocking
"no divergent twin files". `user_service.py`'s divergence is now down to
backend-only `SessionService` + `memory.ownership_reassign` — the latter is
inapplicable to SLM (no `memory/` package). Re-run the closure gate on #12647
once both merge.
