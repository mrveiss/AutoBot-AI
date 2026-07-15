# Company OS Phase 3 — analytics findings → project work items (proposal-only, FP-verified) — design

**Date:** 2026-07-08
**Umbrella:** #11129 (Phase 3) · Issue: #11271
**Status:** design — decisions captured; ready for writing-plans

## Goal

Turn codebase-analytics **findings** for a Company OS project's linked repo into **actionable
project work items** that agents pick up — but **only after** each finding is inspected for
false positives and a human/agent promotes it. Nothing auto-creates work items. This closes the
loop the user described: "the codebase analytics should show repos of projects" (Phase 1) → "this
would allow agent when working on code act on problems" (Phase 3).

## Pipeline

```
analytics findings (per source_id)
   → FP-verify (internal SLM inspects each finding vs. the actual code → is_real + rationale)
   → proposal queue (only is_real findings; LLCFindingProposal, status=pending)
   → promote (human OR agent) → LLCWorkItem   [optionally LLCApproval-gated]
   → dismiss (human marks false-positive / won't-fix with reason)
```

**Proposal-only**: findings never become work items automatically. **FP-verification is a
first-class stage** — a finding cannot enter the queue until the verifier judges it real, and the
verdict + rationale are stored so a human sees *why*.

## Key reuse (everything the seams need already exists)

- **Findings** (`api/codebase_analytics/`): per-file dicts `{type, severity, file_path,
  line_number, description, suggestion, file_category}`, indexed in ChromaDB with `source_id`
  metadata. Queryable via `endpoints/report.py::_fetch_problems_from_chromadb(source_id,
  source_root)` (already validates file existence, #2724). Findings have a stable identity
  `{source_id, file_path, line_number, type}` → dedup key.
- **Proposal-only pattern** (#11170 `code_analysis/src/remediation_loop.py`): `select_targets`
  (ranked, capped selection) + `dispatch_proposal` (flag-gated, default OFF, builds work-item
  payloads without creating them). Phase 3 mirrors this shape.
- **Project↔source join** (Phase 1): `LLCProject.code_source_id` → `CodeSource.id` →
  `clone_path` (local checkout to read code for verification) + findings by `source_id`.
  `llc/api/sprints.py::_project_source_summary` already resolves project→source.
- **Work-item creation**: `llc/services/work_item_service.py::WorkItemService.create(session,
  company_id, type, title, *, description, priority, project_id, labels,
  requires_approval_before, …)` — auto-identifier, returns `LLCWorkItem`. Agent pickup via
  `checkout()` (Redis-fenced).
- **Internal SLM engine** (#11215): `chat_workflow/delegation.py` internal engine +
  `chat_workflow/llm_handler.py` — the verifier calls this (self-hosted; no external cost).
- **SLM-configurable policy** (Phase 2 pattern): `services.slm_client` + a settings key, read with
  safe defaults.
- **Approval** (Phase 2): `llc/services/approval.py` `ApprovalService` + `LLCApproval`.

## Decisions (brainstorm 2026-07-08)

- **FP-verifier model** = the **internal SLM engine** (self-hosted; consistent with governed
  delegation).
- **Scan trigger** = **manual on-demand** ("Scan for findings" project action). An
  `run_on_index` auto-scan is a *config toggle only*, deferred (not built now).
- **Storage** = a new Postgres table `llc_finding_proposals` (project-scoped, statused,
  dedup-keyed) — not Redis; proposals are durable, queryable, and human-reviewed.
- **Safety** = feature flag-gated, default **OFF** (mirrors `REMEDIATION_DISPATCH_ENABLED`).
  Promotion may require an `LLCApproval` per policy.
- **Promotion** creates one `LLCWorkItem` per proposal (type `BUG` for defect-type findings else
  `TASK`), `project_id` set, labels `["analytics-finding", f"severity:{sev}"]`, description
  carries `file:line` + suggestion + the verifier's rationale.

## Data model — `LLCFindingProposal` (`llc/models/finding_proposal.py`)

```
id                UUID PK
company_id        UUID (index)
project_id        UUID  FK llc_projects(id) ondelete=CASCADE (index)
source_id         str   (the CodeSource id the finding came from)
finding_key       str   unique per project = f"{source_id}:{file_path}:{line_number}:{type}"  (dedup)
finding_type      str
severity          str   (high|medium|low)
file_path         str
line_number       int | null
description        text
suggestion        text | null
verdict_is_real   bool | null      (null until verified)
verdict_confidence float | null    (0..1)
verdict_rationale text | null      (why the verifier judged real/FP)
status            enum finding_proposal_status: pending | promoted | dismissed  (default pending, index)
work_item_id      UUID | null      (set on promote)
dismiss_reason    text | null      (set on dismiss)
created_at / updated_at
```

- **Unique constraint** `(project_id, finding_key)` — a re-scan updates the existing proposal
  rather than duplicating; already-promoted/dismissed proposals are not re-queued.

## Services

### `llc/services/findings_gather.py`
`async gather_findings(project, session) -> list[dict]` — resolve `project.code_source_id` →
source → call the analytics problems query (service-level, reusing
`_fetch_problems_from_chromadb`) filtered by `source_id` and the SLM policy's `min_severity`.
Returns raw finding dicts. No writes.

### `llc/services/findings_verify.py`  ← the novel/risky stage
`async verify_finding(finding, clone_path) -> Verdict{is_real, confidence, rationale}` — reads the
code context around `file_path:line_number` from `clone_path`, prompts the **internal SLM engine**
("Here is a static-analysis finding and the surrounding code. Is this a REAL issue or a false
positive? Return is_real, confidence 0..1, and a one-paragraph rationale."), parses a structured
verdict. Best-effort + bounded: on engine error, verdict defaults to `is_real=false` (fail-closed —
an unverifiable finding does NOT enter the queue) with rationale noting the failure. Concurrency
capped; large batches processed in bounded chunks.

### `llc/services/finding_proposal_service.py`
- `async scan(project, session) -> {gathered, verified_real, queued}` — orchestrates gather →
  verify (each finding) → upsert `LLCFindingProposal` for `is_real` findings (dedup by
  `finding_key`; skip keys already `promoted`/`dismissed`). Stores the verdict on every proposal.
- `async promote(proposal, session, actor) -> LLCWorkItem` — only from `pending`; if policy
  `require_approval_to_promote` → create `LLCApproval` (type `finding_promotion`) and set
  status accordingly; else create the work item via `WorkItemService.create` and set
  `status=promoted`, `work_item_id`.
- `async dismiss(proposal, session, reason)` — `pending` → `dismissed` + `dismiss_reason`.

## API (`llc/api/sprints.py` or a new `llc/api/findings.py` under the same `/api/llc` mount)

- `POST /api/llc/projects/{id}/findings/scan` → runs `scan` (flag-gated; 409 if no
  `code_source_id`; 403 if feature flag OFF). Returns counts.
- `GET  /api/llc/projects/{id}/findings/proposals?status=pending` → list proposals (with verdict).
- `POST /api/llc/findings/proposals/{pid}/promote` → promote → work item (or approval-pending).
- `POST /api/llc/findings/proposals/{pid}/dismiss` `{reason}` → dismiss.
- All IDOR-guarded (`company_id == ctx.org_id`).

## SLM-configurable findings policy

Key `llc.findings_policy` (read via `services.slm_client`, safe defaults):
`{ enabled: bool = false, min_severity: "medium", require_approval_to_promote: bool = false,
   run_on_index: bool = false, verify_batch_size: int = 10 }`. SLM-frontend panel mirrors the
Phase 2 `DisposalPolicySettings.vue`.

## Frontend (Company OS — `autobot-frontend`)

- Project detail: a **"Findings"** tab → "Scan for findings" button (calls `scan`) + the proposal
  queue: each row shows severity badge, `file:line`, description, the **verifier verdict +
  rationale**, and **Promote** / **Dismiss** actions (Dismiss prompts for a reason). Promoted rows
  link to the created work item. i18n across all 11 locales; no hardcoded strings.
- Reuse problem-formatting from `report.py::_format_problem_entry` semantics where practical.

## Governance / safety

- Feature flag default OFF; `scan` and `promote` are no-ops/403 when disabled.
- FP-verify **fails closed** (unverifiable → not queued).
- Promotion optionally `LLCApproval`-gated.
- Dedup by `finding_key`; promoted/dismissed proposals are never silently re-queued.
- Verifier is the internal SLM engine (no external data egress; consistent with
  [[autobot_telemetry_local_only]]).

## Error handling

- No `code_source_id` → `scan` 409. Source not `READY`/missing clone_path → 409 (can't read code
  to verify). Analytics query failure → surfaced, no partial queue. Verifier engine down → each
  finding fails closed with rationale; `scan` still returns counts. SLM policy unreadable → safe
  defaults (feature effectively OFF).

## Testing

- Gather: project→source→findings join; min_severity filter; no source → error.
- Verify: real→queued; FP→not queued; engine error→fail-closed (not queued) with rationale; code
  context read from clone_path.
- Proposal service: upsert dedup by finding_key; skip promoted/dismissed on re-scan; promote
  creates work item with correct fields + links; approval-gated path; dismiss sets reason.
- API: scan 409 (no source) / 403 (flag OFF); list; promote; dismiss; IDOR guards.
- Policy: read + safe defaults; frontend panel round-trip.
- Frontend: scan action, queue render incl. verdict/rationale, promote/dismiss flows, i18n 11
  locales.

## Scope

**In:** the full pipeline above (manual scan trigger, internal-SLM FP-verify, Postgres proposal
queue, promote/dismiss, SLM policy + panel, Findings UI). **Out (deferred toggles/roadmap):**
auto-scan `run_on_index` wiring (config field ships, wiring later); cross-project findings
dashboards; auto-promotion without human/agent action; editing findings.
