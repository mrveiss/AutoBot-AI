# Frontend Composable HTTP Patterns

Five patterns coexist in the composable layer. All are intentional. This doc explains when to use each and how they differ.

---

## The Five Patterns

### Pattern A1 — Direct `ApiClient` + `useLoadingState`

**Used for:** user-initiated mutations — button clicks, form submits, one-shot commands — where `ApiClient` is imported directly rather than obtained through Vue injection.

```typescript
import { ApiClient } from '@/utils/ApiClient'
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

---

### Pattern A2 — Injected `useApi()` / `useApiWithState()`

**Used for:** the same mutation use-cases as A1, but the component receives the `ApiClient` instance via Vue injection rather than importing it directly. Under the hood, `useApi()` returns the same `ApiClient` instance that was registered with `app.use(ApiPlugin)`.

**When to choose A2 over A1:** when the component or composable is instantiated inside a Vue component tree that provides the API plugin, and you want testability via injection override. Both patterns talk to the same `ApiClient`.

**Important — loading state:** `withErrorHandling()` from `useApiWithState()` does **not** manage a loading flag. You still need `useLoadingState()` if the UI must show a spinner.

```typescript
import { useApiWithState } from '@/composables/useApi'
import { useLoadingState } from '@/composables/useLoadingState'
import { getApiBase } from '@/config/ssot-config'

export function useOperationsApi() {
  const { api, withErrorHandling } = useApiWithState()
  const { isLoading, wrap } = useLoadingState()

  async function listOperations(filter?: OperationsFilter) {
    return wrap(() =>
      withErrorHandling(async () => {
        const params = new URLSearchParams()
        if (filter?.status) params.append('status', filter.status)
        const response = await api.get(`${getApiBase()}/long-running/?${params}`)
        return response.json()
      })
    )
  }

  return { isLoading, listOperations }
}
```

`useApi()` variant — inject only, no error wrapper:

```typescript
const api = useApi()
const data = await api.get<ResponseType>(`${getApiBase()}/some/endpoint`)
```

---

### Pattern B1 — `useFetchEndpoint` / `useApiResource`

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

### Pattern B2 — Raw `fetchWithAuth` (no wrapper)

**Used in:** older composables written before `useFetchEndpoint` existed. This is a **legacy pattern** — new composables should use `useFetchEndpoint` (B1) instead. Migration of existing B2 sites is tracked in issue #5923.

When it appears: the composable calls `fetchWithAuth` directly and manages its own `loading` ref and error state manually.

```typescript
import { fetchWithAuth } from '@/utils/fetchWithAuth'

const loading = ref(false)
const error = ref<string | null>(null)

async function analyzePatterns(path: string) {
  loading.value = true
  error.value = null
  try {
    const response = await fetchWithAuth(`${getApiBase()}/analytics/codebase/patterns/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await response.json()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}
```

`fetchWithAuth` adds the Bearer token automatically from `localStorage`. It does **not** provide abort-on-unmount or race-condition guards.

---

### Pattern C — Raw `fetch()` with manual auth

**Used for:** cases where no auth helper is available or the auth token must be added manually — Prometheus metrics endpoints, network health checks, SLM calls that use a separately-obtained token.

```typescript
import { getAuthToken } from '@/utils/fetchWithAuth'

async function fetchConfig(workflowId: string) {
  const token = getAuthToken()
  const response = await fetch(`${getApiBase()}/workflow-automation/notification_config/${workflowId}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}
```

Alternatively, auth headers may come from a separate token store:

```typescript
// useTLSCredentials — SLM has its own token separate from the main backend token
async function slmFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {}),
    ...options.headers,
  }
  return fetch(`${getSLMUrl()}${path}`, { ...options, headers })
}
```

**Appropriate for:** Prometheus metrics, SLM endpoints with a separate token, network health checks, endpoints that do not require the main auth token.

**Inappropriate for:** any regular backend endpoint that requires the standard auth Bearer token — use `fetchWithAuth` (B2) or `ApiClient` (A1/A2) instead. Raw `fetch()` does **not** add auth headers automatically.

---

## Decision Table

| Question | A1 (direct `ApiClient`) | A2 (`useApi()`/`useApiWithState()`) | B1 (`useFetchEndpoint`) | B2 (raw `fetchWithAuth`) | C (raw `fetch()`) |
|---|---|---|---|---|---|
| HTTP method | POST / DELETE / PUT | POST / DELETE / PUT / GET | GET (occasional POST) | Any | Any |
| Auth handled by | `ApiClient` internal | `ApiClient` internal | `fetchWithAuth` internal | `fetchWithAuth` internal | manual headers |
| Trigger | User action | User action | `onMounted`, `watch`, timer | User action (legacy) | User action or timer |
| Result goes into | Inline variable / callback | Inline variable / callback | `data.value` reactive ref | Inline variable / manual ref | Inline variable / manual ref |
| Abort on unmount | No | No | Yes (via `useApiResource`) | No | No |
| Race guard | No | No | Yes (monotonic call IDs) | No | No |
| Loading state | `useLoadingState()` | `useLoadingState()` (manual — `withErrorHandling` doesn't manage it) | built-in `loading` ref | manual `loading` ref | manual or `useLoadingState()` |
| New code? | Yes | Yes | Yes | **No — legacy only** | When no auth helper fits |

If you need `data.value` to drive a template, use Pattern B1. If the result is consumed imperatively in the same function, use Pattern A1 or A2. If neither `ApiClient` nor `fetchWithAuth` cover the endpoint's auth needs, use Pattern C.

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

3. **B2 → B1 migration** tracked in issue #5923. Do not write new composables using raw `fetchWithAuth`; use `useFetchEndpoint` instead.

4. **No forced migration.** Do not rewrite working mutation composables to `useFetchEndpoint` unless the composable also needs reactive `data`, abort safety, or `fallbackData`. The ergonomics of `wrap()` are intentionally better for mutations.

---

## Composables currently using each pattern

### Pattern A1 — Direct `ApiClient` + `useLoadingState`

| Composable | Notes |
|---|---|
| `useBrowserAutomation` | All browser commands — launch, navigate, click, screenshot, etc. |
| `useAvailableModels` | GET but result consumed inline; mutation-style usage |
| `useDevSpeedup` | Developer toggle mutations |
| `useAgentRegistry` | Load list + load detail, two separate states |
| `useAIDocument` | Edit / save / refine — three separate states |
| `useKnowledgeStats` | GET stats, inline result |
| `useMachineKnowledge` | GET facts, inline result |
| `useManPages` | GET man page, inline result |
| `useKnowledgeCategories` | GET categories, inline result |
| `useVncControls` | 7 desktop-control commands — click, type, key, scroll, drag, screenshot, clipboard |
| `useVncConnection` | Load/update connection settings; `loadMetrics` has no loading flag |
| `usePlugins` | Load and discover plugins; lifecycle mutations call `listPlugins()` after |
| `useKnowledgeCollaboration` | Hierarchical knowledge access control mutations |
| `useKnowledgeGraph` | Graph data mutations |
| `useWorkflowBuilder` | Workflow builder mutations |
| `useCodeIntelligence` | Counter-based `loadingCount` — not migrated; see #5880 |

### Pattern A2 — Injected `useApi()` / `useApiWithState()`

| Composable | Notes |
|---|---|
| `useConversationFiles` | `useApi()` for file management; `useLoadingState` for loading flag |
| `useAuditApi` | `useApiWithState()` + `withErrorHandling` |
| `useServiceMessages` | `useApiWithState()` + `withErrorHandling` |
| `useSecretsAuditApi` | `useApiWithState()` + `withErrorHandling` |
| `useOperationsApi` | `useApiWithState()` + `withErrorHandling`; `useLoadingState` for UI spinner |
| `useAutoResearch` | `useApiWithState()` for research submission |
| `useBatchProcessing` | `useApiWithState()` for batch job submission |
| `usePrometheusMetrics` | `useApi()` for monitoring reads; `useLoadingState` for loading flag |

### Pattern B1 — `useFetchEndpoint` / `useApiResource`

| Composable | Notes |
|---|---|
| All `analytics/*` composables | `useFetchEndpoint` via analytics alias (`scopeToSource: true` default) |
| `useWorkflowTemplates` | GET templates, reactive `data` |
| `useCommandApproval` | POST to approval endpoint, uses `useApiResource` directly |
| `useMultiModelCompare` | SSE + REST, uses `useApiResource` for the REST portion |

### Pattern B2 — Raw `fetchWithAuth` (legacy)

| Composable | Notes |
|---|---|
| `usePatternAnalysis` | 11 `fetchWithAuth` call pairs — analyze, load, cancel, clear, etc. |
| `useVoiceProfiles` | 3 `fetchWithAuth` calls — list voices, create, delete |
| `analytics/useEnvironmentAnalysis` | 1 `fetchWithAuth` call — environment variable scan |

### Pattern C — Raw `fetch()` with manual auth

| Composable | Notes |
|---|---|
| `useWorkflowNotificationConfig` | raw `fetch()` with `getAuthToken()` header; self-contained `apiRequest` helper |
| `useNotificationConfig` | raw `fetch()` with `localStorage` token lookup via `getAuthHeaders()` |
| `useTLSCredentials` | raw `fetch()` via `slmFetch()`; uses a separate SLM-specific auth token |

---

## Writing a new composable

1. **Mutation (user-triggered POST/DELETE)?** → `ApiClient` (A1) + `useLoadingState`. One `const { isLoading, wrap } = useLoadingState()` per independent loading state. Use A2 (`useApi()`) if the composable is deeply inside a component tree and injection testability matters.

2. **Read that populates a template?** → `useFetchEndpoint` (B1). Provide `path`, `pickData`, and call `load()` in `onMounted` or a `watch`.

3. **Custom fetch logic that doesn't fit `useFetchEndpoint`?** → `useApiResource` (B1) directly. Pass a fetcher closure; get `data`, `error`, `isLoading`, `refresh`, `abort` back.

4. **SSE / WebSocket / streaming?** → Neither. Manage the connection directly; use `ref()` for reactive state and `onScopeDispose()` for cleanup.

5. **Endpoint that needs non-standard auth (SLM, Prometheus, health check)?** → Pattern C (raw `fetch()`). Add auth headers manually. Do not use Pattern C for regular backend endpoints.

6. **Existing B2 composable that needs new calls?** → Add using `fetchWithAuth` to match the existing pattern; file a follow-up migration issue (#5923 tracks B2 → B1 cleanup).
