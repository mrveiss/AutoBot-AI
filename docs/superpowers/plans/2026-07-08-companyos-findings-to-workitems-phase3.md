# Company OS Phase 3 — findings → work items (proposal-only, FP-verified) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Codebase-analytics findings for a project's linked repo become project work items only after a fail-closed false-positive check and a human/agent promotion. Nothing auto-creates work items.

**Architecture:** New Postgres `llc_finding_proposals` queue. A gather service pulls findings by `source_id`; a verify service asks the internal SLM engine whether each finding is real (fail-closed); a proposal service upserts verified proposals (dedup by `finding_key`), promotes them to `LLCWorkItem` (optionally approval-gated), or dismisses them. SLM-configurable policy, flag-gated default OFF. Company OS Findings tab + SLM policy panel.

**Tech stack:** FastAPI, SQLAlchemy 2 async (Postgres), Alembic, Pydantic v2, Vue 3 + TS, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-07-08-companyos-findings-to-workitems-design.md` (source of truth).

## Global Constraints

- Branch `issue-11271`, worktree `.worktrees/issue-11271`, target `Dev_new_gui`.
- **NO commit trailers**; copyright `# Copyright 2025-2026 mrveiss` + `# SPDX-License-Identifier: Apache-2.0` on new files.
- ≤30-line functions; async-first; lazy-import heavy `api.codebase_analytics` modules inside functions.
- Routes under `/api/llc` (the llc router already prepends it — bare paths, **no** extra `/api`).
- **Feature flag default OFF** (`findings_policy.enabled=false`): `scan`/`promote` return 403 when disabled.
- **FP-verify FAILS CLOSED**: any engine/parse error → `is_real=False` → NOT queued.
- **No hardcoded UI strings** — autobot-frontend strings i18n to ALL 11 locales; SLM panel follows the SLM console's inline-English convention (mirror `DisposalPolicySettings.vue`).
- `black -l120` + `isort` clean before every commit. Copyright headers.
- `verify-generated-types` is REQUIRED: new endpoints change the OpenAPI schema → `api.ts` regen is handled by the CI autofix bot (do not hand-generate).
- Commit format `<type>(scope): <desc> (#11271)`.

## File Structure

- Create: `autobot-backend/llc/models/finding_proposal.py`, migration `autobot-backend/migrations/versions/20260708_069_llc_finding_proposals.py`, `autobot-backend/llc/services/findings_gather.py`, `.../findings_verify.py`, `.../findings_policy.py`, `.../finding_proposal_service.py`, `autobot-backend/llc/api/findings.py`, `autobot-slm-frontend/src/views/settings/FindingsPolicySettings.vue`.
- Modify: `autobot-backend/llc/models/enums.py` (statuses), `autobot-backend/llc/api/__init__.py` (include findings router), `autobot-frontend/src/views/llc/ProjectBrowserView.vue` (+11 locale files).
- Enum values reused: `WorkItemType.BUG="bug"`/`TASK="task"`, `WorkItemPriority` CRITICAL/HIGH/MEDIUM/LOW (`llc/models/enums.py`).

---

## Task 1: Model + migration (`LLCFindingProposal`)

**Files:** Create `llc/models/finding_proposal.py`, `llc/models/enums.py` (add `FindingProposalStatus`), migration `20260708_069_llc_finding_proposals.py` (chains onto head `20260708_068` — verify head with `alembic ... get_heads()` before writing). Test `llc/tests/test_finding_proposal_model.py`.

**Interfaces — Produces:** `LLCFindingProposal` (table `llc_finding_proposals`) with columns per the spec's data-model section; `FindingProposalStatus` enum `pending|promoted|dismissed`; unique constraint `uq_finding_proposal_project_key (project_id, finding_key)`.

- [ ] **Step 1 — failing test** `test_finding_proposal_model.py`: assert table has columns `company_id, project_id, source_id, finding_key, finding_type, severity, file_path, line_number, description, suggestion, verdict_is_real, verdict_confidence, verdict_rationale, status, work_item_id, dismiss_reason`; `status` server_default `"pending"`; a unique constraint over `(project_id, finding_key)`; `FindingProposalStatus.PROMOTED.value == "promoted"`.
- [ ] **Step 2 — run, expect fail.** `cd autobot-backend && python3 -m pytest llc/tests/test_finding_proposal_model.py -v`.
- [ ] **Step 3 — enum** in `llc/models/enums.py` (mirror existing `str, Enum` classes + `pg_enum_values`): `class FindingProposalStatus(str, Enum): PENDING="pending"; PROMOTED="promoted"; DISMISSED="dismissed"`.
- [ ] **Step 4 — model** `llc/models/finding_proposal.py` (mirror `LLCProject` column style: `Mapped[...]`, `mapped_column`, `sa.Enum(FindingProposalStatus, name="findingproposalstatus", create_type=True, values_callable=pg_enum_values)`; `project_id` FK `llc_projects.id` ondelete CASCADE, indexed; `finding_key` String(512); `status` indexed server_default `"pending"`; `line_number` Integer nullable; `verdict_confidence` Numeric nullable; `work_item_id` UUID nullable; `UniqueConstraint("project_id","finding_key",name="uq_finding_proposal_project_key")` in `__table_args__`).
- [ ] **Step 5 — migration** `20260708_069_llc_finding_proposals.py` (revision `20260708_069`, down_revision `20260708_068`): create the enum type + table + indexes + unique constraint; downgrade drops table then enum. Follow the Phase-2 migration `20260708_067` structure for enum create/drop.
- [ ] **Step 6 — run, expect pass**; also verify single head: `python3 -c "from alembic.config import Config; from alembic.script import ScriptDirectory; c=Config(); c.set_main_option('script_location','migrations'); print(ScriptDirectory.from_config(c).get_heads())"` → `['20260708_069']`.
- [ ] **Step 7 — commit** `feat(companyos): LLCFindingProposal model + migration (#11271)`.

---

## Task 2: Findings gather service

**Files:** Create `llc/services/findings_gather.py`; test `llc/tests/test_findings_gather.py`.

**Interfaces — Produces:** `async gather_findings(project, min_severity: str, session) -> list[dict]`. **Consumes:** `project.code_source_id`; `api.codebase_analytics.source_storage.get_source`; the analytics problems query. Returns finding dicts `{type, severity, file_path, line_number, description, suggestion}`.

- Implementation: lazy-import inside the function `from api.codebase_analytics.source_storage import get_source`; if `project.code_source_id` falsy → raise `ValueError("project has no linked repo")`. Resolve source; if `source is None` or not ready → `ValueError`. Fetch findings for `source.id` and filter to `severity in _at_or_above(min_severity)` (order high>medium>low). **Verify the exact analytics call**: read `api/codebase_analytics/endpoints/report.py::_fetch_problems_from_chromadb` (line ~1217) + `resolve_source_root` + `api/codebase_analytics/storage.py::get_code_collection_async`; call them at service level (lazy import). If a clean service function doesn't exist, call `_fetch_problems_from_chromadb(collection, None, source_id=source.id, source_root=resolve_source_root(source.id))` exactly as the `/problems` endpoint does. Document the real call in the code comment.

- [ ] **Step 1 — failing test**: patch `llc.services.findings_gather.get_source` (AsyncMock → SimpleNamespace(id, clone_path, status)) and the analytics fetch (patch at its source module) to return 3 findings of mixed severity; assert `min_severity="medium"` drops the `low` one; assert no-`code_source_id` project raises `ValueError`.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** per above (helper `_at_or_above(sev)` returns the set of acceptable severities; ≤30-line functions).
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(companyos): findings gather service (project→source→findings) (#11271)`.

---

## Task 3: FP-verify service (internal SLM, fail-closed)

**Files:** Create `llc/services/findings_verify.py`; test `llc/tests/test_findings_verify.py`.

**Interfaces — Produces:** `@dataclass(frozen=True) Verdict(is_real: bool, confidence: float, rationale: str)`; `async verify_finding(finding: dict, clone_path: str) -> Verdict`. **Consumes:** `services.llm_service.get_llm_service()` → its async `chat(...)` (VERIFY the exact signature/return at `services/llm_service.py:179` — determine how to get a one-shot text completion; the plan's code below names the call but the implementer MUST match the real signature).

- Implementation: read a bounded code window (e.g. ±15 lines) around `finding["line_number"]` from `Path(clone_path)/finding["file_path"]` (utf-8; if file/line missing → still verify with description only). Build a prompt: "You are auditing a static-analysis finding for false positives. FINDING: {type/severity/file/line/description/suggestion}. CODE CONTEXT: {window}. Answer strictly as JSON {\"is_real\": bool, \"confidence\": 0..1, \"rationale\": \"...\"}. Judge is_real=false if the finding does not correspond to a genuine problem in this code." Call `get_llm_service().chat(...)`, extract the text, parse the JSON. **FAIL CLOSED:** any exception, missing file, empty response, or JSON-parse failure → `Verdict(is_real=False, confidence=0.0, rationale="unverifiable: <reason>")`. Wrap the whole body in try/except returning the fail-closed verdict. Log at warning on failure.

- [ ] **Step 1 — failing test**: (a) patch `get_llm_service` to return an object whose `chat` (AsyncMock) yields a valid JSON verdict `{"is_real": true, "confidence": 0.9, "rationale": "..."}` → assert `Verdict.is_real is True`; (b) patch `chat` to raise → assert fail-closed `is_real is False`; (c) patch `chat` to return non-JSON → fail-closed. Use a `tmp_path` clone dir with a small file so the code-window read works.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement**; split code-window read + prompt-build + parse into ≤30-line helpers. **Verify `chat` signature against `services/llm_service.py:179` and adapt the call + response extraction to the real shape.**
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(companyos): fail-closed FP-verify via internal SLM engine (#11271)`.

---

## Task 4: Findings-policy SLM reader

**Files:** Create `llc/services/findings_policy.py`; test `llc/tests/test_findings_policy.py`. **Mirror `llc/services/disposal_policy.py` exactly** (same SLM-client read + safe-default pattern).

**Interfaces — Produces:** `@dataclass(frozen=True) FindingsPolicy(enabled=False, min_severity="medium", require_approval_to_promote=False, run_on_index=False, verify_batch_size=10)`; `POLICY_SETTING_KEY="llc.findings_policy"`; `async get_findings_policy() -> FindingsPolicy` (safe defaults on missing/unreadable/malformed — defaults leave the feature OFF).

- [ ] **Step 1 — failing test** (mirror `test_disposal_policy.py`): defaults when no SLM client; parse a full policy dict; defaults on malformed. Assert default `enabled is False`.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** (copy `disposal_policy.py` structure; coerce types with `max(0,int(...))`/`bool(...)`/`str(...)`; unknown min_severity → "medium").
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(companyos): SLM findings-policy reader with safe defaults (#11271)`.

---

## Task 5: Proposal service (scan / promote / dismiss)

**Files:** Create `llc/services/finding_proposal_service.py`; test `llc/tests/test_finding_proposal_service.py`.

**Interfaces — Produces:**
- `async scan(project, session) -> dict{gathered, verified_real, queued}` — reads policy; if `not policy.enabled` → raise `FindingsDisabledError`. `gather_findings(project, policy.min_severity, session)` → for each finding compute `finding_key=f"{source_id}:{file_path}:{line_number}:{type}"`; skip keys whose existing proposal is `promoted`/`dismissed`; `verify_finding(finding, clone_path)`; only `verdict.is_real` → upsert `LLCFindingProposal` (pending) with the verdict fields. Process in `policy.verify_batch_size` chunks. Returns counts.
- `async promote(proposal, session, actor_user_id) -> LLCWorkItem | dict` — only from `pending`; read policy; if `require_approval_to_promote` → create `LLCApproval` (type `finding_promotion` — add to `ApprovalType` enum + migration note; reuse Phase-2 `ApprovalService`), keep `pending`, return `{"result":"pending_approval","approval_id":...}`; else `WorkItemService.create(session, company_id=str(project.company_id), type=_type_for(finding_type), title=_title(p), description=_body(p), priority=_priority(p.severity), project_id=str(p.project_id), labels=["analytics-finding", f"severity:{p.severity}"])`, set `status=promoted`, `work_item_id=item.id`; return the item.
- `async dismiss(proposal, session, reason) -> None` — `pending`→`dismissed` + `dismiss_reason`.
- Helpers: `_type_for` (BUG for defect-ish types else TASK), `_priority` (high→HIGH, medium→MEDIUM, low→LOW), `_title`/`_body` (body carries `file:line`, suggestion, and the verdict rationale). **Add `ApprovalType.FINDING_PROMOTION="finding_promotion"`** in `enums.py` + an `ALTER TYPE approvaltype ADD VALUE` in Task 1's migration (autocommit_block, mirror Phase-2 `20260708_067`).

- [ ] **Step 1 — failing tests**: scan disabled→raises; scan queues only `is_real` findings and skips a finding_key already promoted (dedup); promote immediate creates a work item (patch `WorkItemService.create`) and sets promoted+work_item_id; promote with approval-required returns pending_approval (patch policy + ApprovalService); dismiss sets reason. Use AsyncMock session + patched gather/verify/policy.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** (lazy-import `WorkItemService`/`ApprovalService` to avoid heavy chains; ≤30-line functions; verify `WorkItemService.create` kwargs at `llc/services/work_item_service.py:250`).
- [ ] **Step 4 — run, expect pass**; then run full `llc/tests/ -q` to confirm no regression.
- [ ] **Step 5 — commit** `feat(companyos): finding-proposal scan/promote/dismiss service (#11271)`.

---

## Task 6: API endpoints (`llc/api/findings.py`)

**Files:** Create `llc/api/findings.py`; modify `llc/api/__init__.py` to `include_router`; test `llc/tests/test_findings_api.py`.

**Interfaces — Produces routes under `/api/llc`:** `POST /projects/{project_id}/findings/scan` (403 if `not policy.enabled`; 409 if no `code_source_id`; returns scan counts); `GET /projects/{project_id}/findings/proposals?status=pending`; `POST /findings/proposals/{proposal_id}/promote`; `POST /findings/proposals/{proposal_id}/dismiss` (`{reason}`). All load-and-IDOR-guard (mirror `_load_owned_project` in `sprints.py`; add `_load_owned_proposal`). Import `get_findings_policy`, `scan`, `promote`, `dismiss` at module level so tests can patch `llc.api.findings.*`. Response models: `FindingProposalResponse` (all proposal fields incl. verdict).

- [ ] **Step 1 — failing tests** (mirror `test_project_lifecycle_api.py` harness with FastAPI TestClient + dependency overrides): scan returns 403 when policy disabled; 409 when project has no `code_source_id`; scan success returns counts (patch `llc.api.findings.scan`); list returns proposals; promote calls the service; dismiss requires a reason; IDOR 404 when `company_id != org_id`.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** the router + `_load_owned_project`/`_load_owned_proposal`; register in `llc/api/__init__.py`. Confirm the mount serves `/api/llc/projects/{id}/findings/scan` (no double `/api`).
- [ ] **Step 4 — run, expect pass**; full `llc/tests/ -q` green.
- [ ] **Step 5 — commit** `feat(companyos): findings scan/proposals/promote/dismiss endpoints (#11271)`.

---

## Task 7: SLM findings-policy panel

**Files:** Create `autobot-slm-frontend/src/views/settings/FindingsPolicySettings.vue`; route + settings-nav entry; test `.../FindingsPolicySettings.test.ts`. **Mirror `DisposalPolicySettings.vue`** (GET/PUT/POST setting key `llc.findings_policy` as JSON; `authStore.getApiUrl()`/`getAuthHeaders()`; `data-test="save-policy"`).

- Fields: enabled (toggle), min_severity (select high/medium/low), require_approval_to_promote (toggle), run_on_index (toggle), verify_batch_size (number).
- [ ] **Step 1 — failing vitest** (mirror the disposal test): loads policy on mount; PUTs JSON on save to `/api/settings/llc.findings_policy`.
- [ ] **Step 2 — run, expect fail:** `cd autobot-slm-frontend && npx vitest run src/views/settings/FindingsPolicySettings.test.ts`.
- [ ] **Step 3 — implement** component + route (`/settings/findings-policy`) + nav tab (mirror how DisposalPolicy is registered).
- [ ] **Step 4 — run test + `npm run build:slm`** (must succeed).
- [ ] **Step 5 — commit** `feat(slm): findings policy settings panel (#11271)`.

---

## Task 8: Company OS Findings tab + i18n

**Files:** Modify `autobot-frontend/src/views/llc/ProjectBrowserView.vue` (or the project detail view — follow where Phase-2 lifecycle actions live); add i18n keys to ALL 11 locale files under `autobot-frontend/src/i18n/locales/`; test `.../__tests__/ProjectBrowserView.findings.test.ts`.

- UI: a "Scan for findings" action (`POST /api/llc/projects/{id}/findings/scan`) and a proposal list — each row shows severity badge, `file:line`, description, the **verdict + rationale**, and **Promote** (`POST /findings/proposals/{id}/promote`) / **Dismiss** (prompt for reason → `POST …/dismiss`). Refresh after each action. Use the existing `ApiClient` (parsed JSON, no `.data`). All strings via i18n keys under the view's existing `llcBrowser` namespace (`llcBrowser.findings.*`), added to every one of the 11 locales.
- [ ] **Step 1 — i18n keys** (English first, then mirror to the other 10): `llcBrowser.findings.{scan, scanning, promote, dismiss, dismissReason, empty, verdictReal, verdictRationale, disabled, severity}`.
- [ ] **Step 2 — failing vitest** (mirror `ProjectBrowserView.lifecycle.test.ts`): a proposal renders with verdict; Scan click calls POST `.../findings/scan`; Promote calls POST `.../promote`; Dismiss (with reason) calls POST `.../dismiss`.
- [ ] **Step 3 — run, expect fail.**
- [ ] **Step 4 — implement** UI + i18n (confirm all 11 locale files edited).
- [ ] **Step 5 — verify:** `npx vitest run …findings.test.ts`; `npx vue-tsc --noEmit -p tsconfig.app.json`; `npx eslint <changed .vue> --max-warnings 0`.
- [ ] **Step 6 — commit** `feat(companyos): project findings proposal queue UI + i18n (#11271)`.

---

## Self-Review Checklist (before final review)

1. **Spec coverage:** gather (T2), fail-closed FP-verify (T3), proposal queue+dedup (T1/T5), promote→work item + approval-gate (T5), dismiss (T5), SLM policy+panel (T4/T7), Findings UI (T8), flag-off 403 (T6). ✔ each.
2. **FP-verify fails closed** — T3 tests cover engine error + parse failure → not queued.
3. **Type consistency:** `FindingProposalStatus` values identical across model/service/API; `FindingsPolicy` fields identical across T4/T6/T7; `finding_key` format identical in T5 (write) and any dedup read.
4. **Migration head:** `20260708_069` chains onto `20260708_068`; single head; enum ADD VALUE for `finding_promotion` in autocommit_block.
5. **Constraints:** no commit trailers; copyright headers; ≤30-line funcs; i18n 11 locales; flag default OFF; no double `/api` prefix; black/isort clean.
6. **verify-generated-types:** new endpoints → api.ts regen via CI autofix bot (close/reopen to re-trigger).
