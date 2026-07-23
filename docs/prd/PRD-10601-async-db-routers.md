# PRD: Async DB Routers and Sessions (#10601, subtask 5.1)

**Status:** Draft for owner review — planning only, no implementation
**Issue:** #10601 (Task 5 — Runtime & hardware efficiency), umbrella #10603
**Author:** mrveiss
**Scope owner sign-off required before any code lands (see Open questions).**

## 1. Summary and problem

Issue #10601 subtask 5.1 asks to "move sync psycopg2 DB off async paths" so that
request handlers stop blocking the event loop on synchronous database I/O. The
original ask named two routers (`routers/code_completion.py`,
`routers/model_management.py`).

Current-state investigation shows the situation has already improved
substantially, and the residual work is smaller and more precise than a
"make the whole DB layer async" refactor:

- The canonical database layer in **both** backends is already fully async
  (`create_async_engine` + `async_sessionmaker`), with the #10491 WSL
  stale-pool safeguard (`pool_pre_ping=True` bounded by
  `connect_args={"timeout": 10, "command_timeout": 10}`).
- The two routers named in 5.1 were **already migrated** to the async
  `db_session_context()` under #10570 and now use `await db.execute(...)`.
- The remaining event-loop-blocking sync DB access is **concentrated in one
  router**: `autobot-backend/routers/feedback.py`. Four `async def` endpoints
  call synchronous, blocking `FeedbackTracker` methods (which open a sync
  `SessionLocal` session) directly on the event loop, with no
  `asyncio.to_thread` offload.

**Risk profile.** This is a *bounded* refactor, not the high-blast-radius
"rewrite the DB layer" the issue framing implies. The genuine risk is the
well-known repo failure mode: a sync→async migration that leaves an un-awaited
caller (a coroutine created but never awaited, or a blocking call left inline).
The surface area is one service class (`FeedbackTracker`) and its one caller
module (`routers/feedback.py`), plus their tests.

## 2. Goals and non-goals

### Goals

- G1 — No `async def` request handler performs synchronous, blocking database
  I/O on the event loop. The four `feedback.py` endpoints must either `await`
  an async DB path or offload the sync path via `asyncio.to_thread`.
- G2 — Preserve the single canonical async engine/pool (#10570) — no new engine,
  no second connection pool, no reintroduced ad-hoc `create_engine`.
- G3 — Keep the #10491 pool safety semantics (pre_ping bounded by
  `command_timeout`) intact on every path that touches Postgres.
- G4 — Zero behavioural/API regression: identical request/response contracts,
  identical commit/rollback semantics.
- G5 — Every phase independently mergeable with its own verification gate.

### Non-goals (explicit, to bound blast radius)

- N1 — The other #10601 subtasks (5.2 HTTP session pooling, 5.3 OpenVINO
  CACHE_DIR, 5.4 per-worker model dedup, 5.5 NPU telemetry, 5.6 sync ChromaDB
  cache, 5.7 retry_after, 5.8 batch path). Each is its own PRD/PR.
- N2 — Migration scripts (`autobot-slm-backend/migrations/**`,
  `autobot-backend/migrations/**`). These use psycopg2 **intentionally**, run
  outside the event loop, and must stay sync (Alembic/psycopg2 semantics).
- N3 — Standalone admin/CLI scripts (`scripts/autobot-admin.py`,
  `scripts/encrypt_sso_secrets.py`) — sync, not on any event loop.
- N4 — Legitimately-threaded sync DB users that already route through the
  canonical engine's `.sync_engine` and never run on the loop:
  `training/data_loader.py` (torch DataLoader worker threads),
  `services/incremental_trainer.py` (BackgroundTasks), and
  `routers/model_management.py::_get_sync_session` (BackgroundTasks thread).
  These are correct as-is; touching them adds risk with no benefit.
- N5 — Schema changes of any kind. No new tables, no drops, no column changes.
- N6 — The SLM control-plane backend — already fully async; no change needed.

## 3. Current-state analysis (file:line evidence)

### 3.1 Canonical async DB layer already exists (both backends)

- `autobot-backend/user_management/database.py:77-89` —
  `create_async_engine(config.postgres_url, ... pool_pre_ping=True,
  connect_args={"timeout": 10, "command_timeout": 10})` (the #10491 fix).
- `autobot-backend/user_management/database.py:102-121` —
  `get_async_session_factory()` returns an `async_sessionmaker[AsyncSession]`.
- `autobot-backend/user_management/database.py:148-169` —
  `db_session_context()` async context manager: commit-on-exit, rollback-on-error,
  post-commit callbacks, guaranteed `await session.close()`.
- `autobot-slm-backend/user_management/database.py:71-119` — two canonical async
  engines (`get_slm_engine`, `get_autobot_engine`), same #10491 safeguards.
- `autobot-slm-backend/user_management/database.py:125-183` — async session
  makers/sessions; `db_session_context = get_slm_session` alias at line 221.
- `autobot-slm-backend/services/database.py:62` — async_sessionmaker (SLM fully async).

### 3.2 The two routers from 5.1 are already async (#10570 — closed)

- `autobot-backend/routers/code_completion.py:22` imports `db_session_context`;
  `:111` `async with db_session_context() as db:`; `:116, 187, 194, 265, 270,
  299-309` all use `await db.execute(...)`.
- `autobot-backend/routers/model_management.py:19-23, 232-335` — endpoints use
  `await db.execute(...)`. The only sync path is `_get_sync_session()` at
  `:36-56`, deliberately for the `BackgroundTasks` training thread, derived from
  `get_async_engine().sync_engine` (one shared pool, not a second engine).

### 3.3 Residual event-loop-blocking sync DB (the real 5.1 work)

`autobot-backend/routers/feedback.py` — endpoints are `async def` but call
**synchronous, blocking** `FeedbackTracker` methods directly (no `to_thread`):

- `feedback.py:133-154` — `async def record_feedback` → line 154
  `_get_feedback_tracker().record_feedback(...)`.
- `feedback.py:182-200` — `async def get_acceptance_metrics` → line 200
  `_get_feedback_tracker().get_acceptance_metrics(...)`.
- `feedback.py:213-234` — `async def get_recent_feedback` → line 234
  `_get_feedback_tracker().get_recent_feedback(...)`.
- `feedback.py:300-311` — `async def get_feedback_statistics` → lines 310-311
  `_get_feedback_tracker().get_acceptance_metrics(...)` (x2).

The called methods are synchronous and open a blocking sync session:

- `autobot-backend/services/feedback_tracker.py:41-42` — sync
  `sessionmaker(bind=get_async_engine().sync_engine)` (routes through canonical
  pool — good — but is still a **blocking** driver).
- `autobot-backend/services/feedback_tracker.py:52-65` — `def record_feedback(...)`
  (sync) → `with self.SessionLocal() as db:` blocking I/O on the event loop.
  Same blocking pattern at `:155, 245, 283`.
- Sync lifecycle wrapper: `autobot_shared/db_session.py:19-43` `session_scope()`.

Every request to these four endpoints stalls the shared uvicorn worker's event
loop for the duration of the DB round-trip. Under load (the issue's verification
step is "load test the two routers — event loop no longer stalls") this
serialises otherwise-concurrent requests on that worker.

### 3.4 Correctly-sync paths that must NOT change (non-goals confirmed)

- `autobot-backend/training/data_loader.py:104-122` — sync sessions inside torch
  `DataLoader` worker threads (comment at `:104`).
- `autobot-backend/services/incremental_trainer.py:58-59, 163` — sync sessions,
  called only from `BackgroundTasks` (`feedback.py:271-283`, wrapped in
  `background_tasks.add_task(_run_training)` at the endpoint — off the loop).
- `autobot-backend/routers/model_management.py:36-56` — `_get_sync_session` for
  the training thread.
- `autobot-slm-backend/migrations/**`, `autobot-backend/migrations/**`,
  `scripts/autobot-admin.py`, `scripts/encrypt_sso_secrets.py` — sync psycopg2,
  intentional, outside the loop.

## 4. Proposed design

**Target:** no `async def` handler blocks the loop on DB I/O; keep exactly one
canonical async engine/pool.

Two viable strategies for the `feedback.py` + `FeedbackTracker` seam:

### Option A (preferred) — native async `FeedbackTracker`

Add async methods to `FeedbackTracker` that use `db_session_context()` +
`await db.execute(...)`, mirroring what #10570 did for the other two routers.
The four endpoints then `await` them.

- Pros: consistent with the established #10570 pattern; releases the loop during
  the actual DB round-trip; single async path end-to-end.
- Cons: larger diff in `FeedbackTracker` (each method's ORM calls become async);
  the sync methods must stay for the `BackgroundTasks`/thread callers
  (`mark_retrain_completed`, retrain path) — so the class ends up with both a
  sync and an async surface, which must be named and documented clearly (no
  `_v2`/duplicate-name smell — use intent-revealing names like
  `record_feedback` async vs a clearly-scoped sync helper, or split responsibilities).

### Option B (smaller, lower-risk) — `asyncio.to_thread` offload

Keep `FeedbackTracker` sync; in the four endpoints wrap the calls:
`feedback = await asyncio.to_thread(_get_feedback_tracker().record_feedback, ...)`.

- Pros: minimal diff; the sync method (already used by threads/bg-tasks) is
  unchanged and reused verbatim; the blocking work moves to the default thread
  pool, freeing the loop.
- Cons: thread-pool sizing (`anyio` default 40 tokens) becomes a shared
  resource; a burst of feedback writes competes with other `to_thread` users.
  For a low-QPS learning-loop endpoint this is acceptable.

**Recommendation:** Option B for the first, shippable fix (fastest to prove and
lowest blast radius), with Option A as an optional follow-up if load testing
shows thread-pool contention. Owner to confirm (Open question OQ-1).

### Avoiding the un-awaited-caller failure mode

This repo has repeatedly been bitten by sync→async migrations that leave a
coroutine un-awaited or a blocking call inline. Guardrails baked into the plan:

- Enable `asyncio` debug mode / rely on the "coroutine was never awaited"
  RuntimeWarning in tests (treat as error).
- Grep gate after each phase: no `async def` endpoint in `routers/feedback.py`
  invokes a known-sync `FeedbackTracker` method without `await`
  (`await asyncio.to_thread(` for Option B, or `await tracker.<method>(` for A).
- Run `vue-tsc`-equivalent for Python: `mypy`/`ruff` async-lint plus the
  conftest real-load test (Section 6) so the endpoint is exercised for real,
  not against a stub that would hide an un-awaited coroutine.
- No `# type: ignore` or swallowed exceptions to paper over an await mismatch.

## 5. Phased rollout plan (each phase = one PR, lowest-risk first)

Every PR bases on `Dev_new_gui`, no schema change, `Refs #10601`.

### Phase 0 — Characterisation test (no behaviour change)

- Add a load/latency regression test that hits `POST /feedback/` concurrently
  and asserts the event loop is not serialised (e.g. N concurrent requests
  complete in ~1x DB round-trip wall-clock, not Nx). Record the *current*
  (blocking) baseline so the fix is provable.
- **Gate:** test runs green and demonstrably captures the pre-fix blocking
  behaviour (baseline numbers checked in).

### Phase 1 — Unblock the write path (`record_feedback`)

- Apply the chosen strategy (Option B: `await asyncio.to_thread(...)`) to
  `feedback.py:154`. Sole highest-value endpoint (write path).
- **Gate:** Phase 0 test flips from serialised→concurrent; feedback record
  round-trips unchanged (same `FeedbackResponse`); commit/rollback verified via
  a forced-error test.

### Phase 2 — Unblock the read paths

- Apply the same treatment to `get_acceptance_metrics` (`:200`),
  `get_recent_feedback` (`:234`), and `get_feedback_statistics` (`:310-311`).
- **Gate:** each endpoint returns byte-identical payloads vs baseline snapshots;
  concurrency test green for all four.

### Phase 3 (optional, owner-gated) — native async `FeedbackTracker`

- Only if Phase 1/2 load tests show thread-pool contention. Convert the
  `FeedbackTracker` read/write methods to async via `db_session_context()`,
  keeping the sync methods for thread/bg-task callers.
- **Gate:** async and sync surfaces both covered; real-load conftest test green;
  no "coroutine never awaited" warnings.

### DB-safety note (applies to every phase)

No migrations, no schema drops, no column changes are in scope. The repo rule
holds: **orphaned schema is harmless; drop-migrations are the risk.** This work
touches only the *access pattern*, never the schema — so there is no data-loss
vector. Rollback of any phase is a pure code revert (no forward migration to
undo).

## 6. Testing strategy

- **Concurrency/latency proof (primary):** the Phase 0 test — fire M concurrent
  requests at each endpoint; assert aggregate wall-clock ≈ single round-trip,
  not M sequential round-trips. This is the direct evidence for the issue's
  "event loop no longer stalls" acceptance criterion.
- **Contract snapshots:** capture response bodies for all four endpoints before
  the change; assert equality after each phase.
- **Commit/rollback semantics:** inject a DB error mid-write; assert rollback and
  that no partial `CompletionFeedback` row persists (mirrors
  `session_scope`/`db_session_context` guarantees).
- **Real-load conftest pattern:** use the repo's conftest real-load approach
  (un-stub the light `feedback_tracker`/`feedback` modules inline after their
  stubs, or via `pytest_configure` for late-stubbed deps) so the endpoint is
  exercised against the real code path — this is what surfaces an un-awaited
  coroutine or a still-blocking call that a mocked DB would hide.
- **Async lint gate:** run tests with `PYTHONASYNCIODEBUG=1`; treat
  "coroutine was never awaited" as a failure.
- **Regression sweep:** existing `feedback_tracker_test.py` must stay green
  (its `@patch("services.feedback_tracker.create_engine")` mocks confirm the
  sync path — extend, don't delete).

## 7. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Un-awaited coroutine left after migration (repo's known failure mode) | Med | `PYTHONASYNCIODEBUG=1` in CI, grep gate per phase, real-load conftest test (not stubs) |
| Thread-pool (anyio ~40 tokens) contention under `to_thread` burst | Low | Endpoint is low-QPS learning loop; Phase 3 Option A escape hatch if load test shows contention |
| Reintroducing a second engine/pool | Low | Reuse `db_session_context()`/`get_async_engine().sync_engine` only; grep `create_engine(` in review; #10570 lint marker `# canonical: ignore py-adhoc-db-engine` remains the only sanctioned sync bind |
| WSL stale-pool 30s hang (#10491) on any new path | Low | No new engine created → inherits `pool_pre_ping` bounded by `command_timeout=10`; verify the sync `.sync_engine` path also carries the bounded timeout (Open question OQ-3) |
| Behavioural regression in response contract | Low | Byte-identical snapshot tests per phase |
| Blast radius creep into non-goal sync users | Low | N2–N4 explicitly frozen; PRs limited to `feedback.py` + `feedback_tracker.py` + tests |

**Rollback:** each phase is a self-contained code revert. No schema state to
reconcile, no data migration to reverse.

## 8. Open questions for the owner

- **OQ-1 (strategy):** Ship the low-risk `asyncio.to_thread` offload (Option B)
  first and only do the native-async `FeedbackTracker` rewrite (Option A) if a
  load test proves thread-pool contention? Or go straight to native async for
  end-to-end consistency with #10570?
- **OQ-2 (issue scoping):** Subtask 5.1's two named routers
  (`code_completion.py`, `model_management.py`) are already async via #10570.
  Should 5.1 be re-scoped to `routers/feedback.py` (the real remaining offender),
  and should the umbrella checklist be updated to reflect that?
- **OQ-3 (pool safety on sync path):** The sync `sessionmaker` binds to
  `get_async_engine().sync_engine`. Does the sync engine wrapper inherit the
  #10491 `command_timeout=10` bound on `pre_ping`, or is a
  `to_thread`-offloaded blocking call still exposed to a ~30s WSL stale-socket
  hang? Confirm before relying on Option B under WSL.
- **OQ-4 (verification bar):** What concurrency factor / latency threshold
  should the Phase 0 load test assert as the pass/fail gate for "event loop no
  longer stalls"?
