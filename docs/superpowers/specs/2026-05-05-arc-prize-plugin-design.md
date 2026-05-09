# ARC Prize Plugin — Design Spec

**Date:** 2026-05-05
**Author:** mrveiss
**Status:** Draft (pending review)
**Related:** ARC Prize 2025 (<https://arcprize.org>), ARC-AGI-1 (<https://github.com/fchollet/ARC-AGI>), ARC-AGI-2 (<https://github.com/arcprize/ARC-AGI-2>)

**Discovery dependencies (filed during this design):**

- **#6970** plugin-sdk: extension-point hooks have no host-side dispatch sites — **HARD BLOCKER for the plan**
- **#6971** plugin-sdk: declarative `required_env` field on `PluginManifest` — needed for the API-key UX in Section "Configuration"
- **#6972** plugin-sdk: standardized frontend-module mounting (replace symlink hack) — needed for the frontend layout in Section "Frontend Architecture"
- **#6973** types: consolidate 15+ `*Status` enums — `Run.status` and `SolverExecution.status` should target the canonical `JobStatus` once it exists
- **#6486** (existing) event-bus consolidation — ARC progress publisher should publish through whichever bus #6486 settles on, not invent a new pubsub channel

---

## Problem Statement

AutoBot has no surface for benchmarking its reasoning stack against the public ARC-AGI benchmark, the standard published yardstick for visual abstract reasoning. Without one, claims about AutoBot's reasoning capability are unmeasured. We need a plugin that:

1. Loads ARC-AGI tasks from the official sources
2. Runs AutoBot agents (and other solvers) against those tasks
3. Scores results with the canonical ARC scoring rule (exact-match)
4. Records run history for trend analysis
5. Surfaces a UI capable of visualizing tasks, runs, and per-task drill-down

The plugin is intentionally scoped narrowly: it is a **benchmark harness**, not a solver-research lab, not a synthetic-data generator, not a public-facing showcase. Those three ride on top of this harness and are tracked as separate follow-up efforts (see "Out of Scope" below).

The ARC Prize itself is a phased target: Phase 1 ships the harness with optional API-key configuration and dataset-via-official-API; Phases 2 and 3 add leaderboard submission and team management as separate specs.

---

## Goals

- Score AutoBot's existing agents against ARC-AGI-1 and ARC-AGI-2 with reproducible runs.
- Provide a solver abstraction (`ARCSolver` Protocol) that future solvers — DSL synthesis, program search, neuro-symbolic — can plug into without changing the harness.
- Render tasks and predictions as canvas-rendered grids using the standard ARC palette so wrong predictions are debuggable visually.
- Persist runs, executions, and predicted grids in SQLite; stream live progress over Redis pubsub; preserve reproducibility across upstream dataset corrections.
- Lay architectural foundations (config UX, dataset-source switching, solver metadata) for Phase 2 (leaderboard submission) and Phase 3 (team management) without building them.

## Non-Goals

- Becoming a general benchmark framework. ARC-AGI only.
- Replacing AutoBot's existing agent / LLM machinery. The plugin is a *consumer*, never a substitute.
- Persisting full LLM reasoning traces. Truncated traces live on `metadata`; full traces go to AutoBot's existing observability stack.
- Submitting results to the official ARC Prize leaderboard (deferred to Phase 2).
- Team / org / attribution management (deferred to Phase 3).
- Generating synthetic ARC-style tasks (out of scope entirely; tracked under the umbrella's "C" subsystem).
- Public marketing surface / anonymous run sandbox (umbrella's "D" subsystem).

---

## Plugin Layout

```text
plugins/core-plugins/arc-prize-plugin/
├── plugin.json                 # manifest (extended with required_env)
├── main.py                     # ARCPrizePlugin(BasePlugin) — registers router, solvers, Celery tasks
├── README.md
├── data/                       # gitignored; populated by scripts/download_datasets.py
│   └── arc/{v1,v2}/{train,eval}/*.json
├── scripts/
│   └── download_datasets.py    # idempotent fetch from fchollet/ARC-AGI + arcprize/ARC-AGI-2
├── backend/
│   ├── api.py                  # FastAPI router mounted at /api/arc
│   ├── models.py               # SQLAlchemy: Run, SolverExecution, ARCPromptTemplate
│   ├── schemas.py              # Pydantic request/response (domain-local; NOT in schemas_common.py)
│   ├── dataset.py              # ARCTask loader, grid validators, source switching
│   ├── scoring.py              # exact-match scorer (canonical ARC rule)
│   ├── solvers/
│   │   ├── base.py             # ARCSolver Protocol + ARCSolution dataclass + auto-discovery
│   │   ├── llm_solver.py       # wraps autobot agent + prompt template
│   │   └── baseline_solver.py  # identity, most-common-color, first-train-output (sanity)
│   ├── tasks.py                # Celery tasks: dispatch_run, run_solver_on_task, finalize_run
│   └── progress.py             # Redis pubsub publisher (channel: arc:run:{run_id})
├── frontend/                   # symlinked into autobot-frontend/src/plugins/arc/
│   ├── views/
│   │   ├── ARCTasksView.vue
│   │   ├── ARCRunView.vue
│   │   ├── ARCRunDetailView.vue
│   │   ├── ARCLeaderboardView.vue
│   │   └── ARCSettingsView.vue
│   ├── components/
│   │   ├── ARCGrid.vue                  # canvas-rendered, ARC palette
│   │   ├── ARCGridTriple.vue            # input | expected | predicted side-by-side
│   │   ├── ARCSolverPicker.vue
│   │   ├── ARCDatasetPicker.vue
│   │   ├── ARCTaskFilterBuilder.vue
│   │   ├── ARCRunProgressBar.vue
│   │   └── ARCPromptTemplateEditor.vue
│   ├── stores/arc.ts                    # pinia
│   ├── api/arcClient.ts                 # typed wrappers around /api/arc/* via useApi()
│   ├── composables/useARCRunStream.ts   # wraps EventSource for /runs/:id/stream
│   └── router.ts                        # adds /arc routes; nav entry registered manually in App.vue
└── tests/
    ├── test_scoring.py
    ├── test_dataset_loader.py
    ├── test_solvers.py
    ├── test_api.py
    ├── test_run_lifecycle.py
    └── test_cancel_propagation.py
```

**Manifest highlights** (`plugin.json`):

```json
{
  "name": "arc-prize",
  "version": "0.1.0",
  "display_name": "ARC Prize",
  "description": "Benchmark AutoBot solvers against ARC-AGI-1 and ARC-AGI-2.",
  "author": "mrveiss",
  "entry_point": "plugins.core_plugins.arc_prize_plugin.main",
  "dependencies": [],
  "hooks": ["api_router_register", "frontend_route_register", "celery_task_register"],
  "config_schema": {
    "type": "object",
    "properties": {
      "dataset_source": {
        "type": "string",
        "enum": ["github_mirror", "official_api", "auto"],
        "default": "auto"
      },
      "default_concurrency_per_solver": {
        "type": "integer",
        "default": 4,
        "description": "Per-solver_class cap on concurrently executing run_solver_on_task Celery tasks. Prevents one slow solver from saturating the worker pool."
      }
    }
  },
  "required_env": [
    {
      "name": "ARC_PRIZE_API_KEY",
      "secret": true,
      "required": false,
      "description": "ARC Prize API key. Plugin works without it (uses public GitHub mirrors); enables official-API access.",
      "docs_url": "https://docs.arcprize.org/api-keys",
      "obtain_steps": [
        "Sign in at arcprize.org",
        "Visit Settings → API Keys",
        "Generate a 'data-access' scope key"
      ]
    }
  ]
}
```

The `required_env` field is **new** to the plugin SDK. Tracked as **#6971**. Phase 1's plan must decide: (a) wait for #6971 to land, (b) bundle the SDK change into the ARC PR, or (c) hardcode env-var reads in `arc-prize-plugin/main.py` and migrate later. Field is opt-in for other plugins; nothing breaks if they don't use it.

---

## Data Model

### SQLite (relational, persistent)

Domain lives under `autobot-backend/database/arc_prize/` (matches existing domain organization; per #5799 we do not add to `schemas_common.py`).

```python
class Run(Base):
    id: UUID                    # primary key
    dataset_id: Enum["arc_v1_train", "arc_v1_eval", "arc_v2_train", "arc_v2_eval"]
    task_filter: JSON           # {"task_ids": [...]} | {"limit": N} | {"all": true}
    solver_configs: JSON        # [{"solver_class": "LLMSolver", "params": {...}}, ...]
    status: Enum["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime
    completed_at: datetime | None
    submitted_by: str           # user_id from auth
    total_executions: int       # = len(tasks) * len(solvers); set on submission

class SolverExecution(Base):
    id: UUID
    run_id: UUID                # FK Run.id
    task_id: str                # ARC task UUID-like string
    solver_class: str           # "LLMSolver", "BaselineSolver"
    solver_params: JSON         # frozen snapshot of params used
    status: Enum["pending", "running", "succeeded", "failed", "timeout", "cancelled"]
    predicted_grid: JSON | None # 2D int array
    expected_grid: JSON         # 2D int array (frozen at execution time)
    correct: bool | None        # exact-match result; null on failed/timeout/cancelled
    latency_ms: int | None
    error: str | None           # exception message if status=failed
    metadata: JSON              # solver-specific: tokens_used, agent_id, prompt_hash, raw_response
    started_at: datetime | None
    completed_at: datetime | None

    # indices: (run_id, status), (solver_class, correct), (task_id, correct)

class ARCPromptTemplate(Base):
    id: UUID                    # primary key
    name: str                   # human-readable identifier
    version: int                # 1, 2, 3...
    body: str                   # template text
    created_at: datetime
    created_by: str

    # constraint: UNIQUE(name, version) — versions are immutable once written
```

**Versioning rule:** prompt templates are immutable per version. UI edits create `version=N+1`. `solver_configs` references `{"prompt_template_id": "<uuid>"}` pinning a specific version. This eliminates duplication while preserving Run reproducibility.

**Why `expected_grid` is duplicated on every execution:** the dataset files can be corrected upstream after a Run completes (especially `arcprize/ARC-AGI-2`). Freezing `expected_grid` at execution time keeps historic Run scores stable against the data they actually saw.

**No `Solver` registry table.** Solver classes are discovered in-process via the `ARCSolver` Protocol. `solver_configs` snapshots the exact params used. A "saved solver presets" feature can be added later if it's ever needed.

### Redis (transient)

| Key / Channel | Purpose |
| --- | --- |
| `arc:run:{run_id}` (pubsub channel) | Live execution-completed events for SSE consumers |
| `arc:run:{run_id}:cancel` (key, TTL 1d) | Set to `1` when user cancels; tasks check before running |

No long-lived state in Redis. All authoritative state is in SQLite.

### Filesystem (immutable)

`data/arc/{v1,v2}/{train,eval}/*.json` — task files from official mirrors, fetched by `download_datasets.py`. Loader caches parsed tasks in-process at plugin `initialize()` time (~2000 small JSON files = a few MB; trivial).

---

## Solver Contract

```python
# backend/solvers/base.py

from typing import Protocol, runtime_checkable
from dataclasses import dataclass

Grid = list[list[int]]   # 2D int array, values 0-9 per ARC palette

@dataclass(frozen=True)
class ARCTask:
    task_id: str
    train_pairs: list[tuple[Grid, Grid]]   # demonstration examples
    test_input: Grid                        # input to predict for
    test_output: Grid                       # ground truth — held by harness, NEVER passed to solver

@dataclass(frozen=True)
class ARCSolution:
    predicted_grid: Grid
    metadata: dict   # solver-specific: tokens_used, model, latency_breakdown, reasoning_trace

@runtime_checkable
class ARCSolver(Protocol):
    name: str   # class-level identifier, e.g., "LLMSolver"

    async def solve(self, task: ARCTask, *, timeout_s: float) -> ARCSolution: ...
```

**Three rules baked into the contract:**

1. `test_output` is never passed to `solve()`. Prevents accidental ground-truth leakage. Harness compares the returned `predicted_grid` against the held-out value.
2. `solve()` must respect `timeout_s` cooperatively. Outer `asyncio.wait_for(solver.solve(...), timeout=timeout_s + 5)` is the safety net.
3. `metadata` is opaque. Harness writes it through to `SolverExecution.metadata` verbatim; UI surfaces it in result drill-down.

**Reference implementations shipped Phase 1:**

- `BaselineSolver(strategy="identity" | "most_common_color" | "first_train_output")` — pure Python, <1ms per task. Sanity check; if it scores >0% on ARC-AGI-2, the dataset has trivial tasks and we want to know.
- `LLMSolver(agent_id, prompt_template_id, temperature, max_tokens)` — renders task using template, calls `LLMService` via the named agent, parses reply via tolerant grid-parser (JSON arrays, ASCII grids, fenced code blocks). Records `tokens_used`, `agent_id`, `model`, `raw_response` on `metadata`.

**Discovery, not registration.** Solvers are auto-discovered by walking `backend/solvers/` and finding classes that satisfy the `ARCSolver` Protocol. Adding a new solver is "drop a file." No central registry to update.

---

## API Surface

All routes mounted at `/api/arc`. Auth: existing AutoBot JWT middleware. No new auth surface.

### Datasets & tasks (read-only)

```text
GET    /api/arc/datasets                          → list available datasets + counts
GET    /api/arc/datasets/{dataset_id}/tasks       → paginated task summaries (id, dims, split)
GET    /api/arc/tasks/{task_id}                   → full task (train pairs + test input only;
                                                    test output omitted unless ?include_solution=true
                                                    + admin role)
```

### Solvers (read-only)

```text
GET    /api/arc/solvers                           → discovered ARCSolver classes + param schemas
```

### Prompt templates (CRUD, versioned-immutable)

```text
GET    /api/arc/prompt-templates                  → list (name + latest version)
GET    /api/arc/prompt-templates/{name}/versions  → all versions of one named template
POST   /api/arc/prompt-templates                  → create v1 (name, body)
POST   /api/arc/prompt-templates/{name}/versions  → create vN+1 (body)
                                                    NOTE: no PUT, no DELETE — immutable
```

### Runs

```text
POST   /api/arc/runs                              → submit; returns 202 + {run_id}
                                                    body: {dataset_id, task_filter, solver_configs}
GET    /api/arc/runs                              → paginated runs (filter by status/dataset/user)
GET    /api/arc/runs/{run_id}                     → run summary + aggregate score per solver
GET    /api/arc/runs/{run_id}/executions          → paginated SolverExecution rows
GET    /api/arc/runs/{run_id}/executions/{exec_id} → single execution incl. predicted_grid + metadata
POST   /api/arc/runs/{run_id}/cancel              → sets cancel flag in Redis
GET    /api/arc/runs/{run_id}/stream              → SSE; Redis pubsub channel arc:run:{run_id}
```

### Leaderboard

```text
GET    /api/arc/leaderboard?dataset_id=...        → aggregate scores per (solver_class, params hash)
                                                    across completed runs on a dataset
```

### Plugin status

```text
GET    /api/arc/plugin/status                     → {api_key_configured: bool,
                                                     dataset_source_active: "github_mirror"|"official_api",
                                                     official_api_reachable: bool|null}
```

**Schemas live in:** `plugins/core-plugins/arc-prize-plugin/backend/schemas.py` — domain-local. Per #5799, no additions to `schemas_common.py`. Response wrappers use existing `DataResponse[T]` from `autobot_shared`.

**Deliberate omissions:** no `DELETE /runs/{id}` (runs are append-only history); no `PUT /runs/{id}` (immutable post-submission); no standalone `/api/arc/score` endpoint (harness owns scoring; exposing it standalone invites uses out of scope for Phase 1).

### Rate limits (system protection)

- `total_executions ≤ 10,000` per submitted run, enforced at submit time.
- Max 5 concurrent active runs per user.
- No budget tracking. AutoBot uses local LLMs by default. **Budget-aware admission** for cloud-LLM solvers is filed as a separate follow-up issue, blocked on the cost-tracker SSOT being stable.

---

## Run Lifecycle

```text
1. Submit
   └─ POST /api/arc/runs { dataset_id, task_filter, solver_configs }
   └─ Validate: dataset exists, prompt_template_ids exist, total_executions ≤ 10,000,
              user has < 5 active runs, every solver_class is discoverable
   └─ Insert Run row (status=pending, total_executions=N×M)
   └─ Insert N×M SolverExecution rows (status=pending)
   └─ Enqueue Celery: dispatch_run.delay(run_id)
   └─ Return 202 + { run_id }

2. Dispatch (Celery: dispatch_run)
   └─ Mark Run.status=running, started_at=now
   └─ For each pending SolverExecution: enqueue run_solver_on_task.delay(execution_id)
   └─ Enqueue finalize_run.apply_async(args=[run_id], countdown=30)  # watchdog
   └─ Publish to arc:run:{run_id}: {"event": "run_started", "total": N*M}

3. Per-execution (Celery: run_solver_on_task; parallelizable)
   └─ Load SolverExecution; bail if status != pending  (idempotent re-entry guard)
   └─ Check Redis arc:run:{run_id}:cancel → if set, mark cancelled, publish, return
   └─ Mark execution status=running, started_at=now
   └─ Load ARCTask via dataset loader (cached in-process)
   └─ Instantiate solver_class with frozen solver_params
   └─ try:
        solution = await asyncio.wait_for(solver.solve(task, timeout_s=120), timeout=125)
        correct = (solution.predicted_grid == task.test_output)
        update execution: status=succeeded, predicted_grid, correct, latency_ms, metadata
      except asyncio.TimeoutError:
        update: status=timeout, latency_ms=elapsed
      except Exception as e:
        update: status=failed, error=str(e)
   └─ Publish to arc:run:{run_id}: {"event": "execution_completed", "execution_id": ..., "correct": ...}

4. Finalize (Celery: finalize_run; idempotent; polled)
   └─ Count remaining {pending, running} executions for the run
   └─ If > 0: re-enqueue self with countdown=30s
   └─ If = 0:
      └─ Update Run.status = completed (or failed if all executions failed/cancelled)
      └─ Set completed_at=now
      └─ Publish to arc:run:{run_id}: {"event": "run_completed", "summary": {...}}
```

### Hardened-by-design properties

1. **Idempotent.** Every Celery task starts with a "load row, bail if status doesn't match expected" guard. Replays from Celery retries don't double-execute.
2. **Cancellation propagates fast.** Cancel flag is checked at the start of each per-execution task; pending executions short-circuit, in-flight ones complete (we don't kill mid-LLM-call). Worst case: one solver timeout (~120s) for in-flight executions.
3. **Solver timeout enforced two ways.** Cooperative inside `solve()`; `asyncio.wait_for` is the safety net.
4. **Finalize is poll-based, not callback-based.** Pubsub callbacks lose messages on Redis disconnect. The 30s poll cannot lose a run; after finalize succeeds it stops re-enqueueing itself.
5. **Frontend recovery is automatic.** Dropped SSE → reconnect to `/api/arc/runs/{id}/stream` *and* refetch `/api/arc/runs/{id}/executions`. Pubsub gives live deltas; REST gives catch-up state. Crash-safe in combination.

### Known trade-off

The `finalize_run` poll loop burns one Celery task slot every 30s for the duration of a run. For a 10,000-execution run lasting 4 hours, that's 480 wasted slots. **Mitigation if it ever matters:** use a separate Celery queue (`arc_finalize`) with its own worker. Out of scope for Phase 1; documented as a known consideration.

---

## Frontend Architecture

Three primary views + a settings view, plus shared canvas components.

```text
autobot-frontend/src/plugins/arc/   (symlinked from plugin dir on POSIX)
├── router.ts
├── stores/arc.ts
├── api/arcClient.ts
├── views/
│   ├── ARCTasksView.vue            # /arc/tasks
│   ├── ARCRunView.vue              # /arc/runs
│   ├── ARCRunDetailView.vue        # /arc/runs/:id
│   ├── ARCLeaderboardView.vue      # /arc/leaderboard
│   └── ARCSettingsView.vue         # /arc/settings (configuration / API key status)
├── components/
│   ├── ARCGrid.vue
│   ├── ARCGridTriple.vue
│   ├── ARCSolverPicker.vue
│   ├── ARCDatasetPicker.vue
│   ├── ARCTaskFilterBuilder.vue
│   ├── ARCRunProgressBar.vue
│   └── ARCPromptTemplateEditor.vue
└── composables/useARCRunStream.ts
```

### `ARCGrid.vue` (the only non-trivial component)

Canvas-rendered, ~250 LOC including tests.

- Standard ARC palette (10 colors, hardcoded — fixed contract, not configurable)
- Props: `grid: number[][]`, `cellSize?: number`, `highlightCells?: [r,c][]`, `readonly?: boolean`
- Auto-sized: `cellSize` derived from container width / grid dims, min 8px max 40px
- Optional `@click` on cells when `readonly=false` (forward-looking API; no consumer in Phase 1)
- Pixel-precise crisp rendering (`canvas.imageSmoothingEnabled = false`)
- Uses existing AutoBot design tokens for chrome (border, background, focus ring); palette only for cells
- Storybook story shipped with the component (per #4201 conventions)

### Data flow per view

| View | Loads | Live updates |
| --- | --- | --- |
| `ARCTasksView` | `GET /datasets` then `GET /datasets/{id}/tasks` | None |
| `ARCRunView` | `GET /runs` + `GET /solvers` for submission form | None |
| `ARCRunDetailView` | `GET /runs/{id}` + `GET /runs/{id}/executions` | SSE stream merged into table reactively |
| `ARCLeaderboardView` | `GET /leaderboard` | None |
| `ARCSettingsView` | `GET /plugin/status` | None |

Click a row in run detail → modal with `ARCGridTriple` (input | expected | predicted) + collapsible `metadata` blob (raw LLM reply, tokens, agent_id).

### Memory-aligned conventions

- **Nav entry registered manually in `App.vue`** (memory: "navItems in App.vue is MANUAL"). Plugin's `frontend_route_register` hook returns route definitions; App.vue's existing nav-registration consumes them.
- **All API calls go through existing `useApi()` composable** (memory: returns parsed JSON `Promise<T>`, not a Response).
- **Icons from existing Font Awesome set only** (memory: #6937 flags Heroicons as a third-icon-system anti-pattern).
- **Storybook stories from day one** for every new component (per Phase-1 Storybook restoration).

### Out of scope for frontend in Phase 1

- Manual grid-painting UI (`readonly=false` API exists; no consumer)
- Charts on leaderboard (table only)
- Cell-level diff visualization on wrong predictions
- Real-time training-pair editing
- Sharing / exporting runs

---

## Configuration & API Keys (Phase 1)

The ARC Prize API key (`ARC_PRIZE_API_KEY`) is **optional**. Without it the plugin uses the public GitHub mirrors. With it the plugin can fetch tasks via `api.arcprize.org`. Leaderboard submission and team management are explicitly **not** Phase 1.

### Where the key lives — env vars, not the database

Per AutoBot pattern (memory: `/etc/autobot/slm-secrets.env`, mode 640 root:autobot, Ansible-deployed; backend reads via pydantic-settings v2):

- **Production:** Ansible writes to `/etc/autobot/autobot-backend.env`; systemd loads it; pydantic-settings reads `ARC_PRIZE_API_KEY` at backend boot.
- **Development:** developer adds `ARC_PRIZE_API_KEY=...` to local `.env`.
- **Never in SQLite.** No plugin config row holds the secret. The DB knows whether a key is *configured* (boolean derived at runtime), never what it is.

### `ARCSettingsView` — Plugin Configuration UI

Status panel shows:

- **API key status** — configured / not configured (derived from `GET /plugin/status`)
- **How to obtain a key** — bulleted steps from the manifest's `obtain_steps`
- **Direct link to** `https://docs.arcprize.org/api-keys`
- **How to install the key** — env-file path (`/etc/autobot/autobot-backend.env` for prod, `.env` for dev) with a copy-pasteable line: `ARC_PRIZE_API_KEY=<your_key>`
- **Dataset source override** — radio: Auto / GitHub mirror / Official API
- **No "paste your key here" textbox.** A web UI writing to `/etc/autobot/*.env` is a security/ops anti-pattern in AutoBot's deployment model. The settings panel **shows status and instructions only**; the actual key install is operator-driven.

### Dataset source switching

`dataset_source: "auto"` (default) → use `official_api` when key present, else `github_mirror`. Explicit overrides exist for testing parity ("does the GitHub mirror return the same task as the official API?").

The dataset loader (`backend/dataset.py`) abstracts the source; switching is a single config read at request time, not a plugin restart.

### Status detection is derived, not stored

`GET /api/arc/plugin/status` resolves at request time:

```json
{
  "api_key_configured": true,
  "dataset_source_active": "official_api",
  "official_api_reachable": true
}
```

No staleness — every request is a fresh check. `official_api_reachable` is `null` when no key is configured (we don't probe without auth).

### README contents

`plugins/core-plugins/arc-prize-plugin/README.md`:

- One-paragraph plugin overview
- Installation: `download_datasets.py` + optional API key setup
- Configuration table: `ARC_PRIZE_API_KEY`, `dataset_source`, `default_concurrency_per_solver`
- Direct link to <https://docs.arcprize.org/api-keys>
- Direct links to <https://github.com/fchollet/ARC-AGI> and <https://github.com/arcprize/ARC-AGI-2>
- "What this plugin does NOT do yet" — pointers to filed Phase 2 + 3 issues

---

## Testing Strategy

```text
tests/
├── test_dataset_loader.py     # parses every shipped fixture without error;
│                                grids non-empty, values in [0,9], rectangular
├── test_scoring.py            # exact-match equality; rejects non-rectangular predictions;
│                                edge cases (empty, single-cell, max 30×30)
├── test_solvers.py
│   ├── BaselineSolver(identity)            scores 100% on hand-crafted identity task
│   ├── BaselineSolver(most_common_color)   returns correct uniform grid
│   ├── LLMSolver  uses mocked LLMService;  asserts prompt rendering + grid parsing
│   │                                        (NOT model behavior)
│   └── grid_parser tolerates: JSON arrays, ASCII grids, fenced code blocks, leading prose
├── test_api.py                # FastAPI TestClient; happy path per endpoint;
│                                cap-violation tests (>10k, >5 active runs)
├── test_run_lifecycle.py      # end-to-end: Celery eager + real SQLite + fakeredis;
│                                covers success, cancel, timeout, partial failure,
│                                finalize idempotency
└── test_cancel_propagation.py # cancel mid-run, verify in-flight completes,
                                 pending short-circuits, run.status=cancelled
```

**Three rules baked in (memory-aligned):**

1. **`AsyncMock` for async functions, not `MagicMock`** (memory: `patch(async_func, return_value=X)` returns MagicMock that breaks awaits).
2. **No real network in any test.** `LLMService` mocked. Dataset files are fixtures in `tests/fixtures/arc/`. Real datasets only via opt-in `@pytest.mark.integration`, CI-skipped.
3. **No mocking SQLAlchemy.** Integration tests hit a real SQLite (in-memory or temp file).

**Frontend tests (Vitest):**

- `ARCGrid.vue` — renders correct cell colors per palette index, respects `cellSize`, accessibility attrs present
- `ARCGridTriple.vue` — three grids in correct order with correct labels
- `useARCRunStream.ts` — mocked `EventSource`, reconnect behavior, message parsing
- Memory note: `vitest mockReset:true` wipes `vi.mock` factories — re-apply in `beforeEach`.

**Out of scope for tests in Phase 1:**

- E2E browser tests (Cypress) — added when frontend stabilizes
- Real-LLM solver scoring tests — flaky and slow; covered by manual smoke runs

---

## Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| LLM solver returns malformed grids → 100% scored as wrong, hides solver capability | Tolerant grid parser (JSON / ASCII / fenced code). On parse failure record `metadata.parse_error`, set `predicted_grid=null`, `correct=null`. Leaderboard distinguishes "wrong" from "unparseable". |
| Celery worker pool saturated by full-dataset run | Hard cap of 10k executions per run, 5 concurrent runs per user. Future option: separate Celery queue for ARC. |
| Dataset URL changes / upstream rename | `download_datasets.py` pinned to specific git refs of `fchollet/ARC-AGI` and `arcprize/ARC-AGI-2`; refs in plugin README. Bump deliberately. |
| Plugin frontend symlink breaks on Windows-developer checkouts | Phase 1 supports POSIX symlink only. If a Windows-developer scenario emerges, the plan adds a `frontend_module_path` resolver in the loader (symlink on POSIX, file copy on Windows). Lowest-priority risk (no Windows dev confirmed). |
| Test runtime ballooning | Real-LLM tests gated behind `@pytest.mark.integration`; CI skips by default. |
| Reproducibility drift if dataset corrected upstream | `SolverExecution.expected_grid` frozen at execution time — old runs stay scored against the data they actually saw. |
| `prompt_template` versions accumulate forever | Acceptable for Phase 1; templates are tiny. Add archive/cleanup if it ever matters. |
| API-key secret leaking via UI | Settings UI is status-only; never accepts or echoes the key. Operator installs via env file. |

---

## Phasing

| Phase | Scope | Spec |
| --- | --- | --- |
| **Phase 1 (this spec)** | Harness + solver Protocol + reference solvers + UI + key-config UX + dataset-via-official-API with GitHub-mirror fallback | This document |
| **Phase 2 (follow-up)** | Leaderboard submission to ARC Prize. Precondition: focused read of `docs.arcprize.org` to verify submission JSON format, scopes, idempotency keys, and rate limits are documented with examples. | Filed at spec-merge time |
| **Phase 3 (follow-up, depends on Phase 2)** | Team / org registration + attribution metadata on submissions | Filed at spec-merge time |

**Filed at spec-merge time:**

- `arc-prize: Phase 2 — leaderboard submission`
- `arc-prize: Phase 3 — team / org registration + attribution`
- `arc-prize: budget-aware admission check for cloud-LLM solvers`

---

## Out of Scope

Built later under separate specs (umbrella):

- **B (Solver lab)** — DSL synthesis, program search, neuro-symbolic. Slot into existing `ARCSolver` Protocol; harness already supports it.
- **C (Synthetic data generator)** — generate ARC-style tasks for training.
- **D (Public showcase)** — anonymous run sandbox, share links, marketing surface.

Out of scope for this plugin **forever**:

- General benchmark framework (ARC-AGI only)
- Replacing AutoBot's existing agent / LLM machinery

---

## Open Questions (for plan phase)

- **How does the plan handle the #6970 dependency?** The plugin needs `api_router_register`, `frontend_route_register`, `celery_task_register` extension-point hooks dispatched by the host. Three options for the plan:
  - **(a) Sequential:** wait for #6970 to land, then start ARC plan
  - **(b) Bundled:** ARC Phase 1 *includes* the #6970 work (add hook enum values + host dispatch sites + use them) — turns this into the first plugin proving the SDK contract
  - **(c) Shortcut migration:** build ARC with direct imports / manual wiring in `app.py`, migrate to hooks after #6970 lands — fastest to a runnable plugin, technical debt promised in writing
- **Does ARC bundle #6971 (required_env)?** `ARC_PRIZE_API_KEY` config UX depends on it. Same options as above (sequential / bundled / shortcut with hardcoded env-var read).
- **Should `download_datasets.py` run as part of plugin `initialize()`** (auto-fetch on first boot) or be a manual operator step? Auto-fetch is friendlier; manual is more conservative. **Default proposed: manual, documented in README.**
- **Event-bus integration (#6486 dependency):** ARC progress publisher should target the consolidated bus from #6486, but #6486 hasn't settled. Phase 1 default: publish to Redis pubsub directly (matches current `RedisEventStreamManager` pattern), migrate to the unified bus when #6486 lands.
