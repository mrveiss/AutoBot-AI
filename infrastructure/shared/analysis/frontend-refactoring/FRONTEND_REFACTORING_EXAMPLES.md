# Frontend Code Refactoring Examples

This document provides concrete before/after examples for the identified duplicate patterns.

---

## Pattern 1: Loading & Error State Management

### BEFORE: Duplicated in 40+ Components
```typescript
// src/components/knowledge/KnowledgeBrowser.vue
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

const loadContent = async () => {
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

### AFTER: Using `useAsyncOperation` Composable
```typescript
// src/composables/useAsyncOperation.ts
export function useAsyncOperation() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const execute = async <T>(
    operation: () => Promise<T>,
    options = {
      showError: true,
      errorMessage: 'Operation failed',
      silent: false
    }
  ): Promise<T | null> => {
    loading.value = true
    error.value = null
    try {
      return await operation()
    } catch (err) {
      error.value = err.message || options.errorMessage
      if (options.showError && !options.silent) {
        showSubtleErrorNotification('Error', error.value)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  return { loading, error, execute }
}

// In component (refactored)
// src/components/knowledge/KnowledgeBrowser.vue
const tree = useAsyncOperation()
const content = useAsyncOperation()
const pagination = useAsyncOperation()

const loadKnowledgeTree = () => tree.execute(
  () => apiClient.get('/api/knowledge/tree'),
  { errorMessage: 'Failed to load knowledge tree' }
)

const loadContent = () => content.execute(
  () => apiClient.get(`/api/knowledge/content/${selectedFile.id}`),
  { errorMessage: 'Failed to load file content' }
)

const loadMoreEntries = () => pagination.execute(
  () => apiClient.get('/api/knowledge/entries', { cursor: cursor.value }),
  { silent: true } // No user notification for pagination
)
```

**Savings**: 30-40 lines per component × 40+ components = 1,200-1,600 lines

---

## Pattern 2: Modal/Dialog State Management

### BEFORE: Duplicated in 35+ Modals
```typescript
// src/components/SecretsManager.vue
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showViewModal = ref(false)
const showTransferModal = ref(false)
const showSecretValue = ref(false)

// Multiple open/close handlers
const openCreateModal = () => { showCreateModal.value = true }
const closeCreateModal = () => { showCreateModal.value = false }
const openEditModal = () => { showEditModal.value = true }
const closeEditModal = () => { showEditModal.value = false }
// ... repeats for each modal
```

### AFTER: Using `useModal` Composable
```typescript
// src/composables/useModal.ts
export function useModal(modalId: string) {
  const isOpen = ref(false)
  const open = () => { isOpen.value = true }
  const close = () => { isOpen.value = false }
  const toggle = () => { isOpen.value = !isOpen.value }

  return { isOpen, open, close, toggle }
}

// In component (refactored)
// src/components/SecretsManager.vue
const createModal = useModal('create')
const editModal = useModal('edit')
const viewModal = useModal('view')
const transferModal = useModal('transfer')
const valueModal = useModal('value')

// Template
<div v-if="createModal.isOpen" class="modal">
  <button @click="createModal.close">Close</button>
</div>

<div v-if="editModal.isOpen" class="modal">
  <button @click="editModal.close">Close</button>
</div>
```

**Savings**: 3-5 lines per modal × 35 modals = 105-175 lines

---

## Pattern 3: Validation Logic

### BEFORE: Scattered Validation Rules
```typescript
// src/components/settings/BackendSettings.vue
const validateSetting = (key: string, value: any) => {
  switch (key) {
    case 'api_endpoint':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'API endpoint is required' }
      }
      if (!value.startsWith('http://') && !value.startsWith('https://')) {
        return { isValid: false, error: 'Must start with http:// or https://' }
      }
      return { isValid: true }

    case 'server_host':
      if (!value || typeof value !== 'string') {
        return { isValid: false, error: 'Server host is required' }
      }
      const hostRegex = /^[a-zA-Z0-9.-]+$/
      if (!hostRegex.test(value)) {
        return { isValid: false, error: 'Invalid host format' }
      }
      return { isValid: true }

    case 'server_port':
      if (!value || isNaN(value) || value < 1 || value > 65535) {
        return { isValid: false, error: 'Port must be between 1 and 65535' }
      }
      return { isValid: true }
  }
}

// Similar validation in 10+ other components
```

### AFTER: Using `useFormValidation` Composable
```typescript
// src/composables/useFormValidation.ts
export function useFormValidation(rules: Record<string, any>) {
  const errors = reactive({})
  const touched = reactive({})

  const validationRules = {
    required: (value: any) => value ? null : 'This field is required',
    url: (value: string) => /^https?:\/\/.+/.test(value) ? null : 'Must be a valid URL',
    port: (value: number) => (value >= 1 && value <= 65535) ? null : 'Port must be between 1-65535',
    email: (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? null : 'Invalid email',
    hostname: (value: string) => /^[a-zA-Z0-9.-]+$/.test(value) ? null : 'Invalid hostname'
  }

  const validateField = (field: string, value: any) => {
    const fieldRules = rules[field] || []
    for (const rule of fieldRules) {
      const error = validationRules[rule]?.(value)
      if (error) {
        errors[field] = error
        return false
      }
    }
    delete errors[field]
    touched[field] = true
    return true
  }

  return { errors, touched, validateField }
}

// In component (refactored)
// src/components/settings/BackendSettings.vue
const { errors, validateField } = useFormValidation({
  api_endpoint: ['required', 'url'],
  server_host: ['required', 'hostname'],
  server_port: ['required', 'port']
})

const updateSetting = (key: string, value: any) => {
  if (validateField(key, value)) {
    emit('setting-changed', key, value)
  }
}

// Template
<div class="setting-item">
  <input
    v-model="settings.api_endpoint"
    @input="updateSetting('api_endpoint', $event.target.value)"
    :class="{ 'error': errors.api_endpoint }"
  />
  <div v-if="errors.api_endpoint" class="error-message">
    {{ errors.api_endpoint }}
  </div>
</div>
```

**Savings**: 10-15 lines per form × 12+ forms = 120-180 lines

---

## Pattern 4: Connection Testing

### BEFORE: Repeated Test Logic (8+ times in BackendSettings.vue)
```typescript
// src/components/settings/BackendSettings.vue
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

const testLLMConnection = async () => {
  // Nearly identical logic
}

const testOllamaConnection = async () => {
  // Nearly identical logic
}

// ... 5 more similar methods
```

### AFTER: Using `useConnectionTester` Composable
```typescript
// src/composables/useConnectionTester.ts
export function useConnectionTester() {
  const status = reactive({
    current: 'unknown',
    message: 'Not tested',
    responseTime: null
  })
  const isLoading = ref(false)

  const testEndpoint = async (
    url: string,
    options = {
      timeout: 5000,
      type: 'http',
      endpoint: '/health'
    }
  ) => {
    if (isLoading.value) return
    isLoading.value = true
    status.current = 'testing'
    status.message = 'Testing connection...'

    try {
      const fullUrl = `${url}${options.endpoint}`
      const startTime = Date.now()
      const response = await fetch(fullUrl, { timeout: options.timeout })
      status.responseTime = Date.now() - startTime

      if (response.ok) {
        status.current = 'connected'
        status.message = 'Connection successful'
      } else {
        status.current = 'disconnected'
        status.message = `Connection failed (${response.status})`
      }
    } catch (error) {
      status.current = 'disconnected'
      status.message = `Connection error: ${error.message}`
      status.responseTime = null
    } finally {
      isLoading.value = false
    }
  }

  return { status, isLoading, testEndpoint }
}

// In component (refactored)
const mainConnection = useConnectionTester()
const ollamaConnection = useConnectionTester()
const lmstudioConnection = useConnectionTester()

const testConnection = () => mainConnection.testEndpoint(
  props.backendSettings?.api_endpoint || defaultEndpoint,
  { endpoint: '/health' }
)

const testOllamaConnection = () => ollamaConnection.testEndpoint(
  llmSettings.local?.providers?.ollama?.endpoint,
  { endpoint: '/api/tags' }
)

const testLMStudioConnection = () => lmstudioConnection.testEndpoint(
  llmSettings.local?.providers?.lmstudio?.endpoint,
  { endpoint: '/v1/models' }
)
```

**Savings**: 15-25 lines per test × 8 tests = 120-200 lines

---

## Pattern 5: Icon Mappings

### BEFORE: Duplicated in 10+ Components
```typescript
// src/components/settings/BackendSettings.vue
const getHealthIconClass = (status: string) => {
  const iconMap = {
    'healthy': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

const getConnectionIcon = (status: string) => {
  const iconMap = {
    'connected': 'fas fa-check-circle',
    'disconnected': 'fas fa-times-circle',
    'testing': 'fas fa-spinner fa-spin',
    'unknown': 'fas fa-question-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

// Similar in SystemStatusIndicator.vue, ConnectionStatus.vue, etc.
```

### AFTER: Using Shared Utility
```typescript
// src/utils/iconMappings.ts
export const statusIconMap = {
  healthy: 'fas fa-check-circle',
  warning: 'fas fa-exclamation-triangle',
  error: 'fas fa-times-circle',
  unknown: 'fas fa-question-circle'
}

export const connectionIconMap = {
  connected: 'fas fa-check-circle',
  disconnected: 'fas fa-times-circle',
  testing: 'fas fa-spinner fa-spin',
  unknown: 'fas fa-question-circle'
}

export const getIcon = (status: string, type: 'health' | 'connection' = 'health') => {
  const map = type === 'health' ? statusIconMap : connectionIconMap
  return map[status] || map.unknown
}

// In components (refactored)
import { getIcon } from '@/utils/iconMappings'

// Template
<i :class="getIcon(status.status, 'health')"></i>
<i :class="getIcon(connectionStatus.status, 'connection')"></i>
```

**Savings**: 10-15 lines per component × 10 components = 100-150 lines

---

## Pattern 6: Pagination Logic

### BEFORE: Duplicated in 13+ Components
```typescript
// src/components/knowledge/KnowledgeBrowser.vue
const hasMoreEntries = ref(true)
const isLoadingMore = ref<boolean>(false)
const cursor = ref<string | null>(null)

const loadMoreEntries = async () => {
  if (isLoadingMore.value || !hasMoreEntries.value) return

  isLoadingMore.value = true
  try {
    const response = await apiClient.get('/api/knowledge/entries', {
      cursor: cursor.value
    })

    const data = await response.json()
    entries.value.push(...data.entries)
    cursor.value = data.cursor
    hasMoreEntries.value = data.has_more
  } catch (error) {
    console.error('Error loading more:', error)
  } finally {
    isLoadingMore.value = false
  }
}

// Similar logic in KnowledgeEntries.vue, LogViewer.vue, etc.
```

### AFTER: Using `usePagination` Composable
```typescript
// src/composables/usePagination.ts
export function usePagination<T>(fetchFn: (cursor: string | null) => Promise<any>) {
  const items = ref<T[]>([])
  const isLoading = ref(false)
  const cursor = ref<string | null>(null)
  const hasMore = ref(true)

  const loadMore = async () => {
    if (isLoading.value || !hasMore.value) return

    isLoading.value = true
    try {
      const response = await fetchFn(cursor.value)
      items.value.push(...response.items)
      cursor.value = response.cursor
      hasMore.value = response.hasMore
    } catch (error) {
      console.error('Pagination error:', error)
    } finally {
      isLoading.value = false
    }
  }

  const reset = () => {
    items.value = []
    cursor.value = null
    hasMore.value = true
  }

  return { items, isLoading, hasMore, loadMore, reset }
}

// In component (refactored)
const entries = usePagination<KnowledgeEntry>(
  (cursor) => apiClient.get('/api/knowledge/entries', { cursor }).then(r => r.json())
)

// Template
<div v-for="entry in entries.items" :key="entry.id">
  {{ entry.name }}
</div>
<button v-if="entries.hasMore" @click="entries.loadMore" :disabled="entries.isLoading">
  Load More
</button>
```

**Savings**: 20-30 lines per component × 13 components = 260-390 lines

---

## IMPLEMENTATION CHECKLIST

### Phase 1: Core Composables (Week 1)
- [ ] Create `useAsyncOperation.ts`
  - [ ] Write composable
  - [ ] Add TypeScript types
  - [ ] Write unit tests
  - [ ] Document with examples

- [ ] Create `useModal.ts`
  - [ ] Write composable
  - [ ] Add TypeScript types
  - [ ] Write unit tests
  - [ ] Update 5 components

- [ ] Extract `iconMappings.ts`
  - [ ] Create utility file
  - [ ] Test with 3+ components

### Phase 2: Form & Validation (Week 2)
- [ ] Create `useFormValidation.ts`
  - [ ] Write composable
  - [ ] Define validation rules library
  - [ ] Write unit tests
  - [ ] Document validation rules

- [ ] Create `useConnectionTester.ts`
  - [ ] Write composable
  - [ ] Add retry logic
  - [ ] Refactor BackendSettings.vue

### Phase 3: Advanced Patterns (Week 3-4)
- [ ] Create `usePagination.ts`
- [ ] Create `useSearch.ts`
- [ ] Consolidate remaining patterns
- [ ] Update component documentation

---

## MIGRATION GUIDE

### For Component Developers

When you find yourself writing this pattern:
```typescript
const loading = ref(false)
const error = ref(null)
try {
  loading.value = true
  // ... API call
} catch (err) {
  error.value = err.message
} finally {
  loading.value = false
}
```

Use this instead:
```typescript
const { loading, error, execute } = useAsyncOperation()
execute(() => apiClient.get('/api/endpoint'), { errorMessage: 'Failed to load' })
```

### For Modal/Dialog Developers

When you find yourself writing:
```typescript
const showMyModal = ref(false)
const openMyModal = () => { showMyModal.value = true }
const closeMyModal = () => { showMyModal.value = false }
```

Use this instead:
```typescript
const myModal = useModal('myModal')
// Call myModal.open(), myModal.close(), myModal.toggle()
```

---

## REFERENCES

- Full Analysis Report: `/FRONTEND_DUPLICATION_ANALYSIS.md`
- Composable Patterns: `src/composables/useServiceManagement.js`
- Existing API Wrapper: `src/composables/useApi.ts`
