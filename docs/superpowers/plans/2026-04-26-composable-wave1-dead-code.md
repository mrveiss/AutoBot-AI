# Composable Wave 1 — Dead Code & Overlap Removal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `useAsyncOperation` (wired duplicate of `useLoadingState`) and refactor `UnifiedLoadingView` to props-driven (deleting `useUnifiedLoading` singleton).

**Architecture:** Mechanical migration — `useAsyncOperation.execute(fn)` → `useLoadingState.wrap(fn)`, `loading` → `isLoading`. `UnifiedLoadingView` gets `isLoading/error/message/hasTimedOut` as props instead of reading from a singleton composable. Tracker issue: #6006.

**Tech Stack:** Vue 3, TypeScript, Vitest, `src/composables/useLoadingState.ts`

---

## Migration pattern (read before all tasks)

```typescript
// BEFORE — useAsyncOperation
import { useAsyncOperation } from '@/composables/useAsyncOperation'
const { execute: doThing, loading: isDoingThing, error: doThingError } = useAsyncOperation()
await doThing(() => apiCall())

// AFTER — useLoadingState
import { useLoadingState } from '@/composables/useLoadingState'
import { ref } from 'vue'
const { isLoading: isDoingThing, wrap: wrapDoThing } = useLoadingState()
const doThingError = ref<Error | null>(null)
doThingError.value = null
await wrapDoThing(() => apiCall()).catch(err => {
  doThingError.value = err instanceof Error ? err : new Error(String(err))
})
```

Key differences:
- `execute()` → `wrap()` (same signature: `(fn: () => Promise<T>) => Promise<T>`)
- `loading` → `isLoading`
- `error` is no longer reactive from the composable — add `ref<Error | null>(null)` + `.catch()` at call site
- `data` result is no longer stored — consume inline from `wrap()` return value
- `isSuccess` / `isError` computeds disappear — replace with `!doThingError.value` / `!!doThingError.value` where needed

---

## Task 1: Create GitHub issue — useAsyncOperation tracker

**Files:**
- No file changes

- [ ] **Step 1: Create tracker issue**

```bash
gh issue create \
  --title "tracker(composables): remove useAsyncOperation — migrate all callers to useLoadingState" \
  --label "refactor,frontend,tech-debt" \
  --body "## Overview
useAsyncOperation duplicates useLoadingState with a different API. Five components use it. Migrate all to useLoadingState.wrap() then delete the file.

## Children
- [ ] refact(ui): migrate CommandPermissionDialog from useAsyncOperation to useLoadingState
- [ ] refact(desktop): migrate DesktopInterface from useAsyncOperation to useLoadingState
- [ ] refact(knowledge): migrate SystemKnowledgeManager from useAsyncOperation to useLoadingState
- [ ] refact(knowledge): migrate KnowledgeBrowser from useAsyncOperation to useLoadingState
- [ ] refact(knowledge): migrate FailedVectorizationsManager from useAsyncOperation to useLoadingState
- [ ] chore(composables): delete useAsyncOperation.ts and AsyncOperationExample.vue

## References
Master tracker: #6006
Design spec: docs/superpowers/specs/2026-04-26-composable-weakness-remediation-design.md"
```

- [ ] **Step 2: Create child issues**

```bash
for title in \
  "refact(ui): migrate CommandPermissionDialog from useAsyncOperation to useLoadingState" \
  "refact(desktop): migrate DesktopInterface from useAsyncOperation to useLoadingState" \
  "refact(knowledge): migrate SystemKnowledgeManager from useAsyncOperation to useLoadingState" \
  "refact(knowledge): migrate KnowledgeBrowser from useAsyncOperation to useLoadingState" \
  "refact(knowledge): migrate FailedVectorizationsManager from useAsyncOperation to useLoadingState" \
  "chore(composables): delete useAsyncOperation.ts and AsyncOperationExample.vue after all callers migrated" \
  "refact(ui): refactor UnifiedLoadingView to props-driven, delete useUnifiedLoading singleton"; do
  gh issue create --title "$title" --label "refactor,frontend,tech-debt" --body "Part of tracker #6006. See design spec: docs/superpowers/specs/2026-04-26-composable-weakness-remediation-design.md"
done
```

Record the issue numbers for worktree branches.

---

## Task 2: Migrate CommandPermissionDialog

**Files:**
- Modify: `autobot-frontend/src/components/ui/CommandPermissionDialog.vue`

Context: Currently uses 2 `useAsyncOperation()` instances for allow + comment flows, with a computed `error` merging both.

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number-from-task-1>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Open the file and locate the useAsyncOperation block**

Lines ~138, 166–167, 173, 221, 261 in `src/components/ui/CommandPermissionDialog.vue`.

- [ ] **Step 3: Replace the import**

Find:
```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'
```
Replace with:
```typescript
import { useLoadingState } from '@/composables/useLoadingState'
```

- [ ] **Step 4: Replace the two useAsyncOperation instances**

Find:
```typescript
const { execute: executeAllow, loading: isProcessingAllow, error: errorAllow } = useAsyncOperation()
const { execute: executeComment, loading: isProcessingComment, error: errorComment } = useAsyncOperation()
const error = computed(() => errorAllow.value || errorComment.value)
```
Replace with:
```typescript
const { isLoading: isProcessingAllow, wrap: wrapAllow } = useLoadingState()
const { isLoading: isProcessingComment, wrap: wrapComment } = useLoadingState()
const errorAllow = ref<Error | null>(null)
const errorComment = ref<Error | null>(null)
const error = computed(() => errorAllow.value || errorComment.value)
```

Ensure `ref` is imported from `'vue'` (check existing imports at top of `<script setup>`).

- [ ] **Step 5: Replace executeAllow call site (~line 221)**

Find:
```typescript
await executeAllow(allowCommandFn).catch(err => logger.error('Command approval error:', err))
```
Replace with:
```typescript
errorAllow.value = null
await wrapAllow(allowCommandFn).catch(err => {
  errorAllow.value = err instanceof Error ? err : new Error(String(err))
  logger.error('Command approval error:', err)
})
```

- [ ] **Step 6: Replace executeComment call site (~line 261)**

Find:
```typescript
await executeComment(submitCommentFn).catch(err => logger.error('Comment submission error:', err))
```
Replace with:
```typescript
errorComment.value = null
await wrapComment(submitCommentFn).catch(err => {
  errorComment.value = err instanceof Error ? err : new Error(String(err))
  logger.error('Comment submission error:', err)
})
```

- [ ] **Step 7: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "CommandPermissionDialog"
```
Expected: no errors for this file.

- [ ] **Step 8: Verify no remaining useAsyncOperation references**

```bash
grep -n "useAsyncOperation\|executeAllow\|executeComment" autobot-frontend/src/components/ui/CommandPermissionDialog.vue
```
Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add autobot-frontend/src/components/ui/CommandPermissionDialog.vue
git commit -m "refact(ui): migrate CommandPermissionDialog from useAsyncOperation to useLoadingState (#ISSUE)"
```

---

## Task 3: Migrate DesktopInterface

**Files:**
- Modify: `autobot-frontend/src/components/desktop/DesktopInterface.vue`

Context: Uses 2 `useAsyncOperation()` instances (`executeLoadVnc`/`loadingVnc` and `executeCheckConnection`/`loadingCheck`). Has a separate `loading = ref(true)` for overall component state — leave that ref alone, only remove `useAsyncOperation`.

- [ ] **Step 1: Create worktree (or continue in same worktree if batching)**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Replace import**

Find:
```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'
```
Replace with:
```typescript
import { useLoadingState } from '@/composables/useLoadingState'
```

- [ ] **Step 3: Replace the two instances (~lines 188–189)**

Find:
```typescript
const { execute: executeLoadVnc, loading: loadingVnc, error: errorVnc } = useAsyncOperation()
const { execute: executeCheckConnection, loading: loadingCheck, error: errorCheck } = useAsyncOperation()
```
Replace with:
```typescript
const { isLoading: loadingVnc, wrap: wrapLoadVnc } = useLoadingState()
const { isLoading: loadingCheck, wrap: wrapCheckConnection } = useLoadingState()
const errorVnc = ref<Error | null>(null)
const errorCheck = ref<Error | null>(null)
```

Ensure `ref` is already imported from `'vue'`.

- [ ] **Step 4: Replace executeLoadVnc call site (~line 232)**

Find:
```typescript
await executeLoadVnc(loadVncUrlFn).catch(err => {
```
Replace with:
```typescript
errorVnc.value = null
await wrapLoadVnc(loadVncUrlFn).catch(err => {
  errorVnc.value = err instanceof Error ? err : new Error(String(err))
```

- [ ] **Step 5: Find and replace any executeCheckConnection call sites**

```bash
grep -n "executeCheckConnection" autobot-frontend/src/components/desktop/DesktopInterface.vue
```
Replace each with `wrapCheckConnection` following the same error-capture pattern.

- [ ] **Step 6: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "DesktopInterface"
```
Expected: no errors for this file.

- [ ] **Step 7: Verify clean**

```bash
grep -n "useAsyncOperation\|executeLoadVnc\|executeCheckConnection" autobot-frontend/src/components/desktop/DesktopInterface.vue
```
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add autobot-frontend/src/components/desktop/DesktopInterface.vue
git commit -m "refact(desktop): migrate DesktopInterface from useAsyncOperation to useLoadingState (#ISSUE)"
```

---

## Task 4: Migrate SystemKnowledgeManager

**Files:**
- Modify: `autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue`

Context: Uses 7 `useAsyncOperation()` instances (one per action: fetchStats, initialize, reindex, refresh, populateManPages, populateAutoBotDocs, generateVectorEmbeddings). Each produces its own `loading` alias (`isLoading`, `isInitializing`, `isReindexing`, etc.).

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Replace import**

Find:
```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation';
```
Replace with:
```typescript
import { useLoadingState } from '@/composables/useLoadingState'
```

- [ ] **Step 3: Replace all 7 instances (~lines 248–254)**

Find:
```typescript
const { execute: fetchStatsOp, loading: isLoading } = useAsyncOperation();
const { execute: initializeMachineKnowledgeOp, loading: isInitializing } = useAsyncOperation();
const { execute: reindexDocumentsOp, loading: isReindexing } = useAsyncOperation();
const { execute: refreshSystemKnowledgeOp, loading: isRefreshing } = useAsyncOperation();
const { execute: populateManPagesOp, loading: isPopulating } = useAsyncOperation();
const { execute: populateAutoBotDocsOp, loading: isDocPopulating } = useAsyncOperation();
const { execute: generateVectorEmbeddingsOp, loading: isVectorizing } = useAsyncOperation();
```
Replace with:
```typescript
const { isLoading, wrap: fetchStatsOp } = useLoadingState()
const { isLoading: isInitializing, wrap: initializeMachineKnowledgeOp } = useLoadingState()
const { isLoading: isReindexing, wrap: reindexDocumentsOp } = useLoadingState()
const { isLoading: isRefreshing, wrap: refreshSystemKnowledgeOp } = useLoadingState()
const { isLoading: isPopulating, wrap: populateManPagesOp } = useLoadingState()
const { isLoading: isDocPopulating, wrap: populateAutoBotDocsOp } = useLoadingState()
const { isLoading: isVectorizing, wrap: generateVectorEmbeddingsOp } = useLoadingState()
```

Note: the `wrap` names match the old `execute` names so call sites need no changes — the function signatures are compatible.

- [ ] **Step 4: Grep for any error usage from these operations**

```bash
grep -n "\.error\b" autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue | head -10
```
If the component used `.error` from `useAsyncOperation` returns, add `ref<Error | null>(null)` + catch blocks at call sites.

- [ ] **Step 5: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "SystemKnowledgeManager"
```
Expected: no errors.

- [ ] **Step 6: Verify clean**

```bash
grep -n "useAsyncOperation" autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue
```
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add autobot-frontend/src/components/knowledge/SystemKnowledgeManager.vue
git commit -m "refact(knowledge): migrate SystemKnowledgeManager from useAsyncOperation to useLoadingState (#ISSUE)"
```

---

## Task 5: Migrate KnowledgeBrowser

**Files:**
- Modify: `autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue`

Context: Uses 2 instances — `loadKnowledgeTree`/`isLoading` and `loadFileContentOp`/`isLoadingContent`. Has `error` ref from each.

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Replace import**

Find:
```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'
```
Replace with:
```typescript
import { useLoadingState } from '@/composables/useLoadingState'
```

- [ ] **Step 3: Replace instances (~lines 295–305)**

Find:
```typescript
} = useAsyncOperation()
```
(all occurrences)

Replace each block following the migration pattern. Specifically (~lines 295–305):
```typescript
// BEFORE
const {
  execute: loadKnowledgeTree,
  loading: isLoading,
  error,
} = useAsyncOperation()
const {
  execute: loadFileContentOp,
  loading: isLoadingContent,
  error: contentError,
} = useAsyncOperation()

// AFTER
const { isLoading, wrap: loadKnowledgeTree } = useLoadingState()
const error = ref<Error | null>(null)
const { isLoading: isLoadingContent, wrap: loadFileContentOp } = useLoadingState()
const contentError = ref<Error | null>(null)
```

- [ ] **Step 4: Fix call sites — add error capture**

Find every `await loadKnowledgeTree(` and `await loadFileContentOp(` call. Prepend `error.value = null` / `contentError.value = null` and add `.catch(err => { error.value = ...; ... })`.

- [ ] **Step 5: Type-check and verify**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "KnowledgeBrowser"
grep -n "useAsyncOperation" autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue
```

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/components/knowledge/KnowledgeBrowser.vue
git commit -m "refact(knowledge): migrate KnowledgeBrowser from useAsyncOperation to useLoadingState (#ISSUE)"
```

---

## Task 6: Migrate FailedVectorizationsManager

**Files:**
- Modify: `autobot-frontend/src/components/knowledge/FailedVectorizationsManager.vue`

Context: One instance — `fetchFailedJobs`/`loading`/`error`. Template uses `loading` and `error` directly.

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Replace import and instance (~lines 106, 128)**

Find:
```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'
```
Replace with:
```typescript
import { useLoadingState } from '@/composables/useLoadingState'
```

Find:
```typescript
const { execute: fetchFailedJobs, loading, error } = useAsyncOperation()
```
Replace with:
```typescript
const { isLoading: loading, wrap: wrapFetchFailedJobs } = useLoadingState()
const error = ref<string | null>(null)
```

Note: `error` in the template displays a string (`{{ error }}`), so keep it as `ref<string | null>` and assign `err.message` in the catch.

- [ ] **Step 3: Fix call sites**

Find all `await fetchFailedJobs(` calls. Replace with:
```typescript
error.value = null
await wrapFetchFailedJobs(<original-fn>).catch(err => {
  error.value = err instanceof Error ? err.message : String(err)
})
```

- [ ] **Step 4: Type-check and verify**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "FailedVectorizationsManager"
grep -n "useAsyncOperation" autobot-frontend/src/components/knowledge/FailedVectorizationsManager.vue
```

- [ ] **Step 5: Commit**

```bash
git add autobot-frontend/src/components/knowledge/FailedVectorizationsManager.vue
git commit -m "refact(knowledge): migrate FailedVectorizationsManager from useAsyncOperation to useLoadingState (#ISSUE)"
```

---

## Task 7: Delete useAsyncOperation.ts and AsyncOperationExample.vue

**Prerequisite:** Tasks 2–6 all merged to Dev_new_gui.

**Files:**
- Delete: `autobot-frontend/src/composables/useAsyncOperation.ts`
- Delete: `autobot-frontend/src/components/examples/AsyncOperationExample.vue`

- [ ] **Step 1: Confirm zero remaining callers**

```bash
grep -r "useAsyncOperation\|AsyncOperationExample" autobot-frontend/src --include="*.ts" --include="*.vue" | grep -v "useAsyncOperation\.ts\|AsyncOperationExample\.vue"
```
Expected: no output. If any remain, do NOT proceed — migrate them first.

- [ ] **Step 2: Confirm AsyncOperationExample is not registered anywhere**

```bash
grep -r "AsyncOperationExample" autobot-frontend/src --include="*.ts" --include="*.vue" | grep -v "AsyncOperationExample\.vue"
```
Expected: no output.

- [ ] **Step 3: Delete the files**

```bash
rm autobot-frontend/src/composables/useAsyncOperation.ts
rm autobot-frontend/src/components/examples/AsyncOperationExample.vue
```

- [ ] **Step 4: Type-check full frontend**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | head -30
```
Expected: no new errors introduced by deletion.

- [ ] **Step 5: Commit**

```bash
git add -u autobot-frontend/src/composables/useAsyncOperation.ts
git add -u autobot-frontend/src/components/examples/AsyncOperationExample.vue
git commit -m "chore(composables): delete useAsyncOperation.ts and AsyncOperationExample.vue — all callers migrated (#ISSUE)"
```

---

## Task 8: Refactor UnifiedLoadingView to props-driven

**Files:**
- Modify: `autobot-frontend/src/components/ui/UnifiedLoadingView.vue`
- Delete: `autobot-frontend/src/composables/useUnifiedLoading.ts`
- Modify: `autobot-frontend/src/App.vue`
- Modify: `autobot-frontend/src/components/desktop/DesktopInterface.vue`
- Modify: `autobot-frontend/src/components/desktop/PopoutChromiumBrowser.vue`

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Rewrite UnifiedLoadingView.vue script section**

Replace the entire `<script setup lang="ts">` block with:

```typescript
<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import Icon from './Icon.vue'
import LoadingSpinner from './LoadingSpinner.vue'

const logger = createLogger('UnifiedLoadingView')
const { t } = useI18n()

interface Props {
  isLoading?: boolean
  error?: string | null
  message?: string
  hasTimedOut?: boolean
  hasContent?: boolean
  onRetry?: () => void
  timeoutMs?: number
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
  error: null,
  message: '',
  hasTimedOut: false,
  hasContent: false,
  timeoutMs: 10000
})

const emit = defineEmits<{
  'loading-complete': []
  'loading-error': [error: string]
  'loading-timeout': []
}>()

let timeoutId: ReturnType<typeof setTimeout> | null = null

function clearTimer() {
  if (timeoutId !== null) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
}

watch(() => props.isLoading, (loading) => {
  clearTimer()
  if (loading && props.timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      logger.warn(`Loading timed out after ${props.timeoutMs}ms`)
      emit('loading-timeout')
    }, props.timeoutMs)
  } else if (!loading) {
    emit('loading-complete')
  }
})

watch(() => props.error, (err) => {
  if (err) emit('loading-error', err)
})

onUnmounted(clearTimer)

const retry = () => {
  if (props.onRetry) props.onRetry()
}

const dismiss = () => {
  emit('loading-complete')
}

const cancelLoading = () => {
  emit('loading-timeout')
}
</script>
```

- [ ] **Step 3: Update template bindings** — remove `:data-loading-key` attribute and any `loadingKey` references from template. The template `v-if` / `v-else-if` conditions already use `error`, `isLoading`, `hasContent`, `hasTimedOut`, `message` — these now come from props directly.

- [ ] **Step 4: Update App.vue**

Find the `<UnifiedLoadingView>` block. Replace `:has-content` + `loading-key` + `:auto-timeout-ms` with direct prop binding. App.vue has its own `isLoading` and `hasErrors` refs — pass them:

```html
<UnifiedLoadingView
  :is-loading="isLoading"
  :error="hasErrors ? 'Application failed to load' : null"
  :has-content="!isLoading && !hasErrors"
  :timeout-ms="15000"
  @loading-complete="handleLoadingComplete"
  @loading-error="handleLoadingError"
  @loading-timeout="handleLoadingTimeout"
  class="h-full"
>
```

Remove the `import { useUnifiedLoading }` line if App.vue had one. Remove the `loadingManager.startLoading('app-main', ...)` call if it existed.

- [ ] **Step 5: Update DesktopInterface.vue**

Replace:
```html
<UnifiedLoadingView
  loading-key="desktop-vnc"
  :has-content="!loading && !error"
  :auto-timeout-ms="15000"
  ...
>
```
With:
```html
<UnifiedLoadingView
  :is-loading="loading"
  :error="errorVnc ? errorVnc.message : null"
  :has-content="!loading && !errorVnc"
  :timeout-ms="15000"
  ...
>
```

- [ ] **Step 6: Update PopoutChromiumBrowser.vue** (has 2 `<UnifiedLoadingView>` usages)

For each, replace `loading-key` / `:auto-timeout-ms` with `:is-loading` / `:timeout-ms` bound to the component's existing loading refs.

- [ ] **Step 7: Confirm zero remaining callers of useUnifiedLoading**

```bash
grep -r "useUnifiedLoading\|loadingManager\|loading-key" autobot-frontend/src --include="*.ts" --include="*.vue" | grep -v "useUnifiedLoading\.ts"
```
Expected: no output.

- [ ] **Step 8: Delete useUnifiedLoading.ts**

```bash
rm autobot-frontend/src/composables/useUnifiedLoading.ts
```

- [ ] **Step 9: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "UnifiedLoad|useUnifiedLoad" | head -20
```
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add autobot-frontend/src/components/ui/UnifiedLoadingView.vue \
        autobot-frontend/src/composables/useUnifiedLoading.ts \
        autobot-frontend/src/App.vue \
        autobot-frontend/src/components/desktop/DesktopInterface.vue \
        autobot-frontend/src/components/desktop/PopoutChromiumBrowser.vue
git commit -m "refact(ui): refactor UnifiedLoadingView to props-driven, delete useUnifiedLoading singleton (#ISSUE)"
```

---

## Final verification

- [ ] Run full type-check:

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
```
Expected: 0 (or same count as before this wave — do not introduce new errors).

- [ ] Confirm all deletions are clean:

```bash
grep -r "useAsyncOperation\|useUnifiedLoading\|loadingManager" autobot-frontend/src --include="*.ts" --include="*.vue"
```
Expected: no output.
