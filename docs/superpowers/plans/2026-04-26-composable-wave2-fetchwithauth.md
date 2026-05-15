# Composable Wave 2 — fetchWithAuth Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate 12 composables from raw `fetchWithAuth` calls to `useFetchEndpoint` (GET reads) or `ApiClient` via `useLoadingState.wrap()` (mutations). Eliminates missing AbortController, missing race-condition guards, and inconsistent error handling.

**Architecture:** Migration target per composable determined by HTTP method. GET reads → `useFetchEndpoint` (gets race safety + abort for free). POST/DELETE mutations → `ApiClient.post/delete()` inside `useLoadingState.wrap()`. SSE calls stay as `fetchWithAuth` (exempt). `useBackgroundTask` composables (POST-start + GET-poll) → `useBackgroundTask` pattern already exists. Master tracker: #6006.

**Tech Stack:** Vue 3, TypeScript, `useFetchEndpoint`, `useApiResource`, `useLoadingState`, `useBackgroundTask`, `ApiClient` (`src/utils/ApiClient.ts`), `fetchWithAuth` (`src/utils/fetchWithAuth.ts`)

---

## Migration patterns (read before all tasks)

### Pattern A — GET read → useFetchEndpoint

```typescript
// BEFORE
const data = ref<MyType | null>(null)
const isLoading = ref(false)
const error = ref('')
const load = async () => {
  isLoading.value = true
  const resp = await fetchWithAuth(`${backendUrl}/api/endpoint`)
  if (!resp.ok) throw new Error(`${resp.status}`)
  const json = await resp.json()
  data.value = json.result
  isLoading.value = false
}

// AFTER
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
const endpoint = useFetchEndpoint<RawResponse, MyType>({
  path: '/api/endpoint',
  pickData: (raw) => raw.result ?? null,
})
// endpoint.data, endpoint.isLoading, endpoint.error, endpoint.load() are reactive
```

### Pattern B — POST/DELETE mutation → ApiClient + useLoadingState

```typescript
// BEFORE
const isSubmitting = ref(false)
const submit = async (payload: Payload) => {
  isSubmitting.value = true
  const resp = await fetchWithAuth(`${backendUrl}/api/endpoint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`${resp.status}`)
  const json = await resp.json()
  isSubmitting.value = false
  return json
}

// AFTER
import apiClient from '@/utils/ApiClient'
import { useLoadingState } from '@/composables/useLoadingState'
import { getApiBase } from '@/config/ssot-config'
const { isLoading: isSubmitting, wrap } = useLoadingState()
const submit = async (payload: Payload) => {
  return wrap(() => apiClient.post<ResponseType>(`${getApiBase()}/api/endpoint`, payload))
}
```

### Pattern C — POST-start + GET-poll → useBackgroundTask

```typescript
// Composable already wraps POST /analyze + GET /status/{id} polling
// See src/composables/useBackgroundTask.ts
import { useBackgroundTask } from '@/composables/useBackgroundTask'
const task = useBackgroundTask('/api/analytics/my-endpoint')
await task.start()  // POSTs to /analyze, polls /status/{id}
// task.result, task.running, task.error are reactive
```

---

## Task 1: Create GitHub issues for Wave 2

- [ ] **Step 1: Create 12 issues**

```bash
for title in \
  "refact(composables): migrate useEnvironmentAnalysis fetchWithAuth GET to useFetchEndpoint" \
  "refact(composables): migrate useVoiceProfiles fetchWithAuth to useFetchEndpoint + ApiClient" \
  "refact(composables): migrate useIndexingJob fetchWithAuth to useBackgroundTask pattern" \
  "refact(composables): migrate usePatternAnalysis fetchWithAuth to useBackgroundTask pattern" \
  "refact(composables): migrate useBugPrediction remaining fetchWithAuth helpers to ApiClient" \
  "refact(composables): migrate useAnalyticsDebug fetchWithAuth to ApiClient + useLoadingState" \
  "refact(composables): migrate useToolApproval fetchWithAuth POST to ApiClient + useLoadingState" \
  "refact(composables): migrate useWorkflowTemplates fetchWithAuth to ApiClient + useLoadingState" \
  "refact(composables): migrate useVoiceOutput fetchWithAuth POST to ApiClient + useLoadingState" \
  "refact(composables): migrate useVoiceConversation fetchWithAuth POST to ApiClient + useLoadingState" \
  "refact(composables): migrate useCommandApproval fetchWithAuth POST to ApiClient (SSE stays)" \
  "refact(composables): migrate useBackgroundTask fetchWithAuth helpers to ApiClient"; do
  gh issue create --title "$title" --label "refactor,frontend,tech-debt" \
    --body "Part of tracker #6006. See design spec: docs/superpowers/specs/2026-04-26-composable-weakness-remediation-design.md"
done
```

Record issue numbers for branch names.

---

## Task 2: Migrate useEnvironmentAnalysis (GET → useFetchEndpoint)

**Files:**
- Modify: `autobot-frontend/src/composables/analytics/useEnvironmentAnalysis.ts`

Current: raw `fetchWithAuth` GET with manually-built URL, manual `isLoading`, manual error string.
Target: `useFetchEndpoint` with `body()` factory for POST-style params or query string builder.

Note: This endpoint takes query params (`?path=...&use_llm_filter=...`). `useFetchEndpoint` supports GET with a `body()` factory — but for query params, build the URL path dynamically in the `path` option.

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Read the file to understand current structure**

```bash
cat autobot-frontend/src/composables/analytics/useEnvironmentAnalysis.ts
```

- [ ] **Step 3: Replace fetchWithAuth GET with useFetchEndpoint**

Remove imports: `fetchWithAuth`, `appConfig`, and manual `ref` for loading/error.
Add imports: `useFetchEndpoint`.

Replace the `loadEnvironmentAnalysis` function body. The path includes reactive query params, so use a computed `path`:

```typescript
import { ref, computed } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'
import { getConfig } from '@/config/ssot-config'
import type { UseCodeIntelAnalysisDeps, EnvironmentAnalysisResult } from './codeIntelTypes'

const logger = createLogger('useEnvironmentAnalysis')

export function useEnvironmentAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath, withSourceId } = deps

  const environmentAnalysis = ref<EnvironmentAnalysisResult | null>(null)
  const useAiFiltering = ref(false)
  const aiFilteringModel = ref(getConfig().llm.defaultModel)
  const aiFilteringPriority = ref('high')
  const llmFilteringResult = ref<{ ... } | null>(null)  // keep existing type

  const envEndpoint = useFetchEndpoint<Record<string, unknown>, EnvironmentAnalysisResult | null>({
    path: '/api/analytics/codebase/env-analysis',
    scopeToSource: false,
    body: () => ({
      path: rootPath.value,
      use_llm_filter: useAiFiltering.value || undefined,
      llm_model: useAiFiltering.value ? aiFilteringModel.value : undefined,
      filter_priority: useAiFiltering.value ? aiFilteringPriority.value : undefined,
    }),
    method: 'POST',  // or keep as GET with query string — check what backend expects
    pickData: (raw) => {
      if (raw.status === 'no_data') return null
      if (raw.status !== 'success') return null
      if (raw.llm_filtering) llmFilteringResult.value = raw.llm_filtering as any
      return {
        total_hardcoded_values: (raw.total_hardcoded_values as number) || 0,
        high_priority_count: (raw.high_priority_count as number) || 0,
        recommendations_count: (raw.recommendations_count as number) || 0,
        categories: (raw.categories as Record<string, unknown>) || {},
        analysis_time_seconds: (raw.analysis_time_seconds as number) || 0,
        hardcoded_values: (raw.hardcoded_values as unknown[]) || [],
        recommendations: (raw.recommendations as unknown[]) || [],
      } as EnvironmentAnalysisResult
    },
    onSuccess: (data) => { environmentAnalysis.value = data },
    onNoData: () => { environmentAnalysis.value = null },
  })

  const loadEnvironmentAnalysis = () => {
    if (!rootPath.value) return
    llmFilteringResult.value = null
    envEndpoint.load()
  }

  return {
    environmentAnalysis,
    loadingEnvAnalysis: envEndpoint.isLoading,
    envAnalysisError: envEndpoint.error,
    useAiFiltering,
    aiFilteringModel,
    aiFilteringPriority,
    llmFilteringResult,
    loadEnvironmentAnalysis,
  }
}
```

**Note:** Check whether the backend endpoint `/api/analytics/codebase/env-analysis` accepts GET with query params or POST with JSON body. Read `autobot-backend/api/analytics.py` if unsure. Match the existing behavior exactly.

- [ ] **Step 4: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "useEnvironmentAnalysis"
```
Expected: no errors.

- [ ] **Step 5: Verify no fetchWithAuth import remains**

```bash
grep "fetchWithAuth\|appConfig" autobot-frontend/src/composables/analytics/useEnvironmentAnalysis.ts
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/composables/analytics/useEnvironmentAnalysis.ts
git commit -m "refact(composables): migrate useEnvironmentAnalysis fetchWithAuth GET to useFetchEndpoint (#ISSUE)"
```

---

## Task 3: Migrate useVoiceProfiles (GET + mutations)

**Files:**
- Modify: `autobot-frontend/src/composables/useVoiceProfiles.ts`

Current: GET voices → `fetchWithAuth`; POST create voice → `fetchWithAuth`; DELETE voice → `fetchWithAuth`; GET active personality → `fetchWithAuth`.

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Read the file**

```bash
cat autobot-frontend/src/composables/useVoiceProfiles.ts
```

- [ ] **Step 3: Replace GET voices fetch with useFetchEndpoint**

The `fetchVoices()` function is a read. Wrap it:

```typescript
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

// Replace manual fetchVoices() with:
const voicesEndpoint = useFetchEndpoint<{ voices: VoiceProfile[] }, VoiceProfile[]>({
  path: '/voice/voices',
  pickData: (raw) => raw.voices ?? null,
})
// voicesEndpoint.data = Ref<VoiceProfile[] | null>
// voicesEndpoint.isLoading, voicesEndpoint.load()
```

- [ ] **Step 4: Replace POST/DELETE mutations with ApiClient**

```typescript
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

// Create voice:
const createVoice = (payload: CreateVoicePayload) =>
  wrap(() => apiClient.post(`${getApiBase()}/voice/voices/create`, payload))

// Delete voice:
const deleteVoice = (voiceId: string) =>
  wrap(() => apiClient.delete(`${getApiBase()}/voice/voices/${voiceId}`))
```

Use the existing `useLoadingState` that the file already imports.

- [ ] **Step 5: Replace GET active personality with useFetchEndpoint**

```typescript
const personalityEndpoint = useFetchEndpoint<{ personality: string }, string>({
  path: '/personality/active',
  pickData: (raw) => raw.personality ?? null,
})
```

- [ ] **Step 6: Type-check and verify**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "useVoiceProfiles"
grep "fetchWithAuth" autobot-frontend/src/composables/useVoiceProfiles.ts
```
Expected for grep: no output.

- [ ] **Step 7: Commit**

```bash
git add autobot-frontend/src/composables/useVoiceProfiles.ts
git commit -m "refact(composables): migrate useVoiceProfiles fetchWithAuth to useFetchEndpoint + ApiClient (#ISSUE)"
```

---

## Task 4: Migrate useIndexingJob (POST-start + GET-poll → useBackgroundTask)

**Files:**
- Modify: `autobot-frontend/src/composables/analytics/useIndexingJob.ts`

Current: 469 lines, manually implements POST-start + GET-poll with `fetchWithAuth`. `useBackgroundTask` already exists and does exactly this.

- [ ] **Step 1: Create worktree and read file**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
cat autobot-frontend/src/composables/analytics/useIndexingJob.ts
```

- [ ] **Step 2: Identify the base URL used for the indexing job**

Look for the endpoint paths (e.g., `/api/analytics/codebase/indexing`). This becomes the `baseUrl` argument to `useBackgroundTask`.

- [ ] **Step 3: Replace manual POST-poll with useBackgroundTask**

```typescript
import { useBackgroundTask } from '@/composables/useBackgroundTask'

// Replace manual indexing task management with:
const indexingTask = useBackgroundTask('/api/analytics/codebase/indexing')
// indexingTask.start()  — POSTs to /analyze, polls /status/{id}
// indexingTask.result   — the completed result
// indexingTask.running  — Ref<boolean>
// indexingTask.error    — Ref<string | null>
// indexingTask.progress — Ref<number>
```

Keep any additional UI state (source selection, etc.) that isn't part of the task lifecycle.

- [ ] **Step 4: Update callers within the file**

Replace `startIndexing()` / `pollStatus()` / manual interval management with `indexingTask.start()`.

- [ ] **Step 5: Verify callers of useIndexingJob haven't broken**

```bash
grep -r "useIndexingJob" autobot-frontend/src --include="*.ts" --include="*.vue" | grep -v "useIndexingJob\.ts"
```
Check each caller still receives the expected returned shape.

- [ ] **Step 6: Type-check and verify**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "useIndexingJob"
grep "fetchWithAuth" autobot-frontend/src/composables/analytics/useIndexingJob.ts
```

- [ ] **Step 7: Commit**

```bash
git add autobot-frontend/src/composables/analytics/useIndexingJob.ts
git commit -m "refact(composables): migrate useIndexingJob fetchWithAuth to useBackgroundTask pattern (#ISSUE)"
```

---

## Tasks 5–12: Remaining composables (follow same structure)

Each task follows the same 7-step structure: create worktree → read file → apply pattern → type-check → verify clean → commit. The specific pattern per composable:

### Task 5: usePatternAnalysis → useBackgroundTask

**File:** `autobot-frontend/src/composables/usePatternAnalysis.ts`
**Pattern:** C (POST-start + GET-poll). Base URL: `/api/analytics/codebase/patterns`.
The retry-on-409 logic in the current file maps to `useBackgroundTask`'s built-in stuck-task clearing.
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/usePatternAnalysis.ts` → no output (SSE exempt if present).

### Task 6: useBugPrediction → ApiClient helpers

**File:** `autobot-frontend/src/composables/analytics/useBugPrediction.ts`
**Pattern:** Already uses `useBackgroundTask`. The remaining `fetchWithAuth` calls are helper POSTs.
Replace each remaining `fetchWithAuth(url, { method: 'POST', ... })` with `apiClient.post(url, body)`.
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/analytics/useBugPrediction.ts` → no output.

### Task 7: useAnalyticsDebug → ApiClient + useLoadingState

**File:** `autobot-frontend/src/composables/analytics/useAnalyticsDebug.ts`
**Pattern:** B (mutations). Replace each `fetchWithAuth` POST with `apiClient.post()` inside `wrap()`.
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/analytics/useAnalyticsDebug.ts` → no output.

### Task 8: useToolApproval → ApiClient + useLoadingState

**File:** `autobot-frontend/src/composables/useToolApproval.ts`
**Pattern:** B (POST only). One `fetchWithAuth` POST at ~line 105.
```typescript
// Before
const response = await fetchWithAuth(url, { method: 'POST', body: JSON.stringify(payload) })
// After
const result = await apiClient.post<ResponseType>(url, payload)
```
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/useToolApproval.ts` → no output.

### Task 9: useWorkflowTemplates → ApiClient + useLoadingState

**File:** `autobot-frontend/src/composables/useWorkflowTemplates.ts`
**Pattern:** B (POST + DELETE at ~lines 226, 255). Already imports `useLoadingState`.
Replace `fetchWithAuth` POST/DELETE with `apiClient.post()` / `apiClient.delete()`.
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/useWorkflowTemplates.ts` → no output.

### Task 10: useVoiceOutput → ApiClient + useLoadingState

**File:** `autobot-frontend/src/composables/useVoiceOutput.ts`
**Pattern:** B (POST synthesize at ~line 262). Binary response (audio data) — check if `ApiClient` supports binary or use `fetchWithAuth` with `response.arrayBuffer()`. If binary, leave `fetchWithAuth` for this specific call and document the exception.
**Verify:** Confirm behavior preserved with the same audio blob result.

### Task 11: useVoiceConversation → ApiClient + useLoadingState

**File:** `autobot-frontend/src/composables/useVoiceConversation.ts`
**Pattern:** B (POST transcribe at ~line 629). May return multipart/form-data response.
Replace with `apiClient.post()` if response is JSON, or document exception if binary.
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/useVoiceConversation.ts` → only SSE lines remain if any.

### Task 12: useCommandApproval — POST only (SSE exempt)

**File:** `autobot-frontend/src/composables/useCommandApproval.ts`
**Pattern:** Hybrid. SSE GET (~line 124) stays `fetchWithAuth` — SSE is exempt. POST approve (~line 226) → `apiClient.post()`.
Replace only the POST call. Leave the SSE `fetchWithAuth` call unchanged.
Add comment to the SSE call: `// SSE stream — fetchWithAuth exempt per composable-weakness-remediation design`
**Verify:** `grep "fetchWithAuth" autobot-frontend/src/composables/useCommandApproval.ts` → only SSE line remains.

### Task 13: useBackgroundTask → ApiClient helpers

**File:** `autobot-frontend/src/composables/useBackgroundTask.ts`
**Pattern:** B (POST/GET helpers at lines 55, 71, 208). Replace the `clearStuckTasks` and `postAnalyze` helper functions.

```typescript
// Before (clearStuckTasks ~line 55)
await fetchWithAuth(`${backendUrl}${clearUrl}?force=true`, { method: 'POST' })

// After
import apiClient from '@/utils/ApiClient'
await apiClient.post(`${backendUrl}${clearUrl}?force=true`)

// Before (postAnalyze ~line 71)
return fetchWithAuth(`${backendUrl}${baseUrl}/analyze${qs}`, fetchOpts)

// After — returns parsed JSON, not Response
const result = await apiClient.post(`${backendUrl}${baseUrl}/analyze${qs}`, body)
return result
```

**Important:** `postAnalyze` currently returns a `Response` object. Callers check `response.ok` and call `response.json()`. After migration, `apiClient.post()` returns parsed JSON directly and throws on non-2xx. Update callers within `useBackgroundTask.ts` accordingly.

**Verify:**
```bash
grep "fetchWithAuth" autobot-frontend/src/composables/useBackgroundTask.ts
```
Expected: no output (all `fetchWithAuth` calls replaced).

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "useBackgroundTask"
```
Expected: no errors.

---

## Final verification for Wave 2

- [ ] **Confirm all 12 composables are clean:**

```bash
for f in \
  analytics/useEnvironmentAnalysis.ts \
  useVoiceProfiles.ts \
  analytics/useIndexingJob.ts \
  usePatternAnalysis.ts \
  analytics/useBugPrediction.ts \
  analytics/useAnalyticsDebug.ts \
  useToolApproval.ts \
  useWorkflowTemplates.ts \
  useVoiceOutput.ts \
  useVoiceConversation.ts \
  useCommandApproval.ts \
  useBackgroundTask.ts; do
  count=$(grep -c "fetchWithAuth" autobot-frontend/src/composables/$f 2>/dev/null || echo 0)
  echo "$f: $count fetchWithAuth"
done
```

Expected: all 0 except `useCommandApproval.ts` (1 — SSE line) and `useVoiceOutput.ts` / `useVoiceConversation.ts` if binary responses required exception.

- [ ] **Full type-check:**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
```
Expected: 0 new errors vs Wave 1 baseline.
