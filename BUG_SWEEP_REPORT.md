# Bug Sweep Report — 2026-06-10

Branch: `bugfix/sweep-2026-06-10` off `Dev_new_gui`.
Scope: all 24 open `bug`-labeled issues. Backend is canonical. One commit per fix, each with a test that would have caught it.

## Phase 1 — Triage

| # | Title (short) | Class | Reason |
|---|---|---|---|
| 9832 | audit_logger/enterprise use non-existent `config.backend_host` → 500 | **FIXABLE-NOW** | Verified: 3 sites use `config.backend_host` (doesn't exist); canonical is `config.vm.main` (ssot_config:106). 500s every audited request. |
| 9788 | whatsapp return dicts carry unmasked phone (PII) | **FIXABLE-NOW** | Verified `"to": to` at ~15 return sites; `_mask_phone` exists. Mask at boundary. |
| 9785 | `add_column_if_not_exists` ALTERs non-existent table on fresh DB | **FIXABLE-NOW** | Verified utils.py:84 guards column not table; add `to_regclass` table guard. |
| 9782 | AI Stack client warn-floods when stack absent | **FIXABLE-NOW** | Verified ai_stack_client polls 127.0.0.1:8080 unconditionally; add enabled gate. |
| 9767 | http_client global error→debug downgrade | **FIXABLE-NOW** | Add `suppress_error_log` kwarg; pass only from health-probe call sites. |
| 9768 | dead `SLM_URL` config field (property ignores it) | **FIXABLE-NOW** | Verified field@1441 unused; property@1775 ignores it. Make property honor it. |
| 9783 | gate Postgres-dependent startup steps in single_user | **FIXABLE-NOW** | Existing `_llc_postgres_available()` gate; mechanical wrap. Watch 100-line limit. |
| 9784 | recover_index_queue `'int'.lower()` on every boot | **DUPLICATE/STALE** | Root cause was `codebase_index_embedding_mode: int=0`.`lower()` at import; #9862 (b25418f95) changed field → `str="precompute"`. Verified via `git show`. |
| 9710 | duplicate update-all-nodes.yml stale SLM build cmd | **DUPLICATE/STALE** | Verified both playbooks now use `npm run build:slm` (line 240 & 341). The deploy-breaking drift is gone; de-dup is optional maintainability follow-up. |
| 9670 | basename validation fails for subdir files (Paperclip MVA-3764) | **NEEDS-REPRO** | No specific file named; many `basename` uses in repo; cause not determinable from report. |
| 9697 | FontAwesome icon rendering failures in tests | **NEEDS-REPRO** | Frontend test-env specific; needs the failing test run + node env to reproduce. |
| 9693 | frontend-tests failures on main post deps-bump #9512 | **NEEDS-REPRO** | Env/CI-specific (starlette/aiohttp bump); no failing-test output captured. |
| 9766 | ChromaDB 0.5→1.5.9 existing data needs reindex | **NEEDS-REPRO** | Data-migration / docs task; no code defect to repro. Deployment-state dependent. |
| 9852 | backend→SLM WebSocket 401 (SLM_AUTH_TOKEN) | **NEEDS-REPRO** | Requires running compose + a JWT-minting design decision; not determinable from code alone. |
| 9489 | Semgrep SAST findings (broad) | **TOO-BIG** | Many files across security surface; **active worktree `pr-9630`** (another agent). |
| 9664 | transcriber merge-conflict resolution | **TOO-BIG** | 33-file cross-branch merge; requires feature-matrix decisions. |
| 9759 | broken Alembic chain (KeyError '20260216_002') | **TOO-BIG** | Cross-cutting schema repair + ordering; blocks RBAC. |
| 9793 | LLC subprocess agents unrunnable under compose | **TOO-BIG** | Requires Docker image change / sidecar; deployment layer. |
| 9794 | collapse duplicate extensions/ package | **TOO-BIG** | Repoint test importers + remove package; consolidation, not behavior-preserving. |
| 9851 | API contract drift (umbrella) | **TOO-BIG** | Umbrella tracking many sub-tasks. |
| 9856 | code_intelligence/security/ broken & unwired | **TOO-BIG** | Repair broken import + rewire 4 consumers + prove equivalence. |
| 9861 | LLC dashboard endpoints + company-context | **TOO-BIG** | 5 endpoints + frontend context plumbing + IDOR hardening. |
| 9863 | api/transcripts.py unmounted — mount or delete | **TOO-BIG** | Requires product decision (mount vs delete); not a blind fix. |
| 9873 | analytics_precommit BUILTIN_CHECKS drift | **TOO-BIG** | **Active worktrees `issue-9873` + `issue-9873b`** with commits — another agent owns it. |

**Counts:** FIXABLE-NOW 7 · NEEDS-REPRO 5 · DUPLICATE/STALE 2 · TOO-BIG 10 (2 of which are already claimed in active worktrees).

## Phase 2 — Fixes

_(filled in as each lands)_

## Phase 3 — Loop closure

_(filled in at end)_
