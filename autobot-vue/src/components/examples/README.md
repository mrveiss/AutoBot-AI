# useAsyncOperation Composable Examples

This directory contains practical examples demonstrating the `useAsyncOperation` composable pattern used throughout the AutoBot Vue 3 application.

## Overview

The `useAsyncOperation` composable provides a standardized way to handle async operations with automatic loading/error state management, eliminating duplicate patterns found across 40+ components.

## Example Component

**File**: `AsyncOperationExample.vue`

A comprehensive demonstration component showcasing 5 real-world patterns with before/after code comparisons.

### Patterns Demonstrated

#### 1. Simple Async Operation (53% code reduction)
- Basic health check with automatic loading and error states
- **Before**: 15 lines of manual state management
- **After**: 7 lines with composable
- **Key benefit**: Automatic state lifecycle management

#### 2. Operation with Success Callback (59% code reduction)
- Save settings with automatic notification on success
- **Before**: 22 lines including notification logic
- **After**: 9 lines with `onSuccess` callback
- **Key benefit**: Cleaner separation of concerns

#### 3. Custom Error Handling (56% code reduction)
- Validate configuration with custom error logging
- **Before**: 25 lines with manual error handling
- **After**: 11 lines with `onError` callback
- **Key benefit**: Consistent error handling pattern

#### 4. Multiple Concurrent Operations (55% code reduction)
- Load users and system info using `createAsyncOperations` helper
- **Before**: 40 lines with duplicate state for each operation
- **After**: 18 lines with helper function
- **Key benefit**: DRY principle for multiple operations

#### 5. Data Transformation (60% code reduction)
- Fetch and transform analytics data
- **Before**: 30 lines with manual state + transformation
- **After**: 12 lines with inline transformation
- **Key benefit**: Focus on business logic, not state management

### Overall Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Lines | 132 | 57 | **57% reduction** |
| State Variables | 15 | 0 (managed by composable) | **100% reduction** |
| Error Handling | Manual in each function | Automatic + callbacks | **Standardized** |
| Type Safety | Mixed | Full TypeScript support | **Enhanced** |

## How to View the Example

### Option 1: Add to Router (Recommended for testing)

Add to `autobot-vue/src/router/index.ts`:

```typescript
{
  path: '/examples/async-operations',
  name: 'async-operations-example',
  component: () => import('@/components/examples/AsyncOperationExample.vue'),
  meta: { title: 'Async Operations Examples' }
}
```

Then navigate to: `http://172.16.168.21:5173/#/examples/async-operations`

### Option 2: Direct Component Import

Import directly in any view for testing:

```vue
<template>
  <AsyncOperationExample />
</template>

<script setup lang="ts">
import AsyncOperationExample from '@/components/examples/AsyncOperationExample.vue'
</script>
```

## Key Benefits Demonstrated

### 🎯 Code Consistency
All async operations follow the same pattern across the codebase, making the code easier to:
- **Read**: Consistent structure across all components
- **Review**: Familiar patterns for code reviewers
- **Maintain**: Changes to async patterns centralized in composable

### 📉 Reduced Boilerplate
Average 57% reduction in async handling code means:
- **Faster development**: Less boilerplate to write
- **Fewer bugs**: Less code = fewer places for bugs
- **Easier refactoring**: Changes in one place, not scattered

### 🔒 Type Safety
Full TypeScript support with generics:
```typescript
const analytics = useAsyncOperation<AnalyticsData>({
  errorMessage: 'Failed to load analytics'
})
// analytics.data.value is typed as AnalyticsData | null
```

### 🧪 Easier Testing
Mock the `execute()` function instead of managing state:
```typescript
// Before: Mock useState, catch blocks, finally blocks
// After: Mock single execute function
vi.spyOn(asyncOp, 'execute').mockResolvedValue(mockData)
```

### 🎨 Cleaner Templates
Use computed helpers for conditional rendering:
```vue
<div v-if="operation.loading.value">Loading...</div>
<div v-if="operation.isError.value">Error!</div>
<div v-if="operation.isSuccess.value">Success!</div>
```

## When to Use Each Pattern

### Simple Operation
Use when you need basic async operation without callbacks:
```typescript
const operation = useAsyncOperation({
  errorMessage: 'Failed to load data'
})
```

### Success Callback
Use when you need to execute side effects on success:
```typescript
const operation = useAsyncOperation({
  onSuccess: (data) => {
    // Show notification
    // Update related state
    // Navigate to next page
  }
})
```

### Error Callback
Use when you need custom error handling:
```typescript
const operation = useAsyncOperation({
  onError: (error) => {
    // Log to analytics
    // Custom error recovery
    // User-specific error messages
  }
})
```

### Multiple Operations
Use `createAsyncOperations` helper when component has multiple independent operations:
```typescript
const ops = createAsyncOperations({
  users: { errorMessage: 'Failed to load users' },
  posts: { errorMessage: 'Failed to load posts' },
  comments: { onSuccess: () => console.log('Comments loaded') }
})
```

### Data Transformation
Use when you need to transform API responses:
```typescript
const operation = useAsyncOperation<TransformedType>({
  errorMessage: 'Failed to load data'
})

const loadData = () => operation.execute(async () => {
  const rawData = await api.get('/endpoint')
  return transformData(rawData) // Transform inline
})
```

## Migration Guide

### Step 1: Identify Async Pattern

Look for this pattern in existing code:
```typescript
const loading = ref(false)
const error = ref<Error | null>(null)
const data = ref(null)

const loadData = async () => {
  loading.value = true
  error.value = null
  try {
    data.value = await api.get('/endpoint')
  } catch (err) {
    error.value = err
  } finally {
    loading.value = false
  }
}
```

### Step 2: Replace with Composable

```typescript
const operation = useAsyncOperation({
  errorMessage: 'Failed to load data'
})

const loadData = () => operation.execute(() => api.get('/endpoint'))
```

### Step 3: Update Template References

```vue
<!-- Before -->
<div v-if="loading">Loading...</div>
<div v-if="error">{{ error.message }}</div>
<div v-if="data">{{ data }}</div>

<!-- After -->
<div v-if="operation.loading.value">Loading...</div>
<div v-if="operation.error.value">{{ operation.error.value.message }}</div>
<div v-if="operation.data.value">{{ operation.data.value }}</div>
```

### Step 4: Add Callbacks (Optional)

If you had post-success/error logic, move to callbacks:
```typescript
const operation = useAsyncOperation({
  onSuccess: (data) => {
    // Your post-success logic here
  },
  onError: (err) => {
    // Your custom error handling here
  },
  errorMessage: 'Failed to load data'
})
```

## Testing the Example

### Prerequisites
- Backend running on `http://172.16.168.20:8001`
- Frontend dev server on `http://172.16.168.21:5173`

### Expected Behavior

**Example 1 (Health Check)**:
- Click "Check Health" button
- Should show loading spinner
- Should display health data or error message
- Reset button should clear state

**Example 2 (Save Settings)**:
- Enter value in input field
- Click "Save Settings"
- Should show loading state
- Should show success notification (green toast)
- Notification auto-dismisses after 3 seconds

**Example 3 (Validate Config)**:
- Click "Validate Configuration"
- Should show loading state
- On error: shows error message + adds to error log
- Error log persists across operations

**Example 4 (Multiple Operations)**:
- Click "Load All Data"
- Both sections show loading simultaneously
- Each section displays its data independently
- Errors are isolated per operation

**Example 5 (Analytics)**:
- Click "Load Analytics"
- Should show loading state
- Should display transformed data in cards
- Data transformation happens automatically

### Mock API Responses

If backend endpoints don't exist, the examples will fail gracefully with error messages. This is intentional to demonstrate error handling.

For testing without backend, you can modify the fetch calls to return mock data:

```typescript
const checkHealth = () => health.execute(async () => {
  // Mock response for testing
  await new Promise(resolve => setTimeout(resolve, 1000))
  return { status: 'healthy', timestamp: Date.now() }
})
```

## Implementation Notes

### Concurrent Calls
The composable handles concurrent calls using "latest wins" strategy:
- All calls execute in parallel
- State reflects the most recently completed operation
- For sequential execution, use `await execute()` before next call

### Error Re-throwing
Errors are re-thrown after being stored, allowing upstream error handling:
```typescript
try {
  await operation.execute(() => api.get('/endpoint'))
} catch (err) {
  // Custom upstream handling if needed
  // Error is already stored in operation.error
}
```

### Type Safety
Full TypeScript support with generic type parameter:
```typescript
interface User { id: number; name: string }
const users = useAsyncOperation<User[]>()
// users.data.value is typed as User[] | null
```

### Reset Functionality
Use `reset()` to clear all states:
```typescript
// Clear loading, error, and data
operation.reset()

// Useful for:
// - Form submission cleanup
// - Component unmount
// - Manual state reset
```

## Production Refactoring Candidates

Based on the patterns in this example, these AutoBot components are good candidates for refactoring:

1. **BackendSettings.vue** - 8 async operations with duplicate state management
2. **NPUWorkersSettings.vue** - 6 async operations with similar patterns
3. **KnowledgeBase.vue** - Multiple file upload operations
4. **ChatView.vue** - Message sending with loading states
5. **DesktopStream.vue** - VNC connection handling
6. **TerminalPanel.vue** - Terminal command execution

Each of these could see 50-60% code reduction using the composable pattern.

## Further Reading

- **Composable Source**: `autobot-vue/src/composables/useAsyncOperation.ts`
- **Vue 3 Composition API**: https://vuejs.org/guide/extras/composition-api-faq.html
- **TypeScript Generics**: https://www.typescriptlang.org/docs/handbook/2/generics.html

## Questions & Feedback

If you encounter issues or have questions about the composable:
1. Check the source code documentation in `useAsyncOperation.ts`
2. Review this example component for usage patterns
3. Test your implementation with the patterns shown here
4. Consider edge cases demonstrated in the examples

---

**Last Updated**: 2025-10-27
**Maintainer**: AutoBot Frontend Team
**Related**: `/autobot-vue/src/composables/useAsyncOperation.ts`
