# useAsyncOperation Quick Reference

Fast reference for using the async operation composable in AutoBot components.

## Import

```typescript
import { useAsyncOperation, createAsyncOperations } from '@/composables/useAsyncOperation'
```

## Basic Usage

```typescript
// Create operation
const operation = useAsyncOperation({
  errorMessage: 'Failed to load data'
})

// Execute async function
const loadData = () => operation.execute(() => api.get('/endpoint'))

// Use in template
<div v-if="operation.loading.value">Loading...</div>
<div v-if="operation.error.value">{{ operation.error.value.message }}</div>
<div v-if="operation.data.value">{{ operation.data.value }}</div>
```

## Common Patterns

### 1. Simple GET Request

```typescript
// Example using /api/llm/models - a real endpoint that returns a list
const models = useAsyncOperation({ errorMessage: 'Failed to load models' })

const fetchModels = () => models.execute(async () => {
  const response = await fetch('/api/llm/models')
  return response.json()
})
```

### 2. POST with Success Notification

```typescript
const saveOp = useAsyncOperation({
  onSuccess: () => showNotification('Saved successfully!'),
  errorMessage: 'Failed to save'
})

const saveData = () => saveOp.execute(() =>
  fetch('/api/save', { method: 'POST', body: JSON.stringify(data) })
)
```

### 3. Custom Error Handling

```typescript
const deleteOp = useAsyncOperation({
  onError: (err) => {
    console.error('Delete failed:', err)
    logToAnalytics('delete_error', err.message)
  },
  errorMessage: 'Failed to delete item'
})

const deleteItem = (id: string) => deleteOp.execute(() =>
  api.delete(`/items/${id}`)
)
```

### 4. Multiple Operations

```typescript
const ops = createAsyncOperations({
  users: { errorMessage: 'Failed to load users' },
  posts: { errorMessage: 'Failed to load posts' },
  comments: { onSuccess: () => console.log('Comments loaded') }
})

// Use individual operations
const loadUsers = () => ops.users.execute(() => api.get('/users'))
const loadPosts = () => ops.posts.execute(() => api.get('/posts'))

// Load concurrently
const loadAll = () => Promise.all([loadUsers(), loadPosts()])
```

### 5. Data Transformation

```typescript
interface TransformedData { /* ... */ }

const operation = useAsyncOperation<TransformedData>({
  errorMessage: 'Failed to load data'
})

const loadData = () => operation.execute(async () => {
  const raw = await api.get('/endpoint')
  return {
    // Transform inline
    name: raw.user.name,
    total: raw.items.length,
    average: calculateAverage(raw.values)
  }
})
```

### 6. Sequential Operations

```typescript
const step1 = useAsyncOperation()
const step2 = useAsyncOperation()

const processWorkflow = async () => {
  // Wait for step1 before starting step2
  const result1 = await step1.execute(() => api.post('/step1'))
  const result2 = await step2.execute(() => api.post('/step2', result1))
  return result2
}
```

### 7. Conditional Execution

```typescript
const operation = useAsyncOperation()

const conditionalLoad = async () => {
  if (someCondition) {
    await operation.execute(() => api.get('/endpoint1'))
  } else {
    await operation.execute(() => api.get('/endpoint2'))
  }
}
```

### 8. Reset After Form Submit

```typescript
const submitOp = useAsyncOperation({
  onSuccess: () => {
    submitOp.reset() // Clear state after success
    form.value = {} // Reset form
  }
})
```

## API Reference

### useAsyncOperation\<T\>(options?)

Returns an object with:

| Property | Type | Description |
|----------|------|-------------|
| `loading` | `Ref<boolean>` | True during execution |
| `error` | `Ref<Error \| null>` | Error object if failed |
| `data` | `Ref<T \| null>` | Resolved data if successful |
| `isSuccess` | `ComputedRef<boolean>` | True if data exists and no error |
| `isError` | `ComputedRef<boolean>` | True if error exists |
| `execute` | `(fn: () => Promise<T>) => Promise<T>` | Execute async function |
| `reset` | `() => void` | Clear all states |

### Options

```typescript
interface AsyncOperationOptions<T> {
  onSuccess?: (data: T) => void        // Success callback
  onError?: (error: Error) => void     // Error callback
  initialLoading?: boolean             // Initial loading state (default: false)
  errorMessage?: string                // Error message prefix
}
```

### createAsyncOperations(configs)

Helper to create multiple operations:

```typescript
const ops = createAsyncOperations({
  operation1: { errorMessage: 'Error 1' },
  operation2: { onSuccess: (data) => console.log(data) },
  operation3: {}
})

// Returns: { operation1: AsyncOperationReturn, operation2: AsyncOperationReturn, ... }
```

## Template Usage

### Loading State

```vue
<button :disabled="operation.loading.value">
  {{ operation.loading.value ? 'Loading...' : 'Load Data' }}
</button>

<div v-if="operation.loading.value" class="spinner">Loading...</div>
```

### Error Display

```vue
<div v-if="operation.error.value" class="error">
  {{ operation.error.value.message }}
</div>

<div v-if="operation.isError.value" class="error-banner">
  Operation failed!
</div>
```

### Success State

```vue
<div v-if="operation.isSuccess.value" class="success">
  Operation completed successfully!
</div>

<div v-if="operation.data.value">
  <pre>{{ JSON.stringify(operation.data.value, null, 2) }}</pre>
</div>
```

### Conditional Rendering

```vue
<!-- Show loading OR error OR data -->
<div v-if="operation.loading.value">Loading...</div>
<div v-else-if="operation.error.value">Error: {{ operation.error.value.message }}</div>
<div v-else-if="operation.data.value">Data: {{ operation.data.value }}</div>
<div v-else>No data yet</div>
```

## Common Mistakes

### ❌ Forgetting .value in Template

```vue
<!-- WRONG -->
<div v-if="operation.loading">...</div>

<!-- CORRECT -->
<div v-if="operation.loading.value">...</div>
```

### ❌ Not Handling Errors

```typescript
// WRONG - Error not displayed
const operation = useAsyncOperation()

// CORRECT - Custom error message
const operation = useAsyncOperation({
  errorMessage: 'Failed to load data'
})
```

### ❌ Creating Multiple Operations for Same State

```typescript
// WRONG - Duplicate operations
const loadOp = useAsyncOperation()
const refreshOp = useAsyncOperation()

// CORRECT - Reuse same operation
const dataOp = useAsyncOperation()
const loadData = () => dataOp.execute(() => api.get('/data'))
const refreshData = () => dataOp.execute(() => api.get('/data'))
```

### ❌ Not Using Async Execute

```typescript
// WRONG - Not awaiting when needed
const process = () => {
  operation.execute(() => api.get('/data'))
  doSomethingElse() // Runs before API call completes!
}

// CORRECT - Await if order matters
const process = async () => {
  await operation.execute(() => api.get('/data'))
  doSomethingElse() // Runs after API call completes
}
```

## TypeScript Tips

### Explicit Type Parameter

```typescript
interface User {
  id: number
  name: string
}

const users = useAsyncOperation<User[]>()
// users.data.value is typed as User[] | null
```

### Type Inference

```typescript
const operation = useAsyncOperation()

// Example using /api/llm/models - demonstrates type inference with real endpoint
const loadModels = () => operation.execute(async (): Promise<LLMModel[]> => {
  const response = await fetch('/api/llm/models')
  return response.json()
})
// operation.data.value is inferred as LLMModel[] | null
```

### Generic Callbacks

```typescript
interface SaveResponse {
  id: string
  timestamp: number
}

const saveOp = useAsyncOperation<SaveResponse>({
  onSuccess: (data) => {
    // data is typed as SaveResponse
    console.log('Saved with ID:', data.id)
  }
})
```

## Performance Tips

1. **Reuse operations** - Don't create new operations on every render
2. **Use createAsyncOperations** - When you have multiple operations
3. **Clear data when appropriate** - Use `reset()` to free memory
4. **Avoid unnecessary executions** - Check conditions before calling `execute()`

## Debugging Tips

### Check Current State

```typescript
console.log('Loading:', operation.loading.value)
console.log('Error:', operation.error.value)
console.log('Data:', operation.data.value)
console.log('Is Success:', operation.isSuccess.value)
console.log('Is Error:', operation.isError.value)
```

### Track Execution

```typescript
const operation = useAsyncOperation({
  onSuccess: (data) => console.log('✅ Success:', data),
  onError: (err) => console.error('❌ Error:', err)
})
```

### Vue DevTools

All reactive properties (`loading`, `error`, `data`) are visible in Vue DevTools under the component's reactive state.

## Migration Checklist

When refactoring existing code:

- [ ] Import `useAsyncOperation` composable
- [ ] Replace `ref(false)` loading states with `operation.loading`
- [ ] Replace `ref<Error | null>(null)` with `operation.error`
- [ ] Replace data refs with `operation.data`
- [ ] Move try-catch-finally to `execute()` call
- [ ] Move post-success logic to `onSuccess` callback
- [ ] Move error handling to `onError` callback
- [ ] Update template to use `operation.loading.value`, etc.
- [ ] Remove manual state management code
- [ ] Test all code paths (success, error, loading)

## Examples

See `AsyncOperationExample.vue` for comprehensive working examples of all patterns.

## Questions?

- Check the full documentation: `README.md` in this directory
- View the source: `src/composables/useAsyncOperation.ts`
- Review examples: `AsyncOperationExample.vue`

---

**Quick Tip**: When in doubt, start with the simplest pattern and add callbacks only when needed!
