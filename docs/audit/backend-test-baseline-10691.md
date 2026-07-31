# Backend test baseline measurement (#10691, step 1)

**Purpose.** Per the owner's 2026-07-31 decision on #10691 ("enable the full backend
suite as a REQUIRED check"), this document is **step 1 (measure the true baseline)**
of the 4-step execution order the decision specifies:

1. Measure the true baseline — this document.
2. Triage into fix-now vs quarantine-with-issue.
3. Add the job as advisory.
4. Flip to required once green and the runtime is acceptable.

This is a measurement-and-triage exercise only. No application code was fixed in
this session; every genuine defect found is filed as a separate GitHub issue
(list below) and left for a follow-up PR.

## Environment

- Fresh checkout of `origin/Dev_new_gui`, Python 3.10.12, all `requirements-ci.txt`
  test tooling already present system-wide (`pytest 9.0.2`, `pytest-asyncio 1.3.0`,
  `pytest-cov 7.1.0`, `pytest-xdist 3.8.0`, `fakeredis 2.36.2`) — no ad-hoc installs
  were performed.
- **Disposable local Postgres 16** — private `initdb` cluster, own data dir, own
  Unix socket, listening only on `127.0.0.1:55432`; the shared host cluster's
  `pg_hba.conf` was never touched and `/etc/autobot/db-credentials.env` was never
  read.
- **Disposable local Redis** — a second `redis-server` instance started on
  `127.0.0.1:63790` with its own data dir, specifically to avoid touching the
  machine's real shared Redis instance (a live `redis-stack` process on `:6379`
  with 948 keys, serving the actual running AutoBot deployment on this box).
  `AUTOBOT_REDIS_HOST`/`AUTOBOT_REDIS_PORT`/`REDIS_HOST`/`REDIS_PORT` were pointed
  at the disposable instance; the shared instance's `dbsize` was confirmed
  unchanged (948, before and after) throughout every run.
- `config/config.yaml` and `data/`, `logs/`, `static/` were created to match
  `ci.yml`'s "Create necessary directories and config files" step exactly.
- No pytest-randomly is installed (checked `pip list`), so `-p no:randomly` was
  not needed — collection order is deterministic given a fixed test-file layout.

## Reproducible invocation

Collection-only census (no marker filter, to get the complete import/collection-error
picture regardless of `-m`):

```
python -m pytest --collect-only -q
```

Full measurement run (mirrors `.github/workflows/ci.yml`'s existing, non-required
`security-tests` job exactly, since promoting *that* job to required + widening its
trigger to `Dev_new_gui` PRs is literally the gap #10691 describes):

```
AUTOBOT_POSTGRES_HOST=127.0.0.1 AUTOBOT_POSTGRES_PORT=55432 AUTOBOT_POSTGRES_USER=postgres \
AUTOBOT_POSTGRES_DB=autobot_test \
AUTOBOT_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/autobot_test \
AUTOBOT_USERS_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/autobot_test \
AUTOBOT_REDIS_HOST=127.0.0.1 AUTOBOT_REDIS_PORT=63790 REDIS_HOST=127.0.0.1 REDIS_PORT=63790 \
python -m pytest \
  -n auto --dist loadscope \
  -m "not integration and not slow and not distributed and not performance" \
  --tb=short -q \
  --continue-on-collection-errors \
  --deselect "autobot-backend/skills/governance_test.py::test_semi_auto_requires_review" \
  --junit-xml=<path>
```

The one `--deselect` is required to get *any* completed run at all — see
"Confirmed hangs" below; it is not a coverage change, it is what made
measurement possible in finite time.

Flakiness re-run (same environment, `--last-failed` against the run above):

```
python -m pytest --last-failed -n auto --dist loadscope -m "..." --continue-on-collection-errors --deselect ... --junit-xml=<path>
```

## Headline numbers

| Metric | Value |
|---|---|
| Tests collected (unfiltered, `--collect-only`) | 20,203 |
| Collection errors (unfiltered) | 252 |
| Full measurement run (marker-filtered, matches CI) | **2,330 failed, 15,226 passed, 2,307 skipped, 3 xfailed, 660 errors** |
| Full-suite wall-clock | **1,175.95 s ≈ 19 min 36 s** (single run, 22-core `-n auto --dist loadscope`) |
| Re-run of the failing/erroring set (`--last-failed`) | 2,274 failed, **56 newly passed**, 659 errors, 314.33 s |
| Flaky / order-dependent tests identified | **56** (≈1.9% of the failing population) |

The wall-clock number is the single most decision-relevant figure: **~20
minutes per PR on the singleton self-hosted runner**, serialized against every
other required check, is a material cost — before any of the ~2,990
failing/erroring tests are fixed. Two of those tests, before being
worked around, made the run **never finish** (see below); the ~20-minute
figure already excludes them.

## Confirmed hangs (found via `py-spy`, not simulated)

These are the most important findings of this measurement, because a required
check that never completes is worse than a required check that fails.

### Hang 1 — genuine deadlock, `autobot-backend/skills/db.py:32/42/45`

`_SkillsEngineManager.get_session_factory()` acquires its own
non-reentrant `threading.Lock` and, **while still holding it**, calls
`self.get()`, which tries to acquire the **same** lock again on the same
thread. On the very first call in a process (before `initialization/lifespan.py`
has warmed up the engine), this is an unconditional self-deadlock with no
timeout anywhere in the path.

Reproduced via `autobot-backend/skills/governance_test.py:39`
(`test_semi_auto_requires_review`), the *only* test in that file that reaches
the real, unmocked `_persist_approval` path (every other `SEMI_AUTO` test in
the same file patches `skills.governance._persist_approval` directly). `py-spy
dump` on the hung xdist worker showed its `MainThread` parked exactly inside
`with self._lock:` at `db.py:32`, called from `db.py:45`, called from within
the `with self._lock:` block starting at `db.py:42` — a textbook non-reentrant
self-deadlock. Confirmed the test was deselected and the rest of the suite
completed normally; without the deselect, the master pytest-xdist process
(`xdist/dsession.py:154`, blocking `queue.get()`) waits forever because that
one worker never reports back.

Filed as **#13082** (bucket A: genuine defect). Not fixed in this session per
task scope.

### Hang 2 — ~10 extra minutes of trailing wall-clock, LLC background schedulers

A separate xdist worker froze at 99% completion for roughly 10 minutes with
zero CPU progress across two full-suite runs. `py-spy dump` showed its
`MainThread` idle inside asyncio's `select()`/`_run_once`, with the scheduled
wake time advancing by **exactly 300.1 seconds** between two dumps taken 5
minutes apart — i.e. a live poll loop re-arming, matching `BudgetWatchdog`'s
default `_POLL_INTERVAL_SECONDS = 300` (`llc/scheduler/budget_watchdog.py:36`)
exactly. `initialization/lifespan.py` starts `BudgetWatchdog`, `LivenessMonitor`
(60s default), and a `CommunityClusterer` loop (6h) unconditionally on real app
startup; some test that exercises the full lifespan does not appear to cancel
them cleanly at teardown. This one **did** eventually resolve on its own
(~2 cycles), so it inflates wall-clock rather than hanging forever, but it is
non-deterministic and worth ~10 minutes on every affected run.

Filed as **#13085** (bucket A). Exact offending test file not pinned down in
the time available — the mechanism is solidly evidenced; identifying the
specific fixture/test is left to the fix PR.

## Shared-state mutation (found, and it is real)

`autobot-backend/utils/thread_safety_test.py::test_concurrent_config_saves`
(lines 187-234) attempts to redirect `ConfigService._save_config_to_file`
writes into a `tempfile.TemporaryDirectory()` by patching
`unified_config_manager.base_config_file`. **The redirect did not take effect
on any of the 3 full-suite runs performed in this session** — the real
worktree file `config/config.yaml` was overwritten every time with exactly the
content the test constructs (`{"test_key": "value_N", "iteration": N}`, N
matching the test's own loop index, incrementing run to run: 8, then 9, then
9 again). This is exactly the failure mode the umbrella issue's decision
comment warns against: *"a required check that corrupts the developer
environment is worse than no check."* `config/config.yaml` is `.gitignore`d so
this session's corruption didn't taint git history, but the app's own runtime
config was destroyed 3/3 times, and the same would happen against any real
config file on a self-hosted CI runner's persistent checkout.

Filed as **#13083** (bucket A: genuine defect, highest-priority shared-state
finding).

No other filesystem/Redis/Postgres mutation outside a tmpdir was observed:
the disposable Postgres never had a single table created in it across any run
(`\dt` empty throughout — DB-dependent tests either use SQLite/aiosqlite or
were never reached), and the shared production Redis instance's `dbsize`
(948) was unchanged before and after every run.

## Collection errors — 252 total, ~95% one root cause

| Cluster | Count | Bucket |
|---|---:|---|
| Cross-backend package collision (`api`/`services`/`user_management`/`middleware` `ModuleNotFoundError`) | 207 | systemic (see #13084) |
| Same collision, manifesting as `ImportError: cannot import name 'X' from 'X' (unknown location)` | 25 | systemic (see #13084) |
| Same collision, manifesting as `fastapi.exceptions.FastAPIError: Invalid args for response field!` (wrong backend's router module executed, response type resolves to a MagicMock stub) | 7 | systemic (see #13084) |
| `tools.lint` not importable (`repo_tests/lint/canonical/**`) | 12 | config gap (#13086) |
| Missing optional dep `cachetools` (`security/enterprise/threat_detection/test_learner.py`) | 1 | bucket B |

**Root cause of the 239/252 systemic cluster**, confirmed by isolation:
`autobot-backend/` and `autobot-slm-backend/` each define top-level packages
with identical names (`api`, `services`, `user_management`, `middleware`,
`migrations`). Running `pytest.ini`'s full `testpaths` in one interpreter
session (exactly what a required full-suite job does) makes whichever
backend's file is collected first bind that dotted name in `sys.modules` for
the **entire session**; the other backend's own test files then fail. Proof:

```
$ pytest autobot-backend/integrations/browser_tracking_test.py --collect-only -q
collected 5 items                                    # passes standalone

$ pytest --collect-only -q                            # full suite
ERROR autobot-backend/integrations/browser_tracking_test.py
E   ModuleNotFoundError: No module named 'user_management.models.base'; 'user_management.models' is not a package
```

and, even more directly, `autobot-backend/api/security_api_test.py:16` imports
`from api.security import ...` but the traceback shows **`autobot-slm-backend/api/security.py:192`**
actually executing.

Full analysis, all file:line citations, and the fix direction are in **#13084**.

## Runtime failures/errors — 2,330 failed + 660 errors, clustered

Given the volume (2,990 non-passing results), full per-test triage was not
attempted; failures were clustered by normalized error message (numbers/quoted
values collapsed) and each cluster's file:line was sampled, matching the
cluster-level triage approach the owner used earlier on this same issue
(2026-07-07 comment: "~12 systemic import/collection patterns... a
relatively small number of conftest fixes likely clears hundreds at once").

| Cluster (normalized) | Count | Bucket | Note |
|---|---:|---|---|
| `ModuleNotFoundError`/`ImportError` variants (runtime, mostly `test_startup_imports.py` parametrized dynamic imports) | ≈1,215 (800+268+147) | systemic, same root cause as collection errors | See #13084 |
| `code_intelligence/*_test.py` MagicMock-comparison family (`AssertionError: assert <MagicMock> == X`, `TypeError: object MagicMock can't be used in 'await' expression`, `TypeError not supported between instances`, etc.) | ≈230+ (76+58+38+37+37+31+29+13+11+10+7+6+5+5) | systemic — conftest stubs `code_intelligence` as MagicMock for other tests, breaking `code_intelligence`'s own tests when co-collected | See #13084 |
| `pytest.UsageError: Plugins may be specified... Got: <MagicMock ...>` (`config/test_no_logging_manager_on_init_path.py`) | 102 | systemic, same conftest-stub family, previously diagnosed by the owner on 2026-07-07 | See #13084 |
| ChromaDB-parametrized `[chromadb]` assertion failures (`knowledge/backends/test_async_base.py`, `test_base.py`) | ≈181 (49+47+45+21+9+6+4) | **bucket B** — needs a live ChromaDB instance (repo convention: port 8100); not provided by Postgres+Redis alone | Needs CI-provisioned service or explicit skip |
| `sqlalchemy.exc.ArgumentError: ... got <MagicMock>` (`autobot-slm-backend/tests/api/test_fleet_node_update_11511.py`, `main_ensure_local_node_test.py`) | 37 | needs further triage — likely same systemic family (model attrs resolving to stubs) | Not fully isolated this session |
| `playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist` (`services/redis_service_management_e2e_test.py` and others) | 10 | **bucket B** — Playwright browser binaries not installed (`playwright install chromium`); no `importorskip`/skip guard present | Needs CI step or skip |
| `TypeError: ConfigManager.__init__() got an unexpected keyword argument 'config_file'` (`security/config_security_test.py`) | 7 | **bucket C: test rot** | Filed as #13087 |
| `TypeError: Exception() takes no keyword arguments` / other `repairable_exception_test.py` failures | 14 (run2) | **bucket D: order-dependent** — same tests passed in the `--last-failed` re-run with zero code change | See flakiness section |
| Everything else (long tail, dozens of small 1-13-count clusters spanning `media/document/pipeline_test.py`, `llc/tests/test_haiku_tier.py`, `utils/distributed_service_discovery_test.py`, etc.) | remainder | mixed A/B/C, not triaged individually | Needs step-2 per-cluster pass |

**Note on the 175-count `AttributeError: module 'X' has no attribute 'X'`
cluster reported by raw normalization:** this label is heterogeneous — the
normalization collapses many *distinct* single-occurrence AttributeErrors
across unrelated modules under one bucket. A sample includes the
already-filed **#12998** (4 GitLab/Gitea connector tests patching a
module-level `_store_ts` removed by #12659) plus many other, different,
module-specific attribute errors. This cluster needs genuine per-case triage
in step 2 and is not claimed to be one root cause.

## Flakiness / order-dependence (bucket D)

A `--last-failed` re-run of exactly the 2,330 failed + 660 errored tests from
the full run flipped **56 tests from failed → passed with no code change**,
concentrated in three files:

- `autobot-slm-backend/migrations/migrate_sso_secrets_test.py` (12 of its tests)
- `autobot-backend/a2a/a2a_security_test.py` (several)
- `autobot-backend/utils/repairable_exception_test.py` (several)

This is **not** classic timing-based flakiness — the collection/worker
distribution differs between a full-suite run and a `--last-failed` subset
run, and these tests are sensitive to that ordering. This is additional
evidence for, not independent of, the #13084 namespace-pollution root cause;
no separate issue was filed for it.

## Bucket B — environment-dependent, needs CI-provisioned service or explicit skip

| Need | Affected tests | Evidence |
|---|---|---|
| Live ChromaDB (port 8100 per repo convention) | `knowledge/backends/test_async_base.py`/`test_base.py` `[chromadb]` parametrized cases | ≈181 failures, no chromadb process was running in this session's environment |
| Playwright browser binaries (`playwright install chromium`) | `services/redis_service_management_e2e_test.py` and others importing `playwright.async_api` | 10 errors: `Executable doesn't exist at .../chromium_headless_shell...` |
| `cachetools` package (not in `requirements-ci.txt`, no `importorskip` guard) | `security/enterprise/threat_detection/test_learner.py` (via `learner.py` import chain) | 1 collection error |
| Real Redis pub/sub producer / live `backend_url` fixture | not isolated individually this session — flagged qualitatively per prior #10691 comments (jwt-lifecycle, npu-redis-cache, transcripts, injection-detection) | carried over from owner's 2026-07-03 scoping, not re-verified here |

None of these were installed ad-hoc in this session, per the "no ad-hoc
installs; missing optional deps are themselves a bucket-B finding" rule.

## Recommended sequencing for steps 2-4

1. **Fix #13084 first** (cross-backend + conftest-stub namespace pollution).
   This is the single highest-leverage fix: it is directly responsible for
   ~239 of 252 collection errors, an estimated ~1,445 of the ~2,330 runtime
   failures (the `ModuleNotFoundError`/`ImportError` and `code_intelligence`
   MagicMock families combined), and all 56 order-dependent (bucket D)
   flips. Fixing it first will make every subsequent triage pass measure the
   *real* remaining failure surface instead of noise.
2. **Fix #13082 and #13083** before this suite can safely run as *any* CI job,
   advisory or required — one hangs the process forever, the other corrupts
   the working tree on every run. These are correctness/safety prerequisites,
   not scope creep.
3. **Re-measure** after 1-2 land, to get an honest post-fix failure count —
   expect it to be dramatically smaller than 2,330/660.
4. **Triage the remaining, now much smaller, failure surface** into
   fix-now vs quarantine-with-issue (owner's step 2), including the
   bucket-B items above (provision ChromaDB + Playwright as CI services, or
   mark/skip explicitly with `pytest.importorskip`/`@pytest.mark.integration`).
5. **Investigate and fix #13085** (LLC scheduler cleanup) before caring about
   wall-clock optimization — it is currently responsible for ~10 of the ~20
   minutes of measured runtime being non-deterministic tail latency.
6. **Add the job as advisory** (owner's step 3) once 1-2 are fixed, to get a
   real, trustworthy wall-clock measurement on the actual self-hosted runner
   (this session's ~20 minutes was measured on a dev workstation with 22
   cores; the singleton runner's core count and load profile may differ
   materially).
7. **Flip to required** (owner's step 4) only once the advisory run has been
   green for a representative number of PRs and the runtime is judged
   acceptable against the "serializes against every other required check on a
   singleton runner" constraint.

## Issues filed this session

| Issue | Bucket | Severity | Summary |
|---|---|---|---|
| [#13082](https://github.com/mrveiss/AutoBot-AI/issues/13082) | A | Critical | `skills/db.py` self-deadlock (non-reentrant lock re-entered) — hangs the full suite forever until deselected |
| [#13083](https://github.com/mrveiss/AutoBot-AI/issues/13083) | A | Critical | `thread_safety_test.py::test_concurrent_config_saves` corrupts the real `config/config.yaml` every run |
| [#13084](https://github.com/mrveiss/AutoBot-AI/issues/13084) | A (systemic) | High | Cross-backend + conftest-stub namespace pollution — ~95% of collection errors, ~1,445 runtime failures, all 56 order-dependent flips |
| [#13085](https://github.com/mrveiss/AutoBot-AI/issues/13085) | A | Medium | LLC background schedulers (BudgetWatchdog/LivenessMonitor/CommunityClusterer) not cancelled cleanly — ~10 min trailing wall-clock |
| [#13086](https://github.com/mrveiss/AutoBot-AI/issues/13086) | A (config gap) | Low | `repo_tests/lint/canonical/**` can't import `tools.lint` — 12 collection errors |
| [#13087](https://github.com/mrveiss/AutoBot-AI/issues/13087) | C | Low | `config_security_test.py` calls `ConfigManager(config_file=...)`, kwarg renamed to `config_dir` — 7 failures |

Already-filed issues from prior sessions, not re-filed (per task instructions):
#13051, #13052, #13057, #13072, #13073, #13074, #13078, #13079, #12993,
#12998, #13004, #13005.
