---
tags: [audit, docs, orphans, maintenance]
date: 2026-06-04
---

# Orphan Audit — 2026-06-04

**Total markdown files:** 1,012  
**Orphans (no incoming links):** 399  
**Expected standalone:** 270 — no action  
**Actionable orphans:** 129 — need linking or cleanup

---

## Summary by Category

| Category | Count | Action |
|---|---|---|
| GitHub convention files | 5 | None — GitHub-required |
| `_index.md` section pages | 43 | None — Hugo outward-only |
| README standalone | 94 | None — expected |
| Prompt templates (`resources/prompts/`) | 91 | None — loaded dynamically |
| Test reports (`tests/results/`) | 27 | None — ephemeral |
| **Causal AI artifacts** | **8** | **Delete or integrate** |
| **Implementation reports** | **8** | **Move to docs/ or delete** |
| **Frontend reports** | **31** | **Link from README or delete** |
| **Developer docs unlinked** | **21** | **Link from CLAUDE_RULES.md index** |
| **Architecture docs** | **5** | **Link from docs/architecture/README** |
| SLM ansible docs | 4 | Expected standalone |
| NPU GUI docs | 6 | Expected standalone |
| **Other actionable** | **56** | **Review individually** |

---

## ACTION REQUIRED: Causal AI Artifacts (8)

Root-level dump files from a prior causal inference implementation sprint. Either integrate into `docs/architecture/` or delete.

- [[CAUSAL_EXTRACTOR_SUMMARY]]
- [[CAUSAL_FRAMEWORK_INTEGRATION_TEST_REPORT]]
- [[CAUSAL_INFERENCE_ALGORITHMS]]
- [[CAUSAL_INFERENCE_ENGINE_SUMMARY]]
- [[CAUSAL_INFERENCE_INTEGRATION]]
- [[CAUSAL_REASONING_IMPLEMENTATION]]
- [[autobot-backend/orchestration/CAUSAL_ERROR_RECOVERY_DESIGN]]
- [[autobot-backend/orchestration/CAUSAL_EXAMPLE]]

---

## ACTION REQUIRED: Implementation / Verification Reports (8)

One-off reports not linked from anywhere. Review if still relevant.

- [[IMPLEMENTATION_SUMMARY]]
- [[MCP_DISTRIBUTION_SUMMARY]]
- [[VERIFICATION]]
- [[VERIFICATION_REPORT]]
- [[VIRTUAL_SCROLLING_INTEGRATION]]
- [[langchain-1x-verification]]
- [[docs/verification]]
- [[docs/developer/analytics-e2e-verification]]

---

## ACTION REQUIRED: Developer Docs — Need Index Links (21)

These live in `docs/developer/` but are not referenced from [[docs/developer/CLAUDE_RULES]] or any index. Add wikilinks to the developer docs index.

- [[docs/developer/ANSIBLE_ROLE_NAMES]]
- [[docs/developer/CANONICAL_RULES]]
- [[docs/developer/COMPOSABLE_HTTP_PATTERNS]]
- [[docs/developer/CONTAINER_SECURITY]]
- [[docs/developer/DESIGN_SYSTEM]]
- [[docs/developer/FRONTEND_COMPOSABLES]]
- [[docs/developer/HEARTBEAT_SYSTEM]]
- [[docs/developer/I18N_ADDING_LANGUAGE]]
- [[docs/developer/LANGCHAIN_MCP_INTEGRATION]]
- [[docs/developer/MCP_BRIDGE_ISOLATION]]
- [[docs/developer/NOTIFICATION_SUPPRESSION]]
- [[docs/developer/PKI_CA_ROTATION]]
- [[docs/developer/PLUGIN_PUBLISHING_GUIDE]]
- [[docs/developer/PRIMITIVES]]
- [[docs/developer/PROMPT_MIDDLEWARE_GUIDE]]
- [[docs/developer/ROUTER_REGISTRY]]
- [[docs/developer/SINGLE_HOST_DEPLOYMENT]]
- [[docs/developer/WORKTREE_SAFETY_INVESTIGATION]]
- [[docs/developer/frontend-type-generation]]
- [[docs/developer/plugin-boundaries]]
- [[docs/developer/plugin-vs-extension-vs-skill]]

---

## ACTION REQUIRED: Architecture Docs — Need Index Links (5)

Live in `docs/architecture/` but no index points to them.

- [[docs/architecture/agent-belief-state-benchmark]]
- [[docs/architecture/agent-belief-state]]
- [[docs/architecture/chat-state-ssot]]
- [[docs/architecture/npu-pipeline-parallelism]]
- [[docs/architecture/shared-runtime-bag]]

---

## ACTION REQUIRED: Frontend Reports (31)

Mix of accessibility completion reports, theming audits, and composable example docs. Either link from `autobot-frontend/README` or delete if stale.

**Completion reports (likely stale — delete candidates):**
- [[autobot-frontend/ACCESSIBILITY_IMPROVEMENTS]]
- [[autobot-frontend/ACCESSIBILITY_PHASE1_COMPLETE]]
- [[autobot-frontend/ACCESSIBILITY_PHASE2_COMPLETE]]
- [[autobot-frontend/ACCESSIBILITY_PHASE3_COMPLETE]]
- [[autobot-frontend/FRONTEND_ARCHITECTURE_OPTIMIZATION]]
- [[autobot-frontend/FRONTEND_MIGRATION_TRACKING]]
- [[autobot-frontend/STUB_FUNCTIONS_REMEDIATION_PLAN]]
- [[autobot-frontend/STUB_REMEDIATION_PROGRESS]]
- [[autobot-frontend/XTERM_UPGRADE_IMPLEMENTATION]]
- [[autobot-frontend/CONVERSATION_FILE_MANAGER_IMPLEMENTATION]]

**Living docs (link from frontend README):**
- [[autobot-frontend/OPTIMIZATION_OPPORTUNITIES]]
- [[autobot-frontend/TESTING]]
- [[autobot-frontend/THEMING-AUDIT]]
- [[autobot-frontend/THEMING]]

**Composable examples (link from each composable file or delete):**
- `autobot-frontend/src/composables/useAsyncOperation.examples.md`
- `autobot-frontend/src/composables/useClipboard.examples.md`
- `autobot-frontend/src/composables/useConnectionTester.examples.md`
- `autobot-frontend/src/composables/useErrorHandler.api-migration.md`
- `autobot-frontend/src/composables/useErrorHandler.examples.md`
- `autobot-frontend/src/composables/useFormValidation.examples.md`
- `autobot-frontend/src/composables/useKeyboard.examples.md`
- `autobot-frontend/src/composables/useLocalStorage.examples.md`
- `autobot-frontend/src/composables/useModal.examples.md`
- `autobot-frontend/src/composables/usePagination.examples.md`
- `autobot-frontend/src/composables/useTimeout.examples.md`
- `autobot-frontend/src/utils/iconMappings.examples.md`

**Component examples:**
- `autobot-frontend/src/components/examples/AsyncOperationExample.delivery.md`
- `autobot-frontend/src/components/examples/AsyncOperationExample.integration.md`
- `autobot-frontend/src/components/examples/BEFORE_AFTER_COMPARISON.md`
- `autobot-frontend/src/components/examples/QUICK_REFERENCE.md`
- `autobot-frontend/src/components/examples/VISUAL_PREVIEW.md`
- `autobot-frontend/src/composables/__tests__/TEST_RESULTS_useErrorHandler.md`

---

## ACTION REQUIRED: Other Actionable Docs (56)

### Backend docs not linked from backend README
- [[autobot-backend/chat_history/CONTEXT_OVERFLOW_INTEGRATION]]
- [[autobot-backend/code_analysis/docs/ARCHITECTURE]]
- [[autobot-backend/context_aware_decision/COUNTERFACTUAL_DESIGN]]
- [[autobot-backend/docs/STRATIFIED_COMPARISON_EXAMPLES]]
- [[autobot-backend/docs/api/health]]
- [[autobot-backend/docs/backend/llm-fallback]]
- [[autobot-backend/docs/connectors/gitlab-gitea-forgejo]]
- [[autobot-backend/docs/mcp-server]]
- [[autobot-backend/orchestration/ERROR_RECOVERY_API]]
- [[autobot-backend/orchestration/ERROR_RECOVERY_EXAMPLES]]
- [[autobot-backend/services/agent_terminal/ARCHITECTURE]]
- [[autobot-backend/services/agent_terminal/STRUCTURE]]

### Backend builtin skills (SKILL.md — should link from skills index)
- [[autobot-backend/skills/builtin/github_search/SKILL]]
- [[autobot-backend/skills/builtin/rss_reader/SKILL]]
- [[autobot-backend/skills/builtin/web_fetch/SKILL]]
- [[autobot-backend/skills/builtin/youtube_transcript/SKILL]]

### Backend code analysis reports (stale?)
- `autobot-backend/code_analysis/auto-tools/results/vue_improvement_report.md`
- `autobot-backend/code_analysis/auto-tools/results/vue_quality_report.md`

### Docs not linked from docs/ indexes
- [[docs/api/MARKETPLACE_API]]
- [[docs/api/health]]
- [[docs/connectors/onedrive-sharepoint]]
- [[docs/external_apps/RAG_OPTIMIZATION_ASSESSMENT]]
- [[docs/external_apps/Rag_optimization_methods]]
- [[docs/external_apps/ollama_api]]
- [[docs/frontend/RESPONSIVE_DESIGN_GUIDE]]
- [[docs/llc/budget-token-mode]]
- [[docs/operations/doctor]]
- [[docs/planning/PRD_AutoBot_LLC_Module]]
- [[docs/security/CVE_MONITORING]]
- [[docs/security/run-jwt-scopes]]
- [[docs/superpowers/plans/2026-06-01-transcript-export]]
- [[docs/superpowers/plans/2026-06-02-odysseus-improvements]]
- [[docs/superpowers/specs/2026-06-01-transcript-export-design]]
- [[docs/user/canvas]]
- [[docs/voice_toolset_bundles]]

### SLM backend docs
- [[autobot-slm-backend/QUICK_REFERENCE]]
- [[autobot-slm-backend/docs/API_ENDPOINTS]]
- [[autobot-slm-backend/docs/SLM_IMPLEMENTATION]]
- [[autobot-slm-backend/docs/deployment-instructions]]

### MCP tracker docs (not linked from tracker README)
- `autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/CLAUDE_DESKTOP_SETUP.md`
- `autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/IMPLEMENTATION_COMPLETE.md`
- `autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/PRODUCTION_DEPLOYMENT.md`
- `autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/UNFINISHED_TASKS_CORRELATION_REPORT.md`
- `autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/USAGE_EXAMPLES.md`

### Infrastructure config docs
- `autobot-infrastructure/shared/config/environment-files.md`
- `autobot-infrastructure/shared/docker/DEPRECATED.md`
- `autobot-infrastructure/shared/tests/REDIS_SERVICE_MANAGEMENT_TEST_COVERAGE.md`
- `autobot-infrastructure/shared/tests/TEST_SUITE_DOCUMENTATION.md`
- `autobot-infrastructure/shared/tests/performance/PERFORMANCE_BASELINE_SUMMARY.md`
- `autobot-infrastructure/shared/mcp/tools/mcp-task-manager-server/tasks.md`

### Misc
- `.paperclip-work/MVA-2993-design.md`
- `changelog/unreleased/MVA-1099-npu-pipeline-routing.md`
- `data/file_manager_root/Rag_optimization_methods.md`
- `data/file_manager_root/test.md`
- `tasks/lessons.md`

---

## Expected Standalone (No Action)

These are intentionally orphaned by convention:

| Category | Files |
|---|---|
| GitHub templates/SECURITY | 5 |
| Hugo `_index.md` section pages | 43 |
| `README.md` component docs | 94 |
| Agent prompt templates | 91 |
| Playwright/test result reports | 27 |
| SLM Ansible role READMEs | 4 |
| NPU Windows GUI docs | 6 |
| **Total** | **270** |
