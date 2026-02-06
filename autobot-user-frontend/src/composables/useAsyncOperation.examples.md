# useAsyncOperation Composable - Usage Examples

This document demonstrates how to refactor existing duplicate loading/error patterns using the `useAsyncOperation` composable.

---

## Example 1: Simple API Call with Loading State

### BEFORE (KnowledgeBrowser.vue - Duplicated Pattern)

```typescript
const isLoading = ref(false)
const error = ref<string | null>(null)
const treeData = ref([])

const loadKnowledgeTree = async () => {
  try {
    isLoading.value = true
    error.value = null

    const response = await apiClient.get('/api/knowledge/tree')
    const data = await response.json()
    treeData.value = data.tree
  } catch (err) {
    console.error('Error fetching tree:', err)
    error.value = err.message || 'Failed to load tree'
  } finally {
    isLoading.value = false
  }
}
```

**Lines of code**: 17 lines

### AFTER (Using useAsyncOperation)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'

const { loading: isLoading, error, data: treeData, execute } = useAsyncOperation({
  errorMessage: 'Failed to load knowledge tree',
  onError: (err) => console.error('Error fetching tree:', err)
})

const loadKnowledgeTree = () => execute(async () => {
  const response = await apiClient.get('/api/knowledge/tree')
  const data = await response.json()
  return data.tree
})
```

**Lines of code**: 10 lines
**Savings**: 7 lines (41% reduction)

---

## Example 2: Multiple Operations in Single Component

### BEFORE (KnowledgeBrowser.vue - 3 Separate Loading States)

```typescript
const isLoading = ref(false)
const isLoadingContent = ref(false)
const isLoadingMore = ref<boolean>(false)
const error = ref<string | null>(null)
const contentError = ref<string | null>(null)

const loadKnowledgeTree = async () => {
  try {
    isLoading.value = true
    error.value = null
    // ... API call
  } catch (err) {
    console.error('Error fetching tree:', err)
    error.value = err.message || 'Failed to load tree'
  } finally {
    isLoading.value = false
  }
}

const loadContent = async (fileId: string) => {
  try {
    isLoadingContent.value = true
    contentError.value = null
    // ... API call
  } catch (err) {
    console.error('Error loading content:', err)
    contentError.value = err.message || 'Failed to load content'
  } finally {
    isLoadingContent.value = false
  }
}

const loadMoreEntries = async () => {
  try {
    isLoadingMore.value = true
    // ... API call
  } catch (err) {
    console.error('Error loading more:', err)
  } finally {
    isLoadingMore.value = false
  }
}
```

**Lines of code**: ~50 lines

### AFTER (Using useAsyncOperation)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'

// Create separate operation handlers for each async operation
const tree = useAsyncOperation({
  errorMessage: 'Failed to load knowledge tree',
  onError: (err) => console.error('Error fetching tree:', err)
})

const content = useAsyncOperation({
  errorMessage: 'Failed to load file content',
  onError: (err) => console.error('Error loading content:', err)
})

const pagination = useAsyncOperation({
  onError: (err) => console.error('Error loading more:', err)
})

const loadKnowledgeTree = () => tree.execute(() =>
  apiClient.get('/api/knowledge/tree').then(r => r.json())
)

const loadContent = (fileId: string) => content.execute(() =>
  apiClient.get(`/api/knowledge/content/${fileId}`).then(r => r.json())
)

const loadMoreEntries = () => pagination.execute(() =>
  apiClient.get('/api/knowledge/entries', { cursor: cursor.value }).then(r => r.json())
)
```

**Lines of code**: ~24 lines
**Savings**: 26 lines (52% reduction)

**Template usage**:
```vue
<template>
  <div v-if="tree.loading.value">Loading tree...</div>
  <div v-if="tree.error.value" class="error">{{ tree.error.value.message }}</div>

  <div v-if="content.loading.value">Loading content...</div>
  <div v-if="content.error.value" class="error">{{ content.error.value.message }}</div>

  <button @click="loadMoreEntries" :disabled="pagination.loading.value">
    {{ pagination.loading.value ? 'Loading...' : 'Load More' }}
  </button>
</template>
```

---

## Example 3: Backend Settings Connection Testing

### BEFORE (BackendSettings.vue - 8 Duplicate Test Methods)

```typescript
const isTestingConnection = ref(false)
const connectionStatus = reactive({
  status: 'unknown',
  message: 'Not tested',
  responseTime: null
})

const testConnection = async () => {
  if (isTestingConnection.value) return
  isTestingConnection.value = true
  connectionStatus.status = 'testing'
  connectionStatus.message = 'Testing connection...'

  try {
    const endpoint = props.backendSettings?.api_endpoint || defaultEndpoint
    const startTime = Date.now()
    const response = await fetch(`${endpoint}/health`, { timeout: 5000 })
    const responseTime = Date.now() - startTime
    connectionStatus.responseTime = responseTime

    if (response.ok) {
      connectionStatus.status = 'connected'
      connectionStatus.message = 'Backend connection successful'
    } else {
      connectionStatus.status = 'disconnected'
      connectionStatus.message = `Connection failed (${response.status})`
    }
  } catch (error) {
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Connection error: ${error.message}`
    connectionStatus.responseTime = null
  } finally {
    isTestingConnection.value = false
  }
}

// Repeated 7 more times for: testLLMConnection, testOllamaConnection, etc.
```

**Lines of code**: ~30 lines per test × 8 tests = 240 lines

### AFTER (Using useAsyncOperation)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'

const mainConnection = useAsyncOperation({
  onSuccess: () => {
    connectionStatus.status = 'connected'
    connectionStatus.message = 'Backend connection successful'
  },
  onError: (err) => {
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Connection error: ${err.message}`
  }
})

const ollamaConnection = useAsyncOperation()
const lmstudioConnection = useAsyncOperation()
const openaiConnection = useAsyncOperation()

const testConnection = async () => {
  connectionStatus.status = 'testing'
  connectionStatus.message = 'Testing connection...'

  const startTime = Date.now()
  await mainConnection.execute(async () => {
    const endpoint = props.backendSettings?.api_endpoint || defaultEndpoint
    const response = await fetch(`${endpoint}/health`, { timeout: 5000 })
    connectionStatus.responseTime = Date.now() - startTime

    if (!response.ok) {
      throw new Error(`Connection failed (${response.status})`)
    }
    return response
  })
}

const testOllamaConnection = () => ollamaConnection.execute(() =>
  fetch(llmSettings.local?.providers?.ollama?.endpoint + '/api/tags')
)

// 6 more test methods with similar simplification
```

**Lines of code**: ~60 lines total
**Savings**: 180 lines (75% reduction)

---

## Example 4: Using Success/Error Callbacks

### BEFORE (NPUWorkersSettings.vue)

```typescript
const loading = ref(false)
const error = ref(null)

const saveSettings = async () => {
  try {
    loading.value = true
    error.value = null

    const response = await api.saveSettings(settings)

    // Show success notification
    showNotification('Settings saved successfully', 'success')

    // Refresh data
    await refreshData()
  } catch (err) {
    console.error('Save failed:', err)
    error.value = err.message
    showNotification('Failed to save settings', 'error')
  } finally {
    loading.value = false
  }
}
```

### AFTER (Using useAsyncOperation with Callbacks)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'

const { loading, error, execute } = useAsyncOperation({
  onSuccess: async () => {
    showNotification('Settings saved successfully', 'success')
    await refreshData()
  },
  onError: (err) => {
    console.error('Save failed:', err)
    showNotification('Failed to save settings', 'error')
  }
})

const saveSettings = () => execute(() => api.saveSettings(settings))
```

**Lines of code**: 9 lines vs 17 lines
**Savings**: 8 lines (47% reduction)

---

## Example 5: Using createAsyncOperations Helper

### BEFORE (Multiple Related Operations)

```typescript
const treeLoading = ref(false)
const treeError = ref(null)
const contentLoading = ref(false)
const contentError = ref(null)
const metadataLoading = ref(false)
const metadataError = ref(null)

// 3 separate try/catch blocks...
```

### AFTER (Using Helper Function)

```typescript
import { createAsyncOperations } from '@/composables/useAsyncOperation'

const operations = createAsyncOperations({
  tree: { errorMessage: 'Failed to load tree' },
  content: { errorMessage: 'Failed to load content' },
  metadata: {
    errorMessage: 'Failed to load metadata',
    onSuccess: (data) => console.log('Metadata loaded:', data)
  }
})

// Use: operations.tree.execute(() => api.getTree())
// Use: operations.content.execute(() => api.getContent())
// Use: operations.metadata.execute(() => api.getMetadata())
```

**Lines of code**: 11 lines vs ~60 lines
**Savings**: 49 lines (82% reduction)

---

## Example 6: Computed Helpers for Template Logic

### BEFORE

```typescript
const loading = ref(false)
const error = ref(null)
const data = ref(null)

// Computed properties for UI state
const hasData = computed(() => data.value !== null && !error.value)
const hasError = computed(() => error.value !== null)
const canRetry = computed(() => !loading.value && hasError.value)
```

### AFTER (Using Built-in Computed Helpers)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'

const { loading, error, data, isSuccess, isError, execute } = useAsyncOperation()

// isSuccess = data exists and no error
// isError = error exists
const canRetry = computed(() => !loading.value && isError.value)
```

**Template usage**:
```vue
<template>
  <div v-if="loading">Loading...</div>
  <div v-else-if="isError" class="error">
    {{ error.message }}
    <button v-if="canRetry" @click="retry">Retry</button>
  </div>
  <div v-else-if="isSuccess">
    {{ data }}
  </div>
</template>
```

---

## Example 7: Reset State After Operations

### BEFORE

```typescript
const loading = ref(false)
const error = ref(null)
const data = ref(null)

const clearForm = () => {
  loading.value = false
  error.value = null
  data.value = null
}

// Called on unmount or form reset
onUnmounted(() => {
  loading.value = false
  error.value = null
  data.value = null
})
```

### AFTER (Using reset Method)

```typescript
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { onUnmounted } from 'vue'

const { loading, error, data, execute, reset } = useAsyncOperation()

const clearForm = reset

onUnmounted(reset)
```

---

## Migration Checklist

When refactoring a component to use `useAsyncOperation`:

1. **Identify duplicate patterns**:
   - [ ] Find all `ref(false)` loading states
   - [ ] Find all `ref(null)` error states
   - [ ] Find all try/catch/finally blocks

2. **Replace with composable**:
   - [ ] Import `useAsyncOperation`
   - [ ] Create operation instance(s)
   - [ ] Move try/catch logic into `execute()` calls
   - [ ] Move success/error handling to callbacks

3. **Update templates**:
   - [ ] Replace `loading` refs with `operation.loading`
   - [ ] Replace `error` refs with `operation.error`
   - [ ] Use `isSuccess`/`isError` computed helpers

4. **Test**:
   - [ ] Verify loading states work correctly
   - [ ] Verify error handling displays properly
   - [ ] Verify success callbacks execute
   - [ ] Test concurrent operations (if applicable)

---

## Summary Statistics

| Pattern | Before (lines) | After (lines) | Savings |
|---------|---------------|--------------|---------|
| Simple API call | 17 | 10 | 41% |
| Multiple operations | 50 | 24 | 52% |
| Connection testing (8 tests) | 240 | 60 | 75% |
| With callbacks | 17 | 9 | 47% |
| Multiple related operations | 60 | 11 | 82% |

**Total estimated savings across 40+ components**: 1,200-1,600 lines of code

**Additional benefits**:
- Consistent error handling patterns
- Reduced cognitive load
- Easier testing
- Better TypeScript support
- Standardized loading/error UX
