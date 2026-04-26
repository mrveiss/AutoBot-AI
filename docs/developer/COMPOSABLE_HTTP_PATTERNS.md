# Frontend Composable HTTP Patterns

Two patterns coexist in the composable layer. Both are intentional. This doc explains when to use each and how they differ.

---

## The Two Patterns

### Pattern A — `ApiClient` + `useLoadingState`

**Used for:** user-initiated mutations — button clicks, form submits, one-shot commands.

```typescript
import ApiClient from '@/utils/ApiClient'
import { useLoadingState } from '@/composables/useLoadingState'

const { isLoading, wrap } = useLoadingState()

async function launch(url: string) {
  return wrap(async () => {
    const data = await ApiClient.post<BrowserSession>(`${getApiBase()}/browser/launch`, { url })
    session.value = data.session
  })
}
```

`ApiClient` manages auth, retries, and a built-in timeout internally. The composable does not need to know about those details. `wrap()` handles the `isLoading` flag and propagates errors unchanged.

### Pattern B — `useFetchEndpoint` (built on `useApiResource`)

**Used for:** data reads that populate reactive UI — dashboard panels, stats, lists that refresh on demand or on mount.

```typescript
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

const { data, loading, error, load } = useFetchEndpoint<RawStats, Stats>({
  path: '/api/knowledge_base/stats',
  pickData: (raw) => raw.stats ?? null,
  onSuccess: (stats) => { /* side effect */ },
})
onMounted(load)
```

`useFetchEndpoint` delegates to `useApiResource` which provides: AbortController abort-on-unmount, race-condition safety via monotonic call IDs, and reactive `data`/`error`/`isLoading` refs. All analytics composables, knowledge composables, and other polling/refreshing composables use this pattern.

---

## Decision Table

| Question | Pattern A (`ApiClient` + `useLoadingState`) | Pattern B (`useFetchEndpoint`) |
|---|---|---|
| HTTP method | POST / DELETE / PUT | GET (occasionally POST for query-style reads) |
| Trigger | User action (button, form) | `onMounted`, `watch`, timer, explicit `load()` |
| Result goes into | Inline variable, passed to callback | `data.value` reactive ref |
| Abort on unmount needed? | No — short one-shot calls | Yes — prevents update-after-dispose |
| Race guard needed? | No — debounced by button disable | Yes — rapid refresh() calls |
| Retry / timeout | Handled inside `ApiClient` | Handled by `fetchWithAuth` + `onResponse` |
| `fallbackData` / `onError` hooks | Not needed | Available |

If you need `data.value` to drive a template, use Pattern B. If the result is consumed imperatively in the same function, use Pattern A.

---

## `useLoadingState` with multiple concurrent states

A single composable can need more than one loading flag:

```typescript
// Three independent loading states with aliased names
const { isLoading, wrap } = useLoadingState()
const { isLoading: isSaving, wrap: wrapSave } = useLoadingState()
const { isLoading: isRefining, wrap: wrapRefine } = useLoadingState()
```

Each `useLoadingState()` call is independent. Concurrent calls through the *same* `wrap()` function are safe — the `_pending` counter ensures `isLoading` only clears when the last concurrent call finishes (see `__tests__/useLoadingState.test.ts` for the concurrent-overlap test).

---

## Long-term consolidation path

The split is deliberate and low-risk today. `ApiClient` is well-tested for mutations; `useFetchEndpoint` is the right abstraction for reads.

1. **`ApiClient` does not expose an `AbortSignal` externally.** Until it does, mutation composables cannot participate in lifecycle teardown. For short-lived one-shot POSTs this is not a problem in practice — the call completes before the component unmounts in the normal case.

2. **Reads on `ApiClient`** (there are a few — `useAvailableModels`, `useDocumentChanges`) could migrate to `useFetchEndpoint` for abort + race safety. Each migration is independent and low-risk. File a follow-up issue when you encounter one rather than doing it inline.

3. **No forced migration.** Do not rewrite working mutation composables to `useFetchEndpoint` unless the composable also needs reactive `data`, abort safety, or `fallbackData`. The ergonomics of `wrap()` are intentionally better for mutations.

---

## Composables currently using each pattern

### Pattern A — `ApiClient` + `useLoadingState`

| Composable | Notes |
|---|---|
| `useBrowserAutomation` | All browser commands — launch, navigate, click, screenshot, etc. |
| `useAvailableModels` | GET but result consumed inline; mutation-style usage |
| `useDevSpeedup` | Developer toggle mutations |
| `usePrometheusMetrics` | Periodic fetch via `usePollingJob`, result inline |
| `useTLSCredentials` | 6 separate mutation operations |
| `useAgentRegistry` | Load list + load detail, two separate states |
| `useAIDocument` | Edit / save / refine — three separate states |
| `useKnowledgeStats` | GET stats, inline result |
| `useMachineKnowledge` | GET facts, inline result |
| `useManPages` | GET man page, inline result |
| `useKnowledgeCategories` | GET categories, inline result |
| `useVncControls` | 7 desktop-control commands — click, type, key, scroll, drag, screenshot, clipboard |
| `useVncConnection` | Load/update connection settings; `loadMetrics` has no loading flag |
| `usePlugins` | Load and discover plugins; lifecycle mutations call `listPlugins()` after |
| `useCodeIntelligence` | Counter-based `loadingCount` — not migrated; see #5880 |

### Pattern B — `useFetchEndpoint` / `useApiResource`

| Composable | Notes |
|---|---|
| All `analytics/*` composables | `useFetchEndpoint` via analytics alias (`scopeToSource: true` default) |
| `useWorkflowTemplates` | GET templates, reactive `data` |
| `usePatternAnalysis` | GET analysis, reactive `data` |
| `useCommandApproval` | POST to approval endpoint, uses `useApiResource` directly |
| `useMultiModelCompare` | SSE + REST, uses `useApiResource` for the REST portion |
| `useVoiceProfiles` | GET profiles, reactive `data` |
| `useWorkflowNotificationConfig` | GET/POST config, reactive `data` |

---

## Writing a new composable

1. **Mutation (user-triggered POST/DELETE)?** → `ApiClient` + `useLoadingState`. One `const { isLoading, wrap } = useLoadingState()` per independent loading state.

2. **Read that populates a template?** → `useFetchEndpoint`. Provide `path`, `pickData`, and call `load()` in `onMounted` or a `watch`.

3. **Custom fetch logic that doesn't fit `useFetchEndpoint`?** → `useApiResource` directly. Pass a fetcher closure; get `data`, `error`, `isLoading`, `refresh`, `abort` back.

4. **SSE / WebSocket / streaming?** → Neither. Manage the connection directly; use `ref()` for reactive state and `onScopeDispose()` for cleanup.
