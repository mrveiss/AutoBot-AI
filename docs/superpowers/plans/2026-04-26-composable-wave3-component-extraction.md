# Composable Wave 3 — Component Inline Fetch Extraction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract inline `fetchWithAuth`/`apiClient` calls from 44 Vue components into dedicated composables, eliminating direct data fetching from component setup/methods. Master tracker: #6006.

**Architecture:** Each component's fetch calls move to a composable in `src/composables/` (or a sub-directory). New composables use `useFetchEndpoint` (reads) or `ApiClient` + `useLoadingState.wrap()` (mutations). Components import composable and call its functions — zero `fetchWithAuth` in component `<script setup>`.

**Tech Stack:** Vue 3, TypeScript, `useFetchEndpoint`, `ApiClient`, `useLoadingState`, `getApiBase()` from `@/config/ssot-config`

---

## Extraction pattern (read before all tasks)

```typescript
// BEFORE — component has inline fetch
// src/components/knowledge/SomeComponent.vue
const data = ref<MyType | null>(null)
const isLoading = ref(false)
const loadData = async () => {
  isLoading.value = true
  const resp = await fetchWithAuth(`${backendUrl}/api/endpoint`)
  data.value = (await resp.json()).result
  isLoading.value = false
}

// AFTER — new composable
// src/composables/knowledge/useMyComposable.ts
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { getApiBase } from '@/config/ssot-config'
export function useMyComposable() {
  const endpoint = useFetchEndpoint<RawType, MyType>({
    path: '/api/endpoint',
    pickData: (raw) => raw.result ?? null,
  })
  return {
    data: endpoint.data,
    isLoading: endpoint.isLoading,
    error: endpoint.error,
    load: endpoint.load,
  }
}

// AFTER — component imports composable
import { useMyComposable } from '@/composables/knowledge/useMyComposable'
const { data, isLoading, load } = useMyComposable()
onMounted(load)
```

For mutations in components:
```typescript
// New composable
import apiClient from '@/utils/ApiClient'
import { useLoadingState } from '@/composables/useLoadingState'
export function useMyComposable() {
  const { isLoading: isSubmitting, wrap } = useLoadingState()
  const submit = (payload: Payload) =>
    wrap(() => apiClient.post<Result>(`${getApiBase()}/api/endpoint`, payload))
  return { isSubmitting, submit }
}
```

---

## Task 1: Create GitHub tracker and child issues

- [ ] **Step 1: Create Tracker A (knowledge)**

```bash
gh issue create \
  --title "tracker(knowledge): extract inline fetching from knowledge components" \
  --label "refactor,frontend,tech-debt" \
  --body "## Children
- [ ] KnowledgeBrowser.vue (5 calls) — extend existing KB composables
- [ ] BackupManager.vue (5 calls) — new useKnowledgeBackups
- [ ] KnowledgePromptEditor.vue (4 calls) — new useKnowledgePrompts
- [ ] KnowledgeGraph.vue (4 calls) — extend useKnowledgeGraph
- [ ] FailedVectorizationsManager.vue (4 calls) — extend useKnowledgeVectorization
- [ ] DeduplicationManager.vue (4 calls) — new useKnowledgeDeduplication
- [ ] CategoryEditModal.vue (3 calls) — extend useKnowledgeCategories
- [ ] KnowledgeSystemDocs.vue (3 calls) — new useKnowledgeDocs
- [ ] EntityGraphManager.vue (3 calls) — new useKnowledgeEntities
- [ ] SessionOrphanManager.vue (2 calls) — new useKnowledgeOrphans
- [ ] MemoryOrphanManager.vue (2 calls) — extend useKnowledgeOrphans
- [ ] KnowledgeCategories.vue (2 calls) — extend useKnowledgeCategories
- [ ] GraphRAGQuery.vue (2 calls) — new useKnowledgeGraphRAG
- [ ] CleanupStatistics.vue (2 calls) — new useKnowledgeCleanup
- [ ] KnowledgeStats.vue (1 call) — extend useKnowledgeStats
- [ ] KnowledgeMaintenance.vue (1 call) — new useKnowledgeMaintenance
- [ ] EntityExtractor.vue (1 call) — extend useKnowledgeEntities

Master tracker: #6006"
```

- [ ] **Step 2: Create Tracker B (analytics)**

```bash
gh issue create \
  --title "tracker(analytics): extract inline fetching from analytics components" \
  --label "refactor,frontend,tech-debt" \
  --body "## Children
- [ ] CodeQualityDashboard.vue (8 calls) — new useCodeQualityData
- [ ] SourceManager.vue (7 calls) — new useAnalyticsSourceManagement
- [ ] TechnicalDebtDashboard.vue (6 calls) — new useTechnicalDebtData
- [ ] LLMPatternDashboard.vue (6 calls) — new useLLMPatternData
- [ ] CodeGenerationDashboard.vue (5 calls) — new useCodeGenerationData
- [ ] LogPatternDashboard.vue (2 calls) — new useLogPatternData
- [ ] CodebaseAnalytics.vue (2 calls) — extend existing analytics composables
- [ ] AddSourceModal.vue (2 calls) — extend useSourceRegistry
- [ ] ShareSourceModal.vue (1 call) — extend useSourceRegistry
- [ ] ConversationFlowDashboard.vue (1 call) — new useConversationFlowData
- [ ] CodeEvolutionTimeline.vue (1 call) — extend existing analytics composables

Master tracker: #6006"
```

- [ ] **Step 3: Create Tracker C (other)**

```bash
gh issue create \
  --title "tracker(components): extract inline fetching from other components" \
  --label "refactor,frontend,tech-debt" \
  --body "## Children
- [ ] desktop/PopoutChromiumBrowser.vue (9 calls) — new useBrowserSessionData
- [ ] file-browser/FileBrowser.vue (7 calls) — new useFileBrowser
- [ ] chat/DocumentationSearchSidebar.vue (3 calls) — new useDocumentationSearch
- [ ] chat/TranslationShortcutPanel.vue (2 calls) — new useChatTranslation
- [ ] chat/ChatMessages.vue (2 calls) — extend existing chat composables
- [ ] visualizations/AgentActivityVisualization.vue (2 calls) — new useAgentActivityData
- [ ] terminal/Terminal.vue (2 calls) — extend useTerminalStore
- [ ] security/SecretsManager.vue (2 calls) — extend useSecretsAuditApi
- [ ] research/CaptchaNotification.vue (2 calls) — new useCaptchaStatus
- [ ] visualizations/SystemArchitectureDiagram.vue (1 call) — new useSystemArchitectureData
- [ ] visualizations/ResourceHeatmap.vue (1 call) — new useResourceMetrics
- [ ] ui/HostSelector.vue (1 call) — extend useHostSelection
- [ ] ui/CommandPermissionDialog.vue (1 call) — extend useCommandApproval
- [ ] terminal/HostSelector.vue (1 call) — extend useHostSelection
- [ ] security/ThreatIntelligenceDashboard.vue (1 call) — new useThreatIntelligence
- [ ] collaboration/InviteUserDialog.vue (1 call) — new useCollaborationInvite

Master tracker: #6006"
```

- [ ] **Step 4: Create child issues for each component**

For each component listed above, create a child issue:
```bash
gh issue create \
  --title "refact(<domain>): extract inline fetching from <ComponentName> to <composableName>" \
  --label "refactor,frontend,tech-debt" \
  --body "Component: src/components/<path>/<ComponentName>.vue
Target composable: src/composables/<path>/<composableName>.ts
Tracker: #<tracker-issue-number>
Master tracker: #6006

## Steps
1. Read component and identify all fetchWithAuth/apiClient calls
2. Create or extend target composable with those functions
3. Update component to import and use composable
4. Type-check: npx vue-tsc --noEmit -p tsconfig.app.json
5. Verify: grep fetchWithAuth src/components/<path>/<ComponentName>.vue → no output"
```

---

## Task 2: Extract BackupManager.vue (representative full example)

This task is shown in full detail. All subsequent component tasks follow the same 8 steps.

**Files:**
- Create: `autobot-frontend/src/composables/knowledge/useKnowledgeBackups.ts`
- Modify: `autobot-frontend/src/components/knowledge/BackupManager.vue`

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Read the component to identify all inline fetch calls**

```bash
grep -n "fetchWithAuth\|apiClient\." autobot-frontend/src/components/knowledge/BackupManager.vue
```

Note each: URL, method, what it does, what data it returns.

- [ ] **Step 3: Create useKnowledgeBackups.ts**

```typescript
// autobot-frontend/src/composables/knowledge/useKnowledgeBackups.ts
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useLoadingState } from '@/composables/useLoadingState'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

export interface BackupInfo {
  // Fill from reading BackupManager.vue — what shape does the backup list return?
  id: string
  created_at: string
  size: number
  status: string
}

export function useKnowledgeBackups() {
  // Reads (GET) → useFetchEndpoint
  const backupsEndpoint = useFetchEndpoint<{ backups: BackupInfo[] }, BackupInfo[]>({
    path: '/knowledge_base/backups',
    pickData: (raw) => raw.backups ?? null,
  })

  // Mutations (POST/DELETE) → ApiClient + useLoadingState
  const { isLoading: isCreating, wrap: wrapCreate } = useLoadingState()
  const { isLoading: isRestoring, wrap: wrapRestore } = useLoadingState()
  const { isLoading: isDeleting, wrap: wrapDelete } = useLoadingState()

  const createBackup = () =>
    wrapCreate(() => apiClient.post(`${getApiBase()}/knowledge_base/backups`))

  const restoreBackup = (backupId: string) =>
    wrapRestore(() => apiClient.post(`${getApiBase()}/knowledge_base/backups/${backupId}/restore`))

  const deleteBackup = (backupId: string) =>
    wrapDelete(() => apiClient.delete(`${getApiBase()}/knowledge_base/backups/${backupId}`))

  return {
    backups: backupsEndpoint.data,
    isLoadingBackups: backupsEndpoint.isLoading,
    backupsError: backupsEndpoint.error,
    loadBackups: backupsEndpoint.load,
    isCreating,
    createBackup,
    isRestoring,
    restoreBackup,
    isDeleting,
    deleteBackup,
  }
}
```

**Important:** Read the actual component to fill in correct URL paths, request/response shapes, and method types. The above is the structural template.

- [ ] **Step 4: Write a basic test**

```typescript
// autobot-frontend/src/composables/__tests__/useKnowledgeBackups.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useKnowledgeBackups } from '../knowledge/useKnowledgeBackups'

vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: () => ({
    data: { value: null },
    isLoading: { value: false },
    error: { value: null },
    load: vi.fn(),
  }),
}))
vi.mock('@/utils/ApiClient', () => ({
  default: { post: vi.fn().mockResolvedValue({}), delete: vi.fn().mockResolvedValue({}) },
}))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => 'http://localhost:8001' }))

describe('useKnowledgeBackups', () => {
  it('exposes loadBackups, createBackup, restoreBackup, deleteBackup', () => {
    const kb = useKnowledgeBackups()
    expect(typeof kb.loadBackups).toBe('function')
    expect(typeof kb.createBackup).toBe('function')
    expect(typeof kb.restoreBackup).toBe('function')
    expect(typeof kb.deleteBackup).toBe('function')
  })

  it('isCreating starts false', () => {
    const { isCreating } = useKnowledgeBackups()
    expect(isCreating.value).toBe(false)
  })
})
```

- [ ] **Step 5: Run tests**

```bash
cd autobot-frontend && npx vitest run src/composables/__tests__/useKnowledgeBackups.test.ts
```
Expected: PASS.

- [ ] **Step 6: Update BackupManager.vue**

Remove all `fetchWithAuth` / manual loading imports. Add:
```typescript
import { useKnowledgeBackups } from '@/composables/knowledge/useKnowledgeBackups'
const {
  backups, isLoadingBackups, loadBackups,
  isCreating, createBackup,
  isRestoring, restoreBackup,
  isDeleting, deleteBackup,
} = useKnowledgeBackups()
```
Remove the inline fetch functions and their `ref` declarations. Replace template bindings.

- [ ] **Step 7: Type-check and verify**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "BackupManager"
grep "fetchWithAuth\|await apiClient" autobot-frontend/src/components/knowledge/BackupManager.vue
```
Expected: no type errors, no fetchWithAuth lines.

- [ ] **Step 8: Commit**

```bash
git add autobot-frontend/src/composables/knowledge/useKnowledgeBackups.ts \
        autobot-frontend/src/composables/__tests__/useKnowledgeBackups.test.ts \
        autobot-frontend/src/components/knowledge/BackupManager.vue
git commit -m "refact(knowledge): extract BackupManager inline fetching to useKnowledgeBackups (#ISSUE)"
```

---

## Tasks 3–44: Remaining components (follow Task 2's 8-step structure)

Each task: create worktree → grep inline calls → create/extend composable → write test → run test → update component → type-check + verify → commit.

### Tracker A — Knowledge components

| Task | Component | Calls | Action | New composable |
|---|---|---|---|---|
| 3 | `KnowledgeBrowser.vue` | 5 | Extend existing KB composables — check which KB composables are already imported | none new |
| 4 | `KnowledgePromptEditor.vue` | 4 | New composable | `useKnowledgePrompts.ts` |
| 5 | `KnowledgeGraph.vue` | 4 | Extend `useKnowledgeGraph.ts` — add missing methods | none new |
| 6 | `FailedVectorizationsManager.vue` | 4 | Extend `useKnowledgeVectorization.ts` | none new |
| 7 | `DeduplicationManager.vue` | 4 | New composable | `useKnowledgeDeduplication.ts` |
| 8 | `CategoryEditModal.vue` | 3 | Extend `useKnowledgeCategories.ts` | none new |
| 9 | `KnowledgeSystemDocs.vue` | 3 | New composable | `useKnowledgeDocs.ts` |
| 10 | `EntityGraphManager.vue` | 3 | New composable | `useKnowledgeEntities.ts` |
| 11 | `SessionOrphanManager.vue` | 2 | New composable | `useKnowledgeOrphans.ts` |
| 12 | `MemoryOrphanManager.vue` | 2 | Extend `useKnowledgeOrphans.ts` | none new |
| 13 | `KnowledgeCategories.vue` | 2 | Extend `useKnowledgeCategories.ts` | none new |
| 14 | `GraphRAGQuery.vue` | 2 | New composable | `useKnowledgeGraphRAG.ts` |
| 15 | `CleanupStatistics.vue` | 2 | New composable | `useKnowledgeCleanup.ts` |
| 16 | `KnowledgeStats.vue` | 1 | Extend `useKnowledgeStats.ts` | none new |
| 17 | `KnowledgeMaintenance.vue` | 1 | New composable | `useKnowledgeMaintenance.ts` |
| 18 | `EntityExtractor.vue` | 1 | Extend `useKnowledgeEntities.ts` | none new |

### Tracker B — Analytics components

| Task | Component | Calls | Action | New composable |
|---|---|---|---|---|
| 19 | `CodeQualityDashboard.vue` | 8 | New composable | `analytics/useCodeQualityData.ts` |
| 20 | `SourceManager.vue` | 7 | New composable | `analytics/useAnalyticsSourceManagement.ts` |
| 21 | `TechnicalDebtDashboard.vue` | 6 | New composable | `analytics/useTechnicalDebtData.ts` |
| 22 | `LLMPatternDashboard.vue` | 6 | New composable | `analytics/useLLMPatternData.ts` |
| 23 | `CodeGenerationDashboard.vue` | 5 | New composable | `analytics/useCodeGenerationData.ts` |
| 24 | `LogPatternDashboard.vue` | 2 | New composable | `analytics/useLogPatternData.ts` |
| 25 | `CodebaseAnalytics.vue` | 2 | Extend existing analytics composables | none new |
| 26 | `AddSourceModal.vue` | 2 | Extend `analytics/useSourceRegistry.ts` | none new |
| 27 | `ShareSourceModal.vue` | 1 | Extend `analytics/useSourceRegistry.ts` | none new |
| 28 | `ConversationFlowDashboard.vue` | 1 | New composable | `analytics/useConversationFlowData.ts` |
| 29 | `CodeEvolutionTimeline.vue` | 1 | Extend existing analytics composables | none new |

### Tracker C — Other components

| Task | Component | Calls | Action | New composable |
|---|---|---|---|---|
| 30 | `desktop/PopoutChromiumBrowser.vue` | 9 | New composable | `useBrowserSessionData.ts` |
| 31 | `file-browser/FileBrowser.vue` | 7 | New composable | `useFileBrowser.ts` |
| 32 | `chat/DocumentationSearchSidebar.vue` | 3 | New composable | `useDocumentationSearch.ts` |
| 33 | `chat/TranslationShortcutPanel.vue` | 2 | New composable | `useChatTranslation.ts` |
| 34 | `chat/ChatMessages.vue` | 2 | Extend existing chat composables | none new |
| 35 | `visualizations/AgentActivityVisualization.vue` | 2 | New composable | `useAgentActivityData.ts` |
| 36 | `terminal/Terminal.vue` | 2 | Extend `useTerminalStore.ts` | none new |
| 37 | `security/SecretsManager.vue` | 2 | Extend `useSecretsAuditApi.ts` | none new |
| 38 | `research/CaptchaNotification.vue` | 2 | New composable | `useCaptchaStatus.ts` |
| 39 | `visualizations/SystemArchitectureDiagram.vue` | 1 | New composable | `useSystemArchitectureData.ts` |
| 40 | `visualizations/ResourceHeatmap.vue` | 1 | New composable | `useResourceMetrics.ts` |
| 41 | `ui/HostSelector.vue` | 1 | Extend `useHostSelection.ts` | none new |
| 42 | `ui/CommandPermissionDialog.vue` | 1 | Extend `useCommandApproval.ts` | none new |
| 43 | `terminal/HostSelector.vue` | 1 | Extend `useHostSelection.ts` | none new |
| 44 | `security/ThreatIntelligenceDashboard.vue` | 1 | New composable | `useThreatIntelligence.ts` |
| 45 | `collaboration/InviteUserDialog.vue` | 1 | New composable | `useCollaborationInvite.ts` |

---

## Per-task checklist (apply to every task 3–45)

For each component listed above:

- [ ] **Grep inline calls:** `grep -n "fetchWithAuth\|apiClient\." src/components/<path>/<Component>.vue`
- [ ] **Identify:** URL, method, response shape for each call
- [ ] **Create or extend composable:** Follow extraction pattern at top of this document
- [ ] **Write minimal test:** At minimum test that functions exist and loading starts false
- [ ] **Run test:** `npx vitest run src/composables/__tests__/<composable>.test.ts`
- [ ] **Update component:** Remove inline fetch, import composable, use returned refs
- [ ] **Type-check:** `npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "<ComponentName>"`
- [ ] **Verify clean:** `grep "fetchWithAuth\|await apiClient\." src/components/<path>/<Component>.vue` → no output
- [ ] **Commit:** `git commit -m "refact(<domain>): extract <Component> inline fetching to <composable> (#ISSUE)"`

---

## Final verification for Wave 3

- [ ] **No inline fetching remains in any component:**

```bash
grep -r "await fetchWithAuth\|await apiClient\." autobot-frontend/src/components --include="*.vue" | wc -l
```
Expected: 0.

- [ ] **All new composable files exist:**

```bash
for f in \
  useKnowledgeBackups useKnowledgePrompts useKnowledgeDeduplication \
  useKnowledgeDocs useKnowledgeEntities useKnowledgeOrphans \
  useKnowledgeGraphRAG useKnowledgeCleanup useKnowledgeMaintenance; do
  ls autobot-frontend/src/composables/knowledge/${f}.ts 2>/dev/null || echo "MISSING: $f"
done
for f in \
  useCodeQualityData useAnalyticsSourceManagement useTechnicalDebtData \
  useLLMPatternData useCodeGenerationData useLogPatternData useConversationFlowData; do
  ls autobot-frontend/src/composables/analytics/${f}.ts 2>/dev/null || echo "MISSING: $f"
done
for f in \
  useBrowserSessionData useFileBrowser useDocumentationSearch useChatTranslation \
  useAgentActivityData useCaptchaStatus useSystemArchitectureData \
  useResourceMetrics useThreatIntelligence useCollaborationInvite; do
  ls autobot-frontend/src/composables/${f}.ts 2>/dev/null || echo "MISSING: $f"
done
```
Expected: all files found, no MISSING lines.

- [ ] **Full type-check:**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
```
Expected: 0 new errors vs Wave 2 baseline.
