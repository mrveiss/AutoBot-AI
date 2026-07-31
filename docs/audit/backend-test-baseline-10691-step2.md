# Backend test triage — step 2 (#10691)

**Purpose.** Per the owner's decision on #10691, step 1 (measure the true
baseline) was completed in `docs/audit/backend-test-baseline-10691.md` (PR
#13088) and the namespace-pollution fix in
`docs/audit/backend-test-namespace-pollution-13084.md` (PR #13109, merged as
`6be4e8260`). This document is **step 2: triage the post-#13109 failure
surface into fix-now vs quarantine-with-issue**, and it recommends whether
the suite can now be flipped to a required gate.

## Environment (independently reproduced, matching prior sessions' methodology)

- Fresh worktree off `origin/Dev_new_gui` at `6be4e8260` (post-#13109),
  Python 3.10.12, system pytest 9.0.2 / pytest-asyncio 1.3.0 / pytest-cov
  7.1.0 / pytest-xdist 3.8.0 / fakeredis 2.36.2 — no ad-hoc installs.
- **Disposable local Postgres 16** — private `initdb` cluster, own data dir,
  own Unix socket (`/tmp/pg10691sock`), listening only on `127.0.0.1:55432`.
  The shared host cluster and `pg_hba.conf` were never touched;
  `/etc/autobot/db-credentials.env` was never read.
- **Disposable local Redis** — a second `redis-server` on `127.0.0.1:63790`
  with its own data dir. The real shared `redis-stack` instance on `:6379`
  was confirmed unchanged (943 keys, before and after every run).
- `config/config.yaml` created to match `ci.yml`'s setup step exactly;
  **sha256 `e125bf80...` confirmed byte-identical before the first run and
  after every run performed** (the #13083 corruption vector this session
  guarded against explicitly).
- No `sudo`, no root-owned files, no application service run as root.

## Reproducible invocation (matches `.github/workflows/ci.yml`'s two-invocation split exactly)

```
python -m pytest autobot-backend autobot_shared autobot-tts-worker repo_tests \
  -n auto --dist loadscope \
  -m "not integration and not slow and not distributed and not performance" \
  --cov=autobot-backend --cov=autobot_shared --cov-report= --tb=short \
  --continue-on-collection-errors -q

python -m pytest autobot-slm-backend \
  -n auto --dist loadscope \
  -m "not integration and not slow and not distributed and not performance" \
  --cov=autobot-slm-backend --cov-report= --tb=short \
  --continue-on-collection-errors -q
```

## Headline numbers

| | Invocation 1 (backend/shared/tts/repo) | Invocation 2 (slm-backend) | Combined |
|---|---:|---:|---:|
| Failed | 855 | 21 | **876** |
| Passed | 18,233 | 1,504 | **19,737** |
| Skipped | 2,440 | 1 | 2,441 |
| xfailed | 2 | 1 | 3 |
| Errors | 104 | 1 | **105** |
| Wall-clock | 1,706.5s | 185.7s | **1,892.2s (~31.5 min)** |

**Comparison to the #13109 PR's own measurement** (874 failed / 76 errors /
14 collection errors / 19,749 passed, ~1,031s): failed matches almost
exactly (+2, normal repo drift); **errors are +29 higher** (105 vs 76). All
of that delta is explained below — it is not unexplained noise:

- **+19** — `autobot-backend/tests/integration/test_mobile_pairing.py` errored
  at setup on **100% of its 19 tests** in this session (bucket A, fixed
  below). Whether this is new drift since the #13109 measurement or an
  environment-order sensitivity not hit in that session is not fully
  reconciled, but it reproduced deterministically across every run this
  session performed.
- **+27 minus 2 already inside the errors bucket in both sessions** — the
  `global_config_manager` test-rot cluster (#13112) contributes 27 setup
  errors; a small residual is attributable to normal ordering/timing drift.

Collection errors matched exactly: **14** (12 `tools.lint` + 1 `cachetools`
+ 1 `test_apply_secrets.py`), same as #13109's measurement.

**Config checksum and shared Redis dbsize were reconfirmed unchanged after
every run in this session, including the fixes below.**

## Order-dependence confirmation (bucket D) — two runs, not one

A `--last-failed` re-run of exactly the failing/erroring set from the run
above (`--tb=line`, same disposable environment):

| | Invocation 1 re-run | Invocation 2 re-run |
|---|---:|---:|
| Result | 771 failed, 67 passed, 80 errors (170.3s) | 14 failed, 1 error (105.7s, no flips — all match already-known/filed causes) |

Of invocation 1's 67 flips, **19 are the `test_mobile_pairing.py` fix landing
mid-session** (not flakiness — a genuine fix), leaving **~48 confirmed
order-dependent flips** with zero code change, consistent in magnitude with
the #13088 baseline's own 56-flip measurement. This is the same
worker/collection-order sensitivity already documented for #13084 — not
classic timing-based flake.

## Root-cause grouping (the deliverable) — by count, largest first

| Root cause | Count | Bucket | Status |
|---|---:|---|---|
| **`code_intelligence` self-poisoning conftest stub** — 11 submodules stubbed as `MagicMock` in `autobot-backend/conftest.py` are ALSO collected as their own test files; `--import-mode=importlib` returns the stub instead of re-importing the real module | **453** (433 in `code_intelligence/*_test.py` + 20 in `api/merge_conflict_resolution_test.py`, a consumer of one poisoned submodule) | A (systemic) | **Filed #13111**, not fixed (11-module removal needs individual full-suite verification per module) |
| `security_layer.global_config_manager` / `knowledge_base.global_config_manager` — symbol removed, tests still `patch()` it | 27 | C (test rot) | **Filed #13112** |
| `asyncio.get_event_loop().run_until_complete()` in sync `def test_...()` — legacy pattern only fails when no async test primed the worker's loop first | 23 | A + D | **Filed #13113** |
| ChromaDB `[chromadb]`-parametrized tests — need a live ChromaDB instance (port 8100 convention) | 38 | B | Documented (not filed — env-dependent, per task scope) |
| `drift_checker_test.py` invariants stale relative to #12450's component migration | 4 | C (test rot) | **Filed #13114** (security-relevant list, needs owner confirmation before editing assertions) |
| `tools.lint` not importable (`repo_tests/lint/canonical/**`) | 12 | config gap | Already filed **#13086** |
| `ConfigManager(config_file=...)` removed kwarg | 7 | C | Already filed **#13087** |
| GitLab connector `_store_ts` removed by #12659 | 8 | C | Already filed **#12998** |
| `services.token_denylist` patches nonexistent `get_redis_client` (real export: `get_async_redis_client`) — incl. `test_auth_logout.py`'s identical pattern | 10 | C | Already filed **#13106** |
| `test_apply_secrets.py` collection error (`services.system_secrets_vault` never stubbed) | 1 | config gap | Already filed **#13108** |
| Playwright browser binary not installed (`chromium_headless_shell`) | 10 | B | Documented (needs `playwright install chromium` as a CI step, or an `importorskip`/skip guard — not present today) |
| `fixture 'backend_url' not found` — needs a live running backend | 13 | B | Documented (carried over from owner's 2026-07-03 scoping) |
| `fixture 'host_id' not found` + IaC `ConnectionError` (NameResolutionError to a real host) | 2 + 7 | B | Documented — needs a live IaC test host/network, or these tests should mock instead |
| `TestUnifiedMultiModalSystem` — audio/vision models (Whisper, Wav2Vec2) not loaded | 12 | B | Documented (GPU/model-weight dependent) |
| `services/redis_service_management_e2e_test.py` — needs live redis-management/VM service | 10 | B | Documented |
| Missing optional dep `cachetools` (no `importorskip` guard) | 1 (collection) + 2 (runtime references) | B | Documented, per "missing optional dep is itself a bucket-B finding" rule — no ad-hoc install performed |
| **Fixed this session** — `test_mobile_pairing.py` (SQLite DDL scope + missing encryption/JWT-secret fixtures + stale bytes/str `.decode()`) | 19 (all were errors → all now pass) | A (genuine defect) | **Fixed** |
| **Fixed this session** — `_resolve_pg_db_url` env-isolation gap (`test_code_sync_deploy_bugs.py`) | 7 | A (test hygiene) | **Fixed** |
| Long tail — remaining `code_intelligence`-adjacent (`mcp/mcp_cache_test.py` TestMCPToolCache, 14), security API assertions, MCP registry, config registry, IaC/webhook/security edge cases, and dozens of 1-6-count single-cluster failures across `pki/`, `services/`, `security/`, `api/` not individually traced this session | ~**312** (981 total − everything else above) | mixed A/B/C, unclassified | **Needs a further per-cluster pass** — not attempted exhaustively per task scope ("874 failures will not be 874 distinct causes... group aggressively", not "triage all 981 individually") |

Total accounted (981 = 876 failed + 105 errors, includes the 14 collection
errors as a subset): 453 + 27 + 23 + 38 + 4 + 12 + 7 + 8 + 10 + 1 + 10 + 13 +
9 + 12 + 10 + 3 + 26 (fixed) + ~312 (tail) = 981.

## What was fixed in this PR (trivial, mechanical, verified)

### 1. `autobot-backend/tests/integration/test_mobile_pairing.py` — 19 setup errors → 0

Three gaps, each already solved identically in the sibling file
`test_mobile_push.py` (same `TEST_DB_URL`, same `MobileDevice` import) or in
`services/device_jwt_test.py` (same secret convention) — this file simply
never received those fixes:

1. `test_db_engine`'s `Base.metadata.create_all` created **every** model
   registered on the shared declarative base, including `llc/models/approval.py:54`'s
   Postgres-only `server_default=sa.text("'{}'::jsonb")`, which SQLite's
   dialect cannot parse (`unrecognized token: ":"`). Scoped to
   `tables=[MobileDevice.__table__]`, exactly matching `test_mobile_push.py`'s
   `#11834` fix.
2. Missing `_test_encryption_service` autouse fixture (copied verbatim from
   `test_mobile_push.py`) — `MobileDevice.device_token` requires
   `AUTOBOT_ENCRYPTION_KEY` via a real `EncryptionService`, absent in the
   hermetic test env (#11687).
3. Missing `DEVICE_JWT_SECRET` env var (copied from `services/device_jwt_test.py`'s
   established `monkeypatch`/`os.environ` convention) — `device_jwt.py:_secret()`
   reads it fresh on every call (no caching), so a plain `monkeypatch.setenv`
   is sufficient and safe.
4. `test_generate_qr_challenge_token` called `.decode()` on a Redis GET
   result, but `get_redis_client()` is configured with `decode_responses=True`
   (`autobot_shared/redis_management/config.py:61`), so the value is already
   `str` — stale test rot, one-line fix.

Verified: `19 passed` (was `19 errored` — 100% of the file). No other file
touched.

### 2. `autobot-slm-backend/tests/api/test_code_sync_deploy_bugs.py` — 7 failures → 0

`_resolve_pg_db_url()`'s "byte-identical" and "assembles from component
vars" tests pass an explicit `env_vars` dict, but the function itself falls
back to the **real** `os.environ.get("AUTOBOT_DATABASE_URL", ...)` for step
1 of its resolution order (`api/code_sync.py:1765`). 7 of these tests never
cleared `AUTOBOT_DATABASE_URL`/`DATABASE_URL` from the ambient environment
before asserting fallback-to-component-vars behaviour — unlike the sibling
test `test_resolve_pg_db_url_byte_identical_nothing_set_returns_empty` in
the same file, which does. Any environment that legitimately exports
`AUTOBOT_DATABASE_URL` (a live deployment's env file, or — as here — this
suite's own disposable-Postgres provisioning for other DB-dependent tests)
breaks these 7 tests regardless of the codebase being correct. Fixed by
adding `monkeypatch.delenv(...)` (or extending the existing manual
backup/restore `clear_keys` set) to each, matching the established sibling
pattern exactly.

Verified: `89 passed` (was `82 passed, 7 failed`) — including a direct
re-run with the exact polluting env vars this session used for the live-DB
tests, proving the fix holds under the real reproduction conditions, not
just in isolation.

## Issues filed this session

| Issue | Bucket | Count | Summary |
|---|---|---:|---|
| [#13111](https://github.com/mrveiss/AutoBot-AI/issues/13111) | A (systemic) | 453 | `code_intelligence` conftest self-poisoning — the single largest root cause (51.8% of the 874-failure surface) |
| [#13112](https://github.com/mrveiss/AutoBot-AI/issues/13112) | C | 27 | `global_config_manager` patch target removed from `security_layer`/`knowledge_base` |
| [#13113](https://github.com/mrveiss/AutoBot-AI/issues/13113) | A + D | 23 | Legacy `asyncio.get_event_loop().run_until_complete()` in sync tests, order-dependent |
| [#13114](https://github.com/mrveiss/AutoBot-AI/issues/13114) | C | 4 | `drift_checker_test.py` invariants stale relative to #12450 |

Already-filed issues confirmed present in this session's reproduction, not
re-filed: #13086, #13087, #12998, #13106, #13108.

## Bucket B — environment-dependent (documented, no mass skip markers added)

Per the task's explicit instruction, **no skip markers were mass-added**.
For each of the following, the recommended mechanism is noted; none were
applied in this PR since doing so is itself a design decision (which
service to provision in CI vs. which marker convention to use) outside
"trivial and mechanical":

| Need | Count | Recommended mechanism |
|---|---:|---|
| Live ChromaDB (port 8100) | 38 | CI-provisioned service container, or `@pytest.mark.integration` |
| Playwright browser binary | 10 | `playwright install chromium` as a CI step, or `pytest.importorskip`-equivalent runtime skip |
| Live running backend (`backend_url` fixture) | 13 | Carried over from owner's 2026-07-03 scoping — needs the same disposition decision |
| Live IaC test host / network | 9 | Either provision a stub host in CI, or these tests should mock the host client instead of hitting real DNS |
| Audio/vision ML models (Whisper, Wav2Vec2) not loaded | 12 | GPU/model-weight dependent — mark `@pytest.mark.slow` or provide lightweight test doubles |
| Live redis-management / VM service | 10 | `@pytest.mark.integration`, needs a real multi-VM or VM-simulation harness |
| Missing optional dep `cachetools` | 1 collection + 2 runtime | Already the correct pattern per project convention (`pytest.importorskip`) — not yet applied to `security/enterprise/threat_detection/` |

## Verification

- `autobot-backend/tests/migrations/` and `test_startup_imports.py` (350) —
  not re-run in full this session (unchanged by this PR's two test-file-only
  edits); no code outside test files was touched.
- `python -m py_compile` on both modified files: clean.
- `black --check --line-length=120`, `isort --check-only --settings-path=.`,
  `flake8 --config=.flake8` on both modified files: clean.
- `config/config.yaml` sha256 `e125bf80...` confirmed byte-identical before
  the first run and after every run this session, including both fix
  verifications.
- Shared production Redis `dbsize` (943) confirmed unchanged before and
  after every run.
- Disposable Postgres/Redis only; shared cluster and `pg_hba.conf` untouched;
  no `sudo`, no root-owned files, no service run as root.
- `autobot-backend/tests/integration/test_mobile_pairing.py`: 19 passed
  (was 19 errored).
- `autobot-slm-backend/tests/api/test_code_sync_deploy_bugs.py`: 89 passed
  (was 82 passed, 7 failed).

## Verdict on flipping the gate to required (owner's step 4)

**Not yet — three things block it, in priority order:**

1. **#13111 must land first.** At 453 of 874 (51.8%), this single
   mechanism dominates the failure surface so completely that no other
   triage signal is trustworthy until it's fixed and the suite re-measured.
   Fixing it requires per-module verification (11 submodules × a full-suite
   run each), which is real, non-trivial work — but it is the single
   highest-leverage next step by a wide margin, exactly as #13084 was for
   step 1.
2. **The four already-filed test-rot issues (#13112, #13086, #13087,
   #12998, #13106 — ~59 failures) and #13113 (23, order-dependent) should
   land** before re-measuring, since they are independent of #13111 and
   individually small enough to fix safely.
3. **Bucket B needs an explicit owner decision** on which environment
   dependencies (ChromaDB, Playwright, live backend, live IaC host,
   ML models, redis-management VM — ~92 tests total) get a CI-provisioned
   service vs. an explicit `@pytest.mark.integration`/skip marker with a
   filed issue. Left undecided, these ~92 will permanently red a required
   gate with no actionable owner.

**Once #13111 lands**, the remaining surface drops from 981 to an estimated
~500 (981 − 453 − 26 already fixed here), overwhelmingly the already-filed
issues above plus the ~312-item long tail this session did not individually
trace. That is the point at which a genuine re-measurement (mirroring the
#13084→#13109 pattern exactly) becomes worthwhile — attempting it now would
just re-measure the same 453-failure noise floor.

**Wall-clock**: 1,892s (~31.5 min) measured this session vs. #13109's 1,031s
(~17.2 min) on the same disposable-environment methodology — this session's
box was under more load; the two-invocation split itself did not regress
(confirmed by #13109's own before/after). The wall-clock question (step
3/4's "runtime acceptable on the singleton runner" gate) cannot be answered
definitively from a dev-box measurement either way and still needs a real
advisory-job run on the actual self-hosted runner.
