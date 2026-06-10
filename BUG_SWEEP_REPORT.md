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

Order: security/crash → functional → cosmetic. Every fix has a test that was red pre-fix (verified by stashing the source) and green post-fix.

| # | Commit | What | Test (red→green) |
|---|---|---|---|
| (prereq) | `ac540cbd1` | `mocks.py` add `from __future__ import annotations` (`"AsyncMock" \| None` eager-eval) — unblocks `audit_logger_test` collection | filed **#9896**; existing `audit_logger_test` now collects |
| 9832 | `95df94afe` | `config.backend_host`→`config.vm.*`/`config.port.*` at 3 sites (audit_logger + EFM ×2); also fixed `backend_port`/`frontend_host`/`vnc_port`/`ai_stack_*`/`browser_*` in EFM which raise identically | `enterprise_feature_manager_test.py` (new) + `audit_logger_test.py` (8 were red) |
| 9788 | `3c2622932` | mask `to`/`phone_number` in all whatsapp return dicts; payloads + `to_dict()` persistence left intact | `whatsapp_integration_test.py` (3 new; payload keeps real number) |
| 9785 | `7f9d14590` | `add_column_if_not_exists`/`create_index_if_not_exists` table-aware via existing `table_exists()` | `migrations/utils_test.py` (new) |
| 9782 | `0ea397521` | `AUTOBOT_AI_STACK_ENABLED` gate (default on); disabled → no network, no flood; compose sets false | `ai_stack_client_gate_test.py` (new) |
| 9783 | `1b1610d77` | gate 4 Postgres-dependent lifespan init steps with `_llc_postgres_available()` | `lifespan_postgres_gate_test.py` (new); Redis-index facet split to **#9904** |
| 9767 | `6f10289e3` | `http_client.request` `suppress_error_log` opt-in; default ERROR restored; 2 probe sites opt in | `http_client_test.py` (new) |
| 9768 | `625d3d97d` | `slm_url` property honors `SLM_URL` field | `ssot_config_test.py` (2 new) |

**7 issues fixed**, 8 commits. Combined backend test group: **35 passed**.

Discoveries filed during the sweep: **#9896** (mocks.py future-import), **#9904** (RediSearch index on db!=0). Also noted but not yet filed: `ssot_config_test.py` uses non-existent `from config.ssot_config` (whole `TestAutoBotConfig` class red); ambiguous top-level `tests` namespace shadows `autobot-backend/tests`.

## Phase 3 — Loop closure

**DUPLICATE/STALE (closed):**
- **#9784** — root cause (`codebase_index_embedding_mode: int=0`.`lower()` at import) fixed by #9862 (`b25418f95` int→str). Verified via `git show`. Closed.
- **#9710** — both `update-all-nodes.yml` copies now use `npm run build:slm`; deploy-breaking drift gone. Closed (de-dup is optional follow-up).

**NEEDS-REPRO (commented + labeled):** #9670, #9697, #9693, #9766, #9852 — each asked for the specific missing info (repro/logs/env/decision).

**TOO-BIG (analysis comment):** #9863, #9759, #9793, #9794, #9856, #9861, #9851 + #9664. **Already owned by active worktrees (left alone):** #9873 (`issue-9873`/`issue-9873b`), #9489 (`pr-9630`).
