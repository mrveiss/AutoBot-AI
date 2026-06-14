# Codegen MANIFEST — Canonical Type Generation

How AutoBot generates frontend TypeScript types from canonical Python sources, what the codegen `MANIFEST` covers, how to extend it, and how duplicate-enum reintroduction is prevented.

> **Tracking:** #7122 (initial pipeline) · #7226 / PR [#7269](https://github.com/mrveiss/AutoBot-AI/pull/7269) (MANIFEST extension) · #6973 / #6689 (canonical enum consolidation) · #9869 (this doc)

---

## Why codegen exists

Without codegen, every backend dataclass or enum change must be mirrored by hand in the frontend type files. #7044 documented exactly this drift: the frontend `TemplateStep` interface had only 2 of 7 fields actually matching what `/api/templates` emits, and the gap survived 18 months because `v-if` defaults masked the missing fields. Codegen makes that drift impossible to introduce silently — the generated file is checked in, and CI regenerates and diffs it on every relevant change.

---

## The MANIFEST

**Source of truth:** `autobot-infrastructure/shared/scripts/gen_frontend_types.py` — the `MANIFEST` list near the top of the script.

Each entry is a tuple `(relative file path from repo root, class name)`. File paths (not module paths) are used so the script can load sources via `spec_from_file_location`, bypassing package `__init__.py` chains that would pull in heavyweight runtime deps (aiohttp, pydantic, etc.) — CI runs the script in a slim Python-only environment.

### What MANIFEST covers today

| Canonical Python source | Class | Emitted TS |
| --- | --- | --- |
| `autobot_shared/workflow/types.py` | `PromptSpec` | `interface PromptSpec` |
| `autobot_shared/workflow/types.py` | `ExecutionStrategy` | string-union `ExecutionStrategy` |
| `autobot_shared/workflow/types.py` | `WorkflowTask` | `interface WorkflowTask` |
| `autobot_shared/workflow/types.py` | `WorkflowPlan` | `interface WorkflowPlan` |
| `autobot-backend/services/workflow_automation/models.py` | `WorkflowStepStatus` | string-union `WorkflowStepStatus` |
| `autobot_shared/status_enums.py` | `Severity` | string-union `Severity` + alias `RiskLevel` |

`WorkflowStepStatus` and `RiskLevel` are the most recent additions — added by PR [#7269](https://github.com/mrveiss/AutoBot-AI/pull/7269) (closing #7226) so the canonical enum consolidations (#6973 `TaskStatus`, #6689 `Severity`/`RiskLevel`) are end-to-end: one Python definition, one generated TS union, no hand-written copy on either side.

`RiskLevel` is not a separate enum: in Python it is an alias (`RiskLevel = Severity` in `autobot_shared/status_enums.py`), and in TypeScript it is emitted via the script's `ALIASES` map as `export type RiskLevel = Severity;`.

### What MANIFEST does NOT cover

- **Pydantic models** — not supported. Convert to a `@dataclass` first, or wait for OpenAPI-based codegen (deferred).
- **API response envelopes / router schemas** — these flow through FastAPI's OpenAPI surface, not this script.
- **Frontend-only types** — anything with no canonical Python source stays hand-written in `autobot-frontend/src/types/`.
- **Enums outside the manifest** — only listed classes are generated. Canonical enums in `autobot_shared/status_enums.py` (e.g. `Priority`, `HealthStatus`, `LLMProvider`) are eligible but only emitted once added to `MANIFEST`.

Supported class kinds: `@dataclass` (→ TS `interface`) and `Enum` / `str, Enum` (→ TS string union of member *values*).

---

## Generation pipeline

```bash
# Regenerate (writes the output file)
python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py

# Check mode (used by CI) — exits non-zero on drift
python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py --check
```

**Output:** `autobot-frontend/src/types/_generated/workflow.ts` — committed to the repo so consumers import a stable path.

**Stable public import path:** `@/types/workflowTemplates` re-exports the generated types (`PromptSpec`, `WorkflowTask`, `WorkflowPlan`, `WorkflowStepStatus`, `RiskLevel`). Prefer importing from there; import from `@/types/_generated/workflow` directly only when the re-export does not expose what you need.

**Python side:** there is no generated Python — the Python types *are* the canonical source. Backend code imports them directly (e.g. `from autobot_shared.status_enums import RiskLevel`, which is the `Severity` alias re-exported via `__all__`).

### CI enforcement — `frontend-codegen-drift`

`.github/workflows/frontend-codegen-drift.yml` runs `gen_frontend_types.py --check` on every PR that touches a MANIFEST source file, the generated output, or the codegen script itself. If the committed `_generated/workflow.ts` does not match what the script produces from the current Python sources, the job fails with a `DRIFT:` message telling you to re-run the script.

Consequence: **you cannot change a manifested Python type without regenerating and committing the TS in the same PR.**

---

## How to add a new canonical enum (or dataclass)

The #7226 cookbook, as documented in the script header:

1. **Identify the canonical Python source.** For dataclasses this is a `@dataclass`; for enums a `class X(Enum):` or `class X(str, Enum):`. If duplicates exist, consolidate onto `autobot_shared` first (see [CANONICAL_RULES.md](CANONICAL_RULES.md) and the #6973/#6689 pattern) — codegen mirrors one source, it does not merge duplicates.
2. **Append `(relative_file_path, "ClassName")` to `MANIFEST`** in `gen_frontend_types.py`. The file must be loadable with only `autobot_shared/`'s parent and `autobot-backend/` on `sys.path` (avoid sources whose module-level imports need heavy runtime deps).
3. **If the TS name should differ or an alias is needed** (like `RiskLevel` → `Severity`), add it to the `ALIASES` map instead of duplicating the enum.
4. **Re-run codegen and commit the regenerated TS:**
   ```bash
   python3 autobot-infrastructure/shared/scripts/gen_frontend_types.py
   git add autobot-infrastructure/shared/scripts/gen_frontend_types.py \
           autobot-frontend/src/types/_generated/workflow.ts
   ```
5. **Update frontend imports** to consume the generated type — re-export it from `@/types/workflowTemplates` if a stable public path is preferred. Delete any hand-written duplicate union/interface it replaces.
6. **Add the new source file to the CI trigger paths** in `.github/workflows/frontend-codegen-drift.yml` (`on.pull_request.paths` and `on.push.paths`) if it lives in a file not already listed — otherwise drift in that file won't trigger the check.

---

## Preventing duplicate-enum reintroduction

Two layers stop the duplicates from creeping back in after consolidation:

1. **Pre-commit hook `no-new-status-enum` (#6973)** — `autobot-infrastructure/shared/scripts/hooks/pre-commit-no-new-status-enum`, registered in `.pre-commit-config.yaml`. Blocks commits adding new top-level `class FooStatus(Enum):` / `class FooStatus(str, Enum):` declarations outside `autobot_shared/status_enums.py` and a short audited exemption list (domain-specific, non-lifecycle shapes). New code must import the canonical type (`TaskStatus`, or its `JobStatus`/`WorkflowStatus` aliases) or alias it. Last-resort suppression: `# noqa: status-shape`.
2. **Pre-commit hook `no-new-workflow-step` (#6951)** — same mechanism for the canonical workflow dataclasses: blocks new top-level `WorkflowStep`/`AgentTask`/`WorkflowPlan` dataclass declarations outside `autobot_shared/workflow/types.py` (subclasses and aliases allowed).

On the frontend, the generated file itself is the guard: the union exists at a single generated path, the drift CI keeps it in sync, and the broader canonical-pattern lint framework is catalogued in [CANONICAL_RULES.md](CANONICAL_RULES.md).

---

## Related documents

- [CANONICAL_RULES.md](CANONICAL_RULES.md) — canonical-pattern rule catalog (`tools/lint/canonical*`)
- [01-architecture.md](01-architecture.md) — system architecture overview
- [../system-state.md](../system-state.md) — canonical type consolidation history (#6973, #6689, #6534, #7226)
