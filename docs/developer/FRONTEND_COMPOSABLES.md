# Frontend Composables — Canonical Patterns

This document defines the standard patterns for all new composables in AutoBot frontend, ensuring consistency across 130+ composables and predictable developer experience.

## Return Shape Contract

**Rule: All composables return objects, never tuples.**

Rationale: Objects enable destructuring by name (more readable, refactor-safe) and support adding fields without breaking call sites.

```typescript
// ✅ CORRECT: Object with named fields
export function useMyData() {
  const data = ref<Data>()
  const error = ref<Error | null>()
  const loading = ref(false)
  const fetch = async () => { /* ... */ }
  
  return {
    data,       // reactive state
    error,      // reactive error state
    loading,    // reactive loading state
    fetch       // action method
  }
}

// ❌ WRONG: Tuple return (don't do this)
export function useMyData() {
  return [data, error, loading, fetch]  // Can't destructure by name
}
```

## Standard Field Names

### State Fields

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `data` | `Ref<T>` | Primary reactive data | `data: Ref<User>` |
| `loading` | `Ref<boolean>` | Loading state | indicates async operation in progress |
| `error` | `Ref<Error \| null>` | Error state | null when no error, Error object otherwise |
| `items` | `Ref<T[]>` | Paginated/list data | used in list/table composables |
| `totalCount` | `Ref<number>` | Total item count | server-side pagination |
| `currentPage` | `Ref<number>` | Current page (1-indexed) | for pagination composables |

### Action Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `fetch()` | `() => Promise<T>` | One-shot data fetch (read-only) |
| `refresh()` | `() => Promise<T>` | Re-fetch existing data |
| `subscribe()` | `(callback?) => Unsubscribe` | Subscribe to live updates (WebSocket/SSE) |
| `execute()` | `(args) => Promise<T>` | Execute mutation or command |
| `reset()` | `() => void` | Reset to initial state |

### Naming Convention

```typescript
// ✅ Standard: action verb describes the operation
const { fetch, refresh, subscribe, execute, reset } = useSomething()

// ❌ Non-standard variants (consolidate):
const { load, reload, query, call, clear } // Too varied
```

## Error & Loading Pattern

Use `useLoadingState()` to eliminate manual try/catch boilerplate:

```typescript
import { useLoadingState } from '@/composables/useLoadingState'
import { ApiClient } from '@/utils/ApiClient'

export function useDocuments() {
  const data = ref<Document[]>()
  const error = ref<Error | null>()
  const { isLoading, wrap } = useLoadingState()

  const fetch = async () => {
    return wrap(async () => {
      data.value = await ApiClient.get<Document[]>('/documents')
    })
  }

  return {
    data,
    error,
    loading: isLoading,  // ← use wrapped loading state
    fetch
  }
}
```

When error handling is needed:

```typescript
import { useAsyncHandler } from '@/composables/useErrorHandler'

const { execute, loading, error } = useAsyncHandler(async () => {
  return await ApiClient.post('/documents', { title: 'New' })
})

// Execute and error automatically propagates to error.value
await execute()
```

## Composable Categories & Patterns

### 1. Data-Loading Composables

Return reactive data from a backend endpoint. Use `useFetchEndpoint` for automatic abort-on-unmount and race-condition safety.

```typescript
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

export function useDocuments(filter?: string) {
  const { data, loading, error, refresh } = useFetchEndpoint(
    () => `/documents?filter=${filter}`,
    { autoAbortOnUnmount: true }
  )

  return { data, loading, error, refresh }
}
```

### 2. Mutation/Command Composables

Execute user-initiated actions (button clicks, form submits). Use `useLoadingState()` for simplicity.

```typescript
export function useCreateDocument() {
  const loading = ref(false)
  const error = ref<Error | null>()

  const execute = async (title: string) => {
    loading.value = true
    try {
      return await ApiClient.post('/documents', { title })
    } catch (e) {
      error.value = e as Error
      throw e
    } finally {
      loading.value = false
    }
  }

  return { execute, loading, error }
}
```

### 3. State & Preference Composables

Manage UI state (expand/collapse, sorting, filters). Use `reactive()` for complex nested state.

```typescript
import { reactive, ref, computed } from 'vue'

export function useTableState(items: Ref<Item[]>) {
  const state = reactive({
    sortBy: 'name',
    sortOrder: 'asc',
    filters: {} as Record<string, any>,
    pageSize: 20,
    currentPage: 1
  })

  const filteredItems = computed(() => {
    // Apply sorting/filtering logic
  })

  const reset = () => {
    state.sortBy = 'name'
    state.sortOrder = 'asc'
    state.currentPage = 1
  }

  return { state, filteredItems, reset }
}
```

### 4. Reactive Utility Composables

Wrap browser APIs (localStorage, visibility, online/offline). Return simple reactive refs.

```typescript
export function useDocumentVisibility() {
  const isVisible = ref(!document.hidden)

  const handleVisibilityChange = () => {
    isVisible.value = !document.hidden
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })

  return { isVisible }
}
```

## Probe-Backed Health Pattern

For service-status displays, do **not** write a bespoke `getHealth()` that fetches a per-module health endpoint. Use the shared `useProbeBackedHealth` composable, which wraps the canonical aggregator at `/api/system/health` (legacy per-module health endpoints are sunset — see #6902).

```typescript
import { useProbeBackedHealth, probeStatusToLegacy } from '@/composables/useProbeBackedHealth'
```

### `ProbeResponse` Shape & Lifecycle

`ProbeResponse` is exported from `@/composables/useHealthProbeRegistry` and describes one probe entry inside the `/api/system/health` payload:

```typescript
export interface ProbeResponse {
  name: string
  status?: 'ok' | 'degraded' | 'unavailable' | string
  data?: Record<string, unknown>   // probe-specific diagnostic fields
  detail?: string                  // human-readable status message
}
```

Lifecycle of one `getHealth()` call:

1. `GET /api/system/health` via `useApiClient()`.
2. The named probe is looked up with `findProbeByName()`, which validates the name against the canonical probe registry (`GET /api/system/health/probes`, lazily fetched and cached) — a typo'd probe name surfaces as a one-shot `logger.warn` instead of a silent `'unavailable'` fallback. Call `refreshProbeRegistry()` after a backend reconnect; probe names can change between deploys.
3. `probe.status === 'ok'` → your `buildHealthy(probe, probe.data ?? {})` runs.
4. Probe missing or non-`ok` → your `buildUnavailable(message)` runs (with `probe.detail` when available).
5. Fetch error → logged via `createLogger`, then `buildUnavailable('Service unavailable')`. The returned function **never throws**.

`probeStatusToLegacy()` maps probe status to the legacy per-module vocab (`'ok'` → `'healthy'`, everything else → `'unavailable'`), mirroring the backend's `_PROBE_TO_LEGACY` dict.

### Minimal Usage

`useProbeBackedHealth<R>(options)` is a factory: it returns a `getHealth: () => Promise<R | null>` function you expose from your API composable and call from `setup()`.

```typescript
import { ref } from 'vue'
import { useProbeBackedHealth, probeStatusToLegacy } from '@/composables/useProbeBackedHealth'
import type { MyServiceHealthResponse } from '@/types/myService'

const getHealth = useProbeBackedHealth<MyServiceHealthResponse>({
  probeName: 'my_service',                       // must exist in the probe registry
  buildHealthy: (probe, data) => ({
    status: probeStatusToLegacy(probe.status),
    redis_connected: Boolean(data.redis_connected),
    message: probe.detail,
  }),
  buildUnavailable: (message) => ({
    status: 'unavailable' as const,
    redis_connected: false,
    message,
  }),
  errorMessage: 'Failed to check my_service health',  // optional; logged on fetch error
})

// In setup():
const healthStatus = ref<MyServiceHealthResponse | null>(null)
async function checkHealth() {
  healthStatus.value = await getHealth()
}
```

`buildHealthy` and `buildUnavailable` must return the **same shape** `R` so consumers can render one response type regardless of outcome.

### Worked Example: Operations Health

Real wire-up from `src/composables/useOperationsApi.ts` (consumed by `src/views/OperationsView.vue` via `useOperationsApi()`):

```typescript
// useOperationsApi.ts — API composable exposes getHealth built by the factory
getHealth: useProbeBackedHealth<OperationsHealthResponse>({
  probeName: 'long_running',
  buildHealthy: (probe, data) => ({
    status: probeStatusToLegacy(probe.status),
    active_operations: Number(data.active_operations ?? 0),
    total_operations: Number(data.total_operations ?? 0),
    redis_connected: Boolean(data.redis_connected),
    background_processor_running: Boolean(data.background_processor_running),
    message: probe.detail,
  }),
  buildUnavailable: (message) => ({
    status: 'unavailable' as const,
    active_operations: 0,
    total_operations: 0,
    redis_connected: false,
    background_processor_running: false,
    message,
  }),
  errorMessage: 'Failed to check operations health',
}),

// useOperationsState (same file) — view-facing state wrapper
const healthStatus = ref<OperationsHealthResponse | null>(null)
const isServiceHealthy = computed(() => healthStatus.value?.status === 'healthy')

async function checkHealth() {
  healthStatus.value = await operationsApi.getHealth()
  return healthStatus.value
}
```

`src/composables/useBatchProcessing.ts` (`probeName: PROBE_NAMES.BATCH_JOBS`) is the second production consumer — prefer the `PROBE_NAMES` constants from `@/types/probe-names` over string literals where one exists.

### When to Prefer It Over a Bespoke Health Composable

Use `useProbeBackedHealth` whenever a service-status display answers "is service X up, and what are its diagnostic fields?" from the system health aggregator. It gives you for free:

- The canonical `/api/system/health` endpoint (no new per-module health route to build, document, and sunset later)
- Probe-name validation against the registry (typos warn loudly)
- Consistent never-throws error handling with logging
- The `probeStatusToLegacy` status mapping kept in sync with the backend

Roll a bespoke composable only when health is **not** probe-backed — e.g. polling an external system the backend doesn't probe, or streaming health over WebSocket/SSE.

## Date & Number Formatting

Use `formatHelpers.ts` utilities instead of `.toLocaleString()` for i18n compatibility:

```typescript
import {
  formatDate,      // ISO string → "10/30/2025"
  formatDateTime,  // ISO string → "10/30/2025, 2:30 PM"
  formatTime,      // ISO string → "2:30 PM"
  formatNumber,    // 1234567 → "1,234,567"
  formatFileSize   // 1048576 → "1 MB"
} from '@/utils/formatHelpers'

export function useDocumentMetadata(docId: string) {
  const doc = ref<Document>()

  const createdAtFormatted = computed(() =>
    doc.value?.created_at ? formatDate(doc.value.created_at) : ''
  )

  const updatedAtFormatted = computed(() =>
    doc.value?.updated_at ? formatDateTime(doc.value.updated_at) : ''
  )

  const sizeFormatted = computed(() =>
    doc.value?.size ? formatFileSize(doc.value.size) : ''
  )

  return { doc, createdAtFormatted, updatedAtFormatted, sizeFormatted }
}
```

## Pagination Composable

For paginated data, use the canonical `usePagination()`:

```typescript
import { usePagination } from '@/composables/usePagination'

export function useDocumentList() {
  const documents = ref<Document[]>([])

  const {
    paginatedData,
    currentPage,
    totalPages,
    hasNext,
    hasPrev,
    next,
    prev,
    goToPage
  } = usePagination(documents, {
    itemsPerPage: 20,
    autoResetOnDataChange: true
  })

  return {
    documents,
    paginatedData,
    currentPage,
    totalPages,
    hasNext,
    hasPrev,
    next,
    prev,
    goToPage
  }
}
```

## ESLint Enforcement

Banned patterns in composables:

```javascript
// .eslintrc or eslint.config.ts
{
  rules: {
    'no-restricted-imports': [
      'error',
      {
        // Deprecated composables — migrate to replacements
        paths: [
          {
            name: '@/composables/useApi',
            message: 'Deprecated. Use useFetchEndpoint (data) or useApiClient (mutations)'
          }
        ]
      }
    ],
    'no-restricted-syntax': [
      'error',
      // Ban raw toLocaleString() — use formatHelpers instead
      {
        selector: "CallExpression[callee.object.callee.name='Date'][callee.property.name='toLocaleString']",
        message: 'Use formatDate/formatDateTime from @/utils/formatHelpers for i18n compatibility'
      },
      {
        selector: "CallExpression[callee.property.name='toLocaleString']",
        message: 'Use formatNumber from @/utils/formatHelpers for number formatting'
      }
    ]
  }
}
```

## Checklist for New Composables

- [ ] Returns object (never tuple)
- [ ] Field names match standard (data, loading, error, fetch, refresh)
- [ ] Action methods are Promise-based
- [ ] No console.log; use `createLogger()` if debugging needed
- [ ] TypeScript: full type coverage (no implicit any)
- [ ] JSDoc comment block at the top with example
- [ ] Tests in `__tests__/` folder covering happy path + error cases
- [ ] No hardcoded values (use function parameters or config)
- [ ] Date/number formatting uses `formatHelpers.ts`
- [ ] Async operations handle cleanup (onUnmounted listeners, abort signals)

## References

- `usePagination.ts` — canonical pagination composable example
- `useLoadingState.ts` — loading state wrapper pattern
- `useProbeBackedHealth.ts` — probe-backed health factory (see Probe-Backed Health Pattern above)
- `useHealthProbeRegistry.ts` — `ProbeResponse` type + probe-name registry validation
- `useErrorHandler.ts` — error handling composable pattern
- `formatHelpers.ts` — date/time/number formatting utilities
- `COMPOSABLE_HTTP_PATTERNS.md` — detailed HTTP request patterns

## Composable Example Docs

Each composable has a co-located `.examples.md` with usage patterns and edge cases:

- [useAsyncOperation.examples.md](../../autobot-frontend/src/composables/useAsyncOperation.examples.md)
- [useClipboard.examples.md](../../autobot-frontend/src/composables/useClipboard.examples.md)
- [useConnectionTester.examples.md](../../autobot-frontend/src/composables/useConnectionTester.examples.md)
- [useErrorHandler.examples.md](../../autobot-frontend/src/composables/useErrorHandler.examples.md)
- [useErrorHandler.api-migration.md](../../autobot-frontend/src/composables/useErrorHandler.api-migration.md)
- [useFormValidation.examples.md](../../autobot-frontend/src/composables/useFormValidation.examples.md)
- [useKeyboard.examples.md](../../autobot-frontend/src/composables/useKeyboard.examples.md)
- [useLocalStorage.examples.md](../../autobot-frontend/src/composables/useLocalStorage.examples.md)
- [useModal.examples.md](../../autobot-frontend/src/composables/useModal.examples.md)
- [usePagination.examples.md](../../autobot-frontend/src/composables/usePagination.examples.md)
- [useTimeout.examples.md](../../autobot-frontend/src/composables/useTimeout.examples.md)
- [iconMappings.examples.md](../../autobot-frontend/src/utils/iconMappings.examples.md)

Component examples: [src/components/examples/](../../autobot-frontend/src/components/examples/)
