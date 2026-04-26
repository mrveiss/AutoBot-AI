# Composable Weakness Remediation — Design Spec

**Date:** 2026-04-26
**Author:** mrveiss
**Status:** Approved

---

## Problem Statement

AutoBot's frontend has ~100 composables accumulated over 182 sessions. A Phase 1 audit identified six categories of weakness:

1. `useAsyncOperation` duplicates `useLoadingState` with a different API — 5 components wired to it
2. `useUnifiedLoading` singleton write API is unwired — `UnifiedLoadingView` reads state that is never set externally
3. ~11 composables call raw `fetchWithAuth` instead of `useFetchEndpoint` / `ApiClient`
4. ~44 Vue components do inline data fetching instead of delegating to composables
5. No `useConfirmDialog` — components manually track `showConfirmDelete = ref(false)` patterns
6. `useEnvironmentAnalysis` (included under weakness 3) uses raw `fetchWithAuth` for a GET that belongs in `useFetchEndpoint`

---

## Classification

Per the dead-code-review framework:

| Item | Classification | Resolution |
|---|---|---|
| `useAsyncOperation` | **Wired duplicate** — 5 real callers, same purpose as `useLoadingState` | `refact`: migrate 5 callers → `useLoadingState.wrap()`, delete file |
| `useUnifiedLoading` write API | **Unwired** — no external callers of `withLoading(key, fn)` | Resolved by refactoring `UnifiedLoadingView` to props-driven; delete composable |
| 11 composables with raw `fetchWithAuth` | **Pattern violation** — should use `useFetchEndpoint` or `ApiClient` | Migrate per-composable |
| 44 components with inline fetching | **Architecture violation** — data fetching belongs in composables | Extract per-component |
| Missing `useConfirmDialog` | **Gap** — repeated manual pattern across components | Create composable + base component |

---

## Issue Structure

All issues created upfront. Implementation in 4 risk-ordered waves.

---

## Wave 1: Dead Code & Overlap Removal (8 issues)

### Tracker: `refact(composables): remove useAsyncOperation — migrate all callers to useLoadingState`

Migration is mechanical: `execute(() => fn())` → `wrap(() => fn())`, `loading` → `isLoading`.

Child issues (one per component):
- `refact(ui): migrate CommandPermissionDialog from useAsyncOperation to useLoadingState`
- `refact(desktop): migrate DesktopInterface from useAsyncOperation to useLoadingState`
- `refact(knowledge): migrate SystemKnowledgeManager from useAsyncOperation to useLoadingState`
- `refact(knowledge): migrate KnowledgeBrowser from useAsyncOperation to useLoadingState`
- `refact(knowledge): migrate FailedVectorizationsManager from useAsyncOperation to useLoadingState`
- `chore(composables): delete useAsyncOperation.ts and AsyncOperationExample.vue after all callers migrated`

### Standalone: `refact(ui): refactor UnifiedLoadingView to props-driven, delete useUnifiedLoading singleton`

**What changes:**
- `UnifiedLoadingView.vue` receives props: `:is-loading`, `:error`, `:message`, `:has-timed-out`, `:timeout-ms` (keeps internal auto-timeout timer)
- `useUnifiedLoading.ts` deleted
- 3 usage sites updated to pass their existing local refs as props:
  - `App.vue` (loading-key: `app-main`)
  - `DesktopInterface.vue` (loading-key: `desktop-vnc`)
  - `PopoutChromiumBrowser.vue` (loading-key: `playwright-connecting`, `browser-session-init`)

---

## Wave 2: fetchWithAuth Migration in Composables (11 issues)

One issue per composable. Migration target determined by HTTP method:

| Composable | HTTP calls | Target |
|---|---|---|
| `analytics/useEnvironmentAnalysis.ts` | GET (with query params) | `useFetchEndpoint` |
| `useVoiceProfiles.ts` | GET list + POST/DELETE mutations | `useFetchEndpoint` (GET) + `ApiClient` (mutations) |
| `analytics/useIndexingJob.ts` | POST start + GET poll | `useBackgroundTask` (pattern already exists) |
| `usePatternAnalysis.ts` | POST start + GET poll + retry | `useBackgroundTask` |
| `analytics/useBugPrediction.ts` | Already uses `useBackgroundTask`; raw helpers remain | `ApiClient` for remaining helpers |
| `analytics/useAnalyticsDebug.ts` | Mixed diagnostic POSTs | `ApiClient` via `useLoadingState.wrap()` |
| `useToolApproval.ts` | POST only | `ApiClient` via `useLoadingState.wrap()` |
| `useWorkflowTemplates.ts` | POST + DELETE | `ApiClient` via `useLoadingState.wrap()` |
| `useVoiceOutput.ts` | POST synthesize | `ApiClient` via `useLoadingState.wrap()` |
| `useVoiceConversation.ts` | POST transcribe | `ApiClient` via `useLoadingState.wrap()` |
| `useCommandApproval.ts` | SSE GET + POST approve | SSE stays `fetchWithAuth`; POST → `ApiClient` |

**Rule:** SSE streaming calls are exempt from `fetchWithAuth` removal — they are a legitimate use case for raw fetch.

---

## Wave 3: Component Inline Fetch Extraction (3 trackers + 44 child issues)

### Tracker A: `refact(knowledge): extract inline fetching from knowledge components`

17 children:

| Component | Calls | Composable |
|---|---|---|
| `KnowledgeBrowser.vue` | 5 | Extend existing KB composables |
| `BackupManager.vue` | 5 | New `useKnowledgeBackups` |
| `KnowledgePromptEditor.vue` | 4 | New `useKnowledgePrompts` |
| `KnowledgeGraph.vue` | 4 | Extend `useKnowledgeGraph` (exists) |
| `FailedVectorizationsManager.vue` | 4 | Extend `useKnowledgeVectorization` (exists) |
| `DeduplicationManager.vue` | 4 | New `useKnowledgeDeduplication` |
| `CategoryEditModal.vue` | 3 | Extend `useKnowledgeCategories` (exists) |
| `KnowledgeSystemDocs.vue` | 3 | New `useKnowledgeDocs` |
| `EntityGraphManager.vue` | 3 | New `useKnowledgeEntities` |
| `SessionOrphanManager.vue` | 2 | New `useKnowledgeOrphans` |
| `MemoryOrphanManager.vue` | 2 | Extend `useKnowledgeOrphans` |
| `KnowledgeCategories.vue` | 2 | Extend `useKnowledgeCategories` (exists) |
| `GraphRAGQuery.vue` | 2 | New `useKnowledgeGraphRAG` |
| `CleanupStatistics.vue` | 2 | New `useKnowledgeCleanup` |
| `KnowledgeStats.vue` | 1 | Extend `useKnowledgeStats` (exists) |
| `KnowledgeMaintenance.vue` | 1 | New `useKnowledgeMaintenance` |
| `EntityExtractor.vue` | 1 | Extend `useKnowledgeEntities` |

### Tracker B: `refact(analytics): extract inline fetching from analytics components`

11 children:

| Component | Calls | Composable |
|---|---|---|
| `CodeQualityDashboard.vue` | 8 | New `useCodeQualityData` |
| `SourceManager.vue` | 7 | New `useAnalyticsSourceManagement` |
| `TechnicalDebtDashboard.vue` | 6 | New `useTechnicalDebtData` |
| `LLMPatternDashboard.vue` | 6 | New `useLLMPatternData` |
| `CodeGenerationDashboard.vue` | 5 | New `useCodeGenerationData` |
| `LogPatternDashboard.vue` | 2 | New `useLogPatternData` |
| `CodebaseAnalytics.vue` | 2 | Extend existing analytics composables |
| `AddSourceModal.vue` | 2 | Extend `useSourceRegistry` (exists) |
| `ShareSourceModal.vue` | 1 | Extend `useSourceRegistry` (exists) |
| `ConversationFlowDashboard.vue` | 1 | New `useConversationFlowData` |
| `CodeEvolutionTimeline.vue` | 1 | Extend existing analytics composables |

### Tracker C: `refact(components): extract inline fetching from other components`

16 children:

| Component | Calls | Composable |
|---|---|---|
| `desktop/PopoutChromiumBrowser.vue` | 9 | New `useBrowserSessionData` |
| `file-browser/FileBrowser.vue` | 7 | New `useFileBrowser` |
| `chat/DocumentationSearchSidebar.vue` | 3 | New `useDocumentationSearch` |
| `chat/TranslationShortcutPanel.vue` | 2 | New `useChatTranslation` |
| `chat/ChatMessages.vue` | 2 | Extend existing chat composables |
| `visualizations/AgentActivityVisualization.vue` | 2 | New `useAgentActivityData` |
| `terminal/Terminal.vue` | 2 | Extend `useTerminalStore` (exists) |
| `security/SecretsManager.vue` | 2 | Extend `useSecretsAuditApi` (exists) |
| `research/CaptchaNotification.vue` | 2 | New `useCaptchaStatus` |
| `visualizations/SystemArchitectureDiagram.vue` | 1 | New `useSystemArchitectureData` |
| `visualizations/ResourceHeatmap.vue` | 1 | New `useResourceMetrics` |
| `ui/HostSelector.vue` | 1 | Extend `useHostSelection` (exists) |
| `ui/CommandPermissionDialog.vue` | 1 | Extend `useCommandApproval` (exists) |
| `terminal/HostSelector.vue` | 1 | Extend `useHostSelection` (exists) |
| `security/ThreatIntelligenceDashboard.vue` | 1 | New `useThreatIntelligence` |
| `collaboration/InviteUserDialog.vue` | 1 | New `useCollaborationInvite` |

---

## Wave 4: New Composable (1 issue)

### `feat(composables): add useConfirmDialog composable`

**Interface:**
```typescript
// composables/useConfirmDialog.ts
export function useConfirmDialog() {
  // confirm(options) shows dialog, returns Promise<boolean>
  confirm(options: { title: string; message: string; confirmLabel?: string; cancelLabel?: string }): Promise<boolean>
  // Reactive state for the paired ConfirmDialog.vue base component
  isOpen: Ref<boolean>
  title: Ref<string>
  message: Ref<string>
  confirmLabel: Ref<string>
  cancelLabel: Ref<string>
  onConfirm: () => void
  onCancel: () => void
}
```

**Pattern replaces:**
```typescript
// Before (in every component)
const showConfirmDelete = ref(false)
const handleDelete = async () => {
  if (!await someConfirm()) return
  ...
}

// After
const { confirm } = useConfirmDialog()
const handleDelete = async () => {
  if (!await confirm({ title: 'Delete?', message: 'This cannot be undone.' })) return
  ...
}
```

Paired with a `ConfirmDialog.vue` base component registered globally or imported where needed.

---

## Implementation Order

| Wave | Risk | Prerequisite |
|---|---|---|
| Wave 1 (dead code) | Low — isolated file changes | None |
| Wave 2 (composable fetchWithAuth) | Medium — composable internals only | Wave 1 complete (correct patterns established) |
| Wave 3 (component extraction) | Medium-high — new composables + component updates | Wave 2 complete (patterns stable) |
| Wave 4 (useConfirmDialog) | Low — additive only | Can run parallel to Wave 3 |

**Batch size:** 3 agents max per batch round.
**Branch target:** All PRs → `Dev_new_gui`.

---

## New Composables Created

| Composable | Location | Purpose |
|---|---|---|
| `useKnowledgeBackups` | `composables/knowledge/` | KB backup/restore operations |
| `useKnowledgePrompts` | `composables/knowledge/` | Prompt CRUD for KB |
| `useKnowledgeDeduplication` | `composables/knowledge/` | Deduplication job management |
| `useKnowledgeDocs` | `composables/knowledge/` | KB system docs fetching |
| `useKnowledgeEntities` | `composables/knowledge/` | Entity graph operations |
| `useKnowledgeOrphans` | `composables/knowledge/` | Session + memory orphan management |
| `useKnowledgeGraphRAG` | `composables/knowledge/` | GraphRAG query operations |
| `useKnowledgeCleanup` | `composables/knowledge/` | Cleanup statistics |
| `useKnowledgeMaintenance` | `composables/knowledge/` | Maintenance operations |
| `useCodeQualityData` | `composables/analytics/` | Code quality dashboard data |
| `useAnalyticsSourceManagement` | `composables/analytics/` | Source CRUD + management |
| `useTechnicalDebtData` | `composables/analytics/` | Technical debt analysis data |
| `useLLMPatternData` | `composables/analytics/` | LLM pattern dashboard data |
| `useCodeGenerationData` | `composables/analytics/` | Code generation dashboard data |
| `useLogPatternData` | `composables/analytics/` | Log pattern dashboard data |
| `useConversationFlowData` | `composables/analytics/` | Conversation flow data |
| `useBrowserSessionData` | `composables/` | Chromium browser session management |
| `useFileBrowser` | `composables/` | File browser operations |
| `useDocumentationSearch` | `composables/` | Documentation search |
| `useChatTranslation` | `composables/` | Chat translation shortcuts |
| `useAgentActivityData` | `composables/` | Agent activity visualization data |
| `useCaptchaStatus` | `composables/` | Captcha detection/notification |
| `useSystemArchitectureData` | `composables/` | System architecture diagram data |
| `useResourceMetrics` | `composables/` | Resource heatmap metrics |
| `useThreatIntelligence` | `composables/` | Threat intelligence data |
| `useCollaborationInvite` | `composables/` | Collaboration invite operations |
| `useConfirmDialog` | `composables/` | Reusable confirm dialog promise |

---

## Total Issue Count

| Wave | Trackers | Children | Standalone | Total |
|---|---|---|---|---|
| Wave 1 | 1 | 5 | 2 | 8 |
| Wave 2 | — | — | 11 | 11 |
| Wave 3 | 3 | 44 | — | 47 |
| Wave 4 | — | — | 1 | 1 |
| **Total** | **4** | **49** | **14** | **67** |
