# AutoBot Frontend Codebase Duplication Analysis Report

**Date**: 2025-10-27
**Scope**: Vue.js components (src/components/), composables (src/composables/), utilities (src/utils/), and services
**Analysis Level**: Medium - Focus on common and high-impact duplications

---

## Executive Summary

The AutoBot frontend codebase shows **good separation of concerns** with existing composables and utilities, but contains **significant duplication opportunities**, particularly in:

- **Loading/Error State Management** (186+ occurrences)
- **API Call Wrapping** (40 components making direct API calls)
- **Validation Patterns** (52+ validation instances with similar logic)
- **Modal/Dialog Management** (35+ modal state variables)
- **Form Input Handling** (30+ input change handlers with similar patterns)

**Duplication Severity**: MEDIUM-HIGH
- Estimated 15-20% of frontend code is duplicated
- Most duplications are in components rather than utilities
- Opportunity to reduce codebase by ~10-15% with proper extraction

---

## TOP 10 DUPLICATE PATTERNS BY IMPACT

### 1. **Loading & Error State Management Pattern** (HIGHEST IMPACT)
**Occurrence**: 186+ instances across 47+ files
**Severity**: HIGH - Repeated in nearly every component with async operations

**Pattern Found**:
```typescript
// Pattern 1: Loading state (appears in 40+ components)
const loading = ref(false)
const error = ref(null)
const isLoading = ref(false)
const isLoadingContent = ref(false)
const isLoadingMore = ref(false)

// Pattern 2: Error handling (appears 52+ times)
try {
  loading.value = true
  // ... API call
  error.value = null
} catch (err) {
  error.value = err.message || 'Error occurred'
  console.error('Error:', err)
} finally {
  loading.value = false
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/KnowledgeBrowser.vue` (3 state vars)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (8 loading states)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/NPUWorkersSettings.vue` (5+ instances)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/MonitoringDashboard.vue` (8+ instances)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/KnowledgeCategories.vue` (2 loading states)
- 42 more components with similar patterns

**Recommendation**: Create composable `useAsyncState` or enhance existing `useUnifiedLoading.ts`
**Estimated Impact**: 30-40 lines of duplicated code per component × 40+ components

---

### 2. **API Call with Error Handling Pattern**
**Occurrence**: 40+ components
**Severity**: HIGH

**Pattern Found**:
```typescript
const refreshStatus = async () => {
  try {
    loading.value = true
    error.value = null
    const response = await apiClient.get('/api/endpoint')
    const data = await response.json()
    // process data
  } catch (err) {
    error.value = err.message || 'Failed to refresh status'
    console.error('Error:', err)
    showSubtleErrorNotification('Error Title', 'Error message', 'error')
  } finally {
    loading.value = false
  }
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (25+ async methods)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/NPUWorkersSettings.vue` (7+ methods)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/composables/useServiceManagement.js` (4 methods with same pattern)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/FailedVectorizationsManager.vue` (multiple methods)

**Status**: PARTIALLY ADDRESSED
- `useApi.ts` provides `useApiWithState()` composable with `withErrorHandling()` wrapper
- Many components NOT using this composable, writing their own try/catch blocks

**Recommendation**: Create composable wrapper `useFetchWithState` or `useAsyncOperation` that combines:
- Loading state management
- Error handling with notifications
- Automatic cleanup in finally block

**Example Usage**:
```typescript
const { loading, error, execute } = useAsyncOperation()

const loadData = () => execute(
  () => apiClient.get('/api/data'),
  { showError: true, errorMessage: 'Failed to load' }
)
```

---

### 3. **Modal/Dialog State Management** (35+ modals)
**Occurrence**: 35 modal state variables across 25+ components
**Severity**: MEDIUM-HIGH

**Pattern Found**:
```typescript
const showDialog = ref(false)
const showModal = ref(false)
const showEditModal = ref(false)
const showDeleteDialog = ref(false)
const visible = ref(false)

// In multiple components:
// SecretsManager.vue: 5 different modal states
// ChatSidebar.vue: 2 modal states
// NPUWorkersSettings.vue: 4 modal states
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/SecretsManager.vue` (5 modals: create, edit, view, transfer, value-view)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/NPUWorkersSettings.vue` (4 modals)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/AdvancedStepConfirmationModal.vue` (5 modals)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/chat/ChatSidebar.vue` (2 modals)

**Recommendation**: Create `useModal` composable
```typescript
const { isOpen, open, close, toggle } = useModal('modalId')
// Usage: v-if="isOpen" @close="close()"
```

**Estimated Impact**: 3-5 lines per modal × 35 modals = 105-175 lines

---

### 4. **Validation Logic Duplication**
**Occurrence**: 52+ validation instances (mainly in settings components)
**Severity**: MEDIUM

**Pattern Found**:
```typescript
// Pattern: URL validation appears in 8+ places
if (!value.startsWith('http://') && !value.startsWith('https://')) {
  validationErrors[key] = 'Must start with http:// or https://'
}

// Pattern: Email validation appears in 3+ places
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
if (!emailRegex.test(value)) {
  validationErrors[key] = 'Invalid email format'
}

// Pattern: Port validation appears in 5+ places
if (value < 1 || value > 65535) {
  validationErrors[key] = 'Port must be between 1 and 65535'
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (lines 859-890, 896-918)
- Multiple form components with manual validation

**Recommendation**: Create validation utility `useFormValidation.ts`
```typescript
const { errors, validate, validateField } = useFormValidation({
  rules: {
    api_endpoint: ['required', 'url'],
    port: ['required', 'number|min:1|max:65535'],
    email: ['required', 'email']
  }
})
```

**Estimated Impact**: 10-15 lines per component × 12+ components

---

### 5. **Connection Testing & Health Check Patterns**
**Occurrence**: 12+ testing methods across 5 components
**Severity**: MEDIUM

**Pattern Found**:
```typescript
const testConnection = async () => {
  if (isTestingConnection.value) return
  isTestingConnection.value = true
  connectionStatus.status = 'testing'

  try {
    const response = await fetch(endpoint, { timeout: 5000 })
    connectionStatus.status = response.ok ? 'connected' : 'disconnected'
    connectionStatus.message = response.ok ? 'Success' : `Failed (${response.status})`
  } catch (error) {
    connectionStatus.status = 'disconnected'
    connectionStatus.message = `Error: ${error.message}`
  } finally {
    isTestingConnection.value = false
  }
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (8+ test methods)
  - `testConnection()` (lines 995-1028)
  - `testLLMConnection()` (lines 1038-1048)
  - `testOllamaConnection()`
  - `testLMStudioConnection()`
  - `testOpenAIConnection()`
  - `testAnthropicConnection()`
  - `testEmbeddingConnection()`
  - `testGPU()`, `testNPU()`

**Recommendation**: Create `useConnectionTester` composable
```typescript
const { testEndpoint, status, isLoading } = useConnectionTester()
await testEndpoint(url, { timeout: 5000, type: 'http' })
```

**Estimated Impact**: 15-25 lines per test method × 12+ methods = 180-300 lines

---

### 6. **Settings Form State & Update Pattern**
**Occurrence**: 30+ setting update handlers
**Severity**: MEDIUM

**Pattern Found**:
```typescript
// Appears in BackendSettings.vue, NPUWorkersSettings.vue, etc.
const updateSetting = (key: string, value: any) => {
  emit('setting-changed', key, value)
}

const updateSettingWithValidation = (key: string, value: any) => {
  delete validationErrors[key]
  const validation = validateSetting(key, value)
  if (validation.isValid) {
    validationSuccess[key] = true
    emit('setting-changed', key, value)
  } else {
    validationErrors[key] = validation.error
  }
}

const updateLLMSetting = (key: string, value: any) => {
  emit('llm-setting-changed', key, value)
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (lines 838-973)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/UISettings.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/CacheSettings.vue`

**Recommendation**: Create `useSettingsForm` composable
```typescript
const form = useSettingsForm(validationRules)
form.updateField(key, value)
form.validateField(key)
form.submit()
```

---

### 7. **Search/Filter State Management**
**Occurrence**: 15+ search implementations
**Severity**: MEDIUM-LOW

**Pattern Found**:
```typescript
const searchQuery = ref('')
const isSearching = ref(false)

const handleSearch = () => {
  // filter logic
}

const clearSearch = () => {
  searchQuery.value = ''
  // reload data
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/KnowledgeBrowser.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/ManPageManager.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/LogViewer.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/stores/useKnowledgeStore.ts`
- 10+ other components

**Recommendation**: Create `useSearch` composable (similar to existing patterns)

---

### 8. **API Response Parsing Pattern**
**Occurrence**: 8+ implementations
**Severity**: MEDIUM-LOW

**Pattern Found**:
```typescript
const parseResponse = async (response: any): Promise<any> => {
  if (typeof response.json === 'function') {
    return await response.json()
  }
  return response
}

// Found in:
// - KnowledgeBrowser.vue (line 225-231)
// - useKnowledgeBase.ts (line 77-111)
// - Multiple other files
```

**Recommendation**: Consolidate into utility or extend ApiClient

---

### 9. **Pagination/Cursor-based Loading**
**Occurrence**: 13+ components with pagination
**Severity**: MEDIUM

**Pattern Found**:
```typescript
const hasMoreEntries = ref(true)
const isLoadingMore = ref(false)
const cursor = ref(null)

const loadMoreEntries = async () => {
  if (isLoadingMore.value || !hasMoreEntries.value) return
  isLoadingMore.value = true
  try {
    const response = await api.list({ cursor: cursor.value })
    entries.value.push(...response.data)
    cursor.value = response.nextCursor
    hasMoreEntries.value = !!response.hasMore
  } finally {
    isLoadingMore.value = false
  }
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/KnowledgeBrowser.vue` (line 158-168)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/KnowledgeEntries.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/LogViewer.vue`

**Recommendation**: Create `usePagination` composable

---

### 10. **Icon/Status Mapping Helper Functions**
**Occurrence**: 10+ components
**Severity**: LOW-MEDIUM

**Pattern Found**:
```typescript
// Appears in 10+ files
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
    'testing': 'fas fa-spinner fa-spin'
  }
  return iconMap[status] || 'fas fa-question-circle'
}
```

**Files with Duplication**:
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/settings/BackendSettings.vue` (line 975-993)
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/SystemStatusIndicator.vue`
- `/home/kali/Desktop/AutoBot/autobot-vue/src/components/ConnectionStatus.vue`

**Recommendation**: Move to utility file `src/utils/iconMappings.ts`

---

## COMPOSABLE USAGE ANALYSIS

**Current Composables** (in `/src/composables/`):
- ✅ `useApi.ts` - Good API wrapper with error handling
- ✅ `useKnowledgeBase.ts` - Knowledge-specific utilities
- ✅ `useServiceManagement.js` - Service lifecycle management (excellent pattern!)
- ✅ `useHealthMonitoring.js` - Health check wrapper
- ✅ `useUnifiedLoading.ts` - Loading state management
- ✅ `useChatHistory.js` - Chat history management
- ⚠️ `useKnowledgeVectorization.ts` - Some repetition with useKnowledgeBase
- ❌ Missing: `useAsyncState` / `useAsyncOperation`
- ❌ Missing: `useModal` / `useDialog`
- ❌ Missing: `useFormValidation`
- ❌ Missing: `useConnectionTester`
- ❌ Missing: `usePagination`

**Composable Adoption Rate**: Only 26 out of 60+ components use composables

---

## RECOMMENDATIONS FOR SHARED UTILITIES

### Priority 1: Create `useAsyncOperation.ts` Composable
**Impact**: HIGH (saves 30-40 lines per component × 40+ components)
**Effort**: LOW (2-3 hours)

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
```

### Priority 2: Create `useModal.ts` Composable
**Impact**: MEDIUM (saves 3-5 lines per modal × 35 modals)
**Effort**: LOW (1-2 hours)

```typescript
// src/composables/useModal.ts
export function useModal(modalId: string) {
  const isOpen = ref(false)
  const open = () => { isOpen.value = true }
  const close = () => { isOpen.value = false }
  const toggle = () => { isOpen.value = !isOpen.value }
  return { isOpen, open, close, toggle }
}
```

### Priority 3: Create `useFormValidation.ts` Composable
**Impact**: MEDIUM (saves 15-30 lines per form × 12+ forms)
**Effort**: MEDIUM (3-4 hours)

```typescript
// src/composables/useFormValidation.ts
export function useFormValidation(rules: ValidationRules) {
  const errors = reactive({})
  const touched = reactive({})

  const validateField = (field: string, value: any) => {
    const fieldRules = rules[field]
    // validation logic
  }

  const validateForm = (formData: Record<string, any>) => {
    // validate all fields
  }

  return { errors, touched, validateField, validateForm }
}
```

### Priority 4: Create `useConnectionTester.ts` Composable
**Impact**: MEDIUM (saves 15-25 lines per test × 12 tests)
**Effort**: MEDIUM (2-3 hours)

### Priority 5: Extract Icon Mappings Utility
**Impact**: LOW-MEDIUM (saves 10-15 lines per component)
**Effort**: LOW (1 hour)

**File**: `src/utils/iconMappings.ts`
```typescript
export const statusIconMap = {
  healthy: 'fas fa-check-circle',
  warning: 'fas fa-exclamation-triangle',
  error: 'fas fa-times-circle',
  // ... more mappings
}

export const getIconForStatus = (status: string, type: 'health' | 'connection' = 'health') => {
  // return appropriate icon
}
```

### Priority 6: Create `usePagination.ts` Composable
**Impact**: MEDIUM (saves 20-30 lines per paginated component × 13 components)
**Effort**: MEDIUM (2-3 hours)

---

## FILE STRUCTURE RECOMMENDATIONS

### Suggested New Directory Structure
```
src/
├── composables/          (currently good)
│   ├── useAsyncOperation.ts       [NEW - HIGH PRIORITY]
│   ├── useModal.ts                [NEW - MEDIUM PRIORITY]
│   ├── useFormValidation.ts       [NEW - MEDIUM PRIORITY]
│   ├── usePagination.ts           [NEW - MEDIUM PRIORITY]
│   ├── useConnectionTester.ts     [NEW - MEDIUM PRIORITY]
│   ├── useApi.ts                  [EXISTS - good]
│   ├── useKnowledgeBase.ts        [EXISTS - minor refactoring needed]
│   └── ...other composables
│
├── utils/
│   ├── iconMappings.ts            [NEW - LOW PRIORITY]
│   ├── validators.ts              [NEW - consolidate validation rules]
│   ├── ApiClient.ts               [EXISTS - good]
│   └── ...other utilities
│
└── components/
    ├── composables/               [or rename to "shared/"]
    │   ├── ModalBase.vue
    │   ├── FormBase.vue
    │   └── AsyncOperationWrapper.vue
    └── ...existing components
```

---

## QUICK WINS (Low Effort, High Impact)

1. **Extract Icon Mappings** (1 hour)
   - Create `src/utils/iconMappings.ts`
   - Reduces visual duplication across 10+ files

2. **Create useModal Composable** (1-2 hours)
   - Simple, high usage (35+ modals)
   - Eliminates repetitive state management

3. **Consolidate useApi usages** (2-3 hours)
   - Audit all components using direct API calls
   - Replace with `useApi()` composable calls

4. **Create Base Validation Rules** (2 hours)
   - Consolidate regex patterns
   - Create shared validation rules object

---

## ESTIMATED IMPACT SUMMARY

| Pattern | Duplication Count | Lines to Save | Priority | Effort |
|---------|------------------|---------------|----------|--------|
| Loading/Error State | 40+ components | 1,200-1,600 | HIGH | HIGH |
| API Call Wrapping | 25+ components | 750-1,000 | HIGH | HIGH |
| Modal Management | 35 modals | 105-175 | MEDIUM | LOW |
| Form Validation | 12+ components | 180-360 | MEDIUM | MEDIUM |
| Connection Testing | 12 methods | 180-300 | MEDIUM | MEDIUM |
| Settings Updates | 30+ handlers | 300-600 | MEDIUM | MEDIUM |
| Search/Filter | 15+ components | 150-225 | MEDIUM | LOW |
| Pagination | 13 components | 260-390 | MEDIUM | MEDIUM |
| Icon Mappings | 10+ components | 100-150 | LOW | LOW |

**TOTAL POTENTIAL SAVINGS**: 3,225-5,195 lines of code (10-15% reduction)

---

## IMPLEMENTATION ROADMAP

### Phase 1 (Week 1): Foundation
1. Create `useAsyncOperation.ts` composable
2. Create `useModal.ts` composable
3. Extract `iconMappings.ts` utility
4. Audit and document all validation patterns

### Phase 2 (Week 2): Consolidation
1. Create `useFormValidation.ts` composable
2. Create `useConnectionTester.ts` composable
3. Refactor 15-20 highest-duplication components

### Phase 3 (Week 3-4): Extended Cleanup
1. Create `usePagination.ts` composable
2. Consolidate remaining API patterns
3. Refactor remaining components
4. Tests and documentation

---

## CONCLUSION

The AutoBot frontend codebase demonstrates good architecture with the presence of composables and services. However, there are **significant opportunities** for code reuse, particularly in:

1. **Async state management** (loading + error handling)
2. **Modal/dialog management**
3. **Form validation patterns**
4. **API testing utilities**

By implementing the recommended composables and utilities, the frontend can reduce duplication by **10-15%** while improving:
- Code maintainability
- Consistency across components
- Developer velocity
- Testing coverage

The recommended composables follow Vue 3 composition API best practices and leverage existing infrastructure like `useApi.ts` and `useServiceManagement.js`.
