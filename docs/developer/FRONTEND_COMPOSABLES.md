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
- `useErrorHandler.ts` — error handling composable pattern
- `formatHelpers.ts` — date/time/number formatting utilities
- `COMPOSABLE_HTTP_PATTERNS.md` — detailed HTTP request patterns
