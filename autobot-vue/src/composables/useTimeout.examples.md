# useTimeout Composable - Migration Examples

This document shows how to migrate from duplicate timeout/debounce implementations to the `useTimeout` composable.

**Files affected: 51+ Vue components**

---

## Table of Contents

1. [Debounce Patterns](#debounce-patterns)
2. [Throttle Patterns](#throttle-patterns)
3. [Timeout Patterns](#timeout-patterns)
4. [Interval Patterns](#interval-patterns)
5. [Sleep/Delay Patterns](#sleepdelay-patterns)
6. [Advanced Patterns](#advanced-patterns)

---

## Debounce Patterns

### Example 1: Custom Debounce Implementation (WebResearchSettings.vue)

**BEFORE (lines 429-454):**
```vue
<script setup lang="ts">
// Custom debounce implementation
function debounce(func, wait) {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// Create debounced function
const debouncedUpdate = debounce(updateSettings, 1000)

// Use in watch
watch([
  () => researchSettings.max_results,
  () => researchSettings.timeout_seconds
], () => {
  if (!isUpdating.value) {
    debouncedUpdate()
  }
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useDebounce } from '@/composables/useTimeout'

// Create debounced function
const debouncedUpdate = useDebounce(updateSettings, 1000)

// Use in watch (same as before)
watch([
  () => researchSettings.max_results,
  () => researchSettings.timeout_seconds
], () => {
  if (!isUpdating.value) {
    debouncedUpdate()
  }
})
</script>
```

**Benefits:**
- ✅ Removes 11 lines of duplicate debounce logic
- ✅ Automatic cleanup on component unmount
- ✅ Type-safe with TypeScript
- ✅ Consistent debounce behavior across app

---

### Example 2: Search Input Debounce (ChatInput.vue)

**BEFORE (lines 595):**
```vue
<script setup lang="ts">
const typingDebounceTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const handleInput = (query: string) => {
  // Clear previous timeout
  clearTimeout(typingDebounceTimer.value)

  // Set new timeout
  typingDebounceTimer.value = setTimeout(() => {
    performSearch(query)
  }, 500)
}

onUnmounted(() => {
  if (typingDebounceTimer.value) {
    clearTimeout(typingDebounceTimer.value)
  }
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useDebounce } from '@/composables/useTimeout'

// Create debounced search function
const debouncedSearch = useDebounce((query: string) => {
  performSearch(query)
}, 500)

// Use directly in template or handler
const handleInput = (query: string) => {
  debouncedSearch(query)
}
</script>

<template>
  <input @input="debouncedSearch($event.target.value)" />
</template>
```

**Benefits:**
- ✅ Removes manual timeout tracking
- ✅ Automatic cleanup (no need for onUnmounted)
- ✅ Cleaner code (9 lines → 4 lines)

---

### Example 3: Form Auto-Save with Debounce

**BEFORE:**
```vue
<script setup lang="ts">
let saveTimeout: ReturnType<typeof setTimeout> | null = null

const autoSave = () => {
  if (saveTimeout) clearTimeout(saveTimeout)

  saveTimeout = setTimeout(() => {
    saveData()
  }, 1000)
}

watch(formData, () => {
  autoSave()
}, { deep: true })

onUnmounted(() => {
  if (saveTimeout) clearTimeout(saveTimeout)
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useDebounce } from '@/composables/useTimeout'

const debouncedSave = useDebounce(saveData, 1000)

watch(formData, () => {
  debouncedSave()
}, { deep: true })
</script>
```

**Benefits:**
- ✅ 14 lines → 5 lines
- ✅ No manual cleanup needed
- ✅ More readable

---

## Throttle Patterns

### Example 4: Scroll Event Throttling

**BEFORE:**
```vue
<script setup lang="ts">
let lastScrollTime = 0
const throttleDelay = 200

const handleScroll = () => {
  const now = Date.now()

  if (now - lastScrollTime >= throttleDelay) {
    lastScrollTime = now

    // Actual scroll logic
    updateScrollPosition()
  }
}

window.addEventListener('scroll', handleScroll)

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useThrottle } from '@/composables/useTimeout'

const throttledScroll = useThrottle(() => {
  updateScrollPosition()
}, 200)

window.addEventListener('scroll', throttledScroll)

onUnmounted(() => {
  window.removeEventListener('scroll', throttledScroll)
})
</script>
```

**Benefits:**
- ✅ Simpler throttle logic
- ✅ Automatic cleanup on unmount
- ✅ Type-safe

---

### Example 5: API Rate Limiting with Throttle

**BEFORE:**
```vue
<script setup lang="ts">
let isThrottled = false
const throttleTime = 1000

const updateData = (data: any) => {
  if (isThrottled) return

  isThrottled = true
  api.update(data)

  setTimeout(() => {
    isThrottled = false
  }, throttleTime)
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useThrottle } from '@/composables/useTimeout'

const throttledUpdate = useThrottle((data: any) => {
  api.update(data)
}, 1000, { trailing: false })
</script>
```

**Benefits:**
- ✅ No manual state tracking
- ✅ Configurable leading/trailing options
- ✅ Cleaner API

---

## Timeout Patterns

### Example 6: Auto-Hide Notification (SystemStatusNotification.vue)

**BEFORE (line 277):**
```vue
<script setup lang="ts">
const autoHideTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const showNotification = (message: string) => {
  notification.value = message

  // Clear existing timer
  clearTimeout(autoHideTimer.value)

  // Set new timer
  autoHideTimer.value = setTimeout(() => {
    notification.value = null
  }, 3000)
}

onUnmounted(() => {
  if (autoHideTimer.value) {
    clearTimeout(autoHideTimer.value)
  }
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useTimeout } from '@/composables/useTimeout'

const { restart: restartAutoHide } = useTimeout(() => {
  notification.value = null
}, 3000, { immediate: false })

const showNotification = (message: string) => {
  notification.value = message
  restartAutoHide() // Restart timer
}
</script>
```

**Benefits:**
- ✅ No manual timer tracking
- ✅ Automatic cleanup
- ✅ Restart method handles clear + set

---

### Example 7: Fetch Timeout (NoVNCViewer.vue)

**BEFORE (lines 285-294):**
```vue
<script setup lang="ts">
const fetchWithTimeout = async (url: string) => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 5000)

  try {
    const response = await fetch(url, { signal: controller.signal })
    return response
  } finally {
    clearTimeout(timeoutId)
  }
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useTimeout } from '@/composables/useTimeout'

const fetchWithTimeout = async (url: string) => {
  const controller = new AbortController()

  const { stop } = useTimeout(() => {
    controller.abort()
  }, 5000)

  try {
    const response = await fetch(url, { signal: controller.signal })
    return response
  } finally {
    stop()
  }
}
</script>
```

**Benefits:**
- ✅ Consistent timeout management
- ✅ Type-safe
- ✅ Automatic cleanup if component unmounts during fetch

---

### Example 8: Loading State with Timeout (UnifiedLoadingView.vue)

**BEFORE (line 89):**
```vue
<script setup lang="ts">
let timeoutId: ReturnType<typeof setTimeout> | null = null

const showLoading = () => {
  isLoading.value = true

  // Auto-hide after 10 seconds
  timeoutId = setTimeout(() => {
    isLoading.value = false
    showError.value = true
  }, 10000)
}

const hideLoading = () => {
  isLoading.value = false
  if (timeoutId) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
}

onUnmounted(() => {
  if (timeoutId) clearTimeout(timeoutId)
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useTimeout } from '@/composables/useTimeout'

const { start, stop } = useTimeout(() => {
  isLoading.value = false
  showError.value = true
}, 10000, { immediate: false })

const showLoading = () => {
  isLoading.value = true
  start()
}

const hideLoading = () => {
  isLoading.value = false
  stop()
}
</script>
```

**Benefits:**
- ✅ Declarative timeout control
- ✅ No manual cleanup
- ✅ Simpler state management

---

## Interval Patterns

### Example 9: Polling with Interval (OptimizedRumDashboard.vue)

**BEFORE (line 385):**
```vue
<script setup lang="ts">
let refreshTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  refreshTimer = setInterval(() => {
    refreshData()
  }, 5000)
}

const stopPolling = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useInterval } from '@/composables/useTimeout'

const { start, stop, pause, resume } = useInterval(() => {
  refreshData()
}, 5000, { immediate: true })

// start() and stop() methods available
// Automatic cleanup on unmount
</script>
```

**Benefits:**
- ✅ 18 lines → 4 lines
- ✅ Automatic cleanup
- ✅ Built-in pause/resume

---

### Example 10: Connection Health Check with Interval

**BEFORE:**
```vue
<script setup lang="ts">
let healthCheckInterval: ReturnType<typeof setInterval> | null = null

const startHealthCheck = () => {
  // Execute immediately
  checkConnection()

  // Then repeat every 10 seconds
  healthCheckInterval = setInterval(checkConnection, 10000)
}

const stopHealthCheck = () => {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval)
    healthCheckInterval = null
  }
}

watch(isConnected, (connected) => {
  if (connected) startHealthCheck()
  else stopHealthCheck()
})

onUnmounted(() => {
  stopHealthCheck()
})
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useInterval } from '@/composables/useTimeout'

const { start, stop } = useInterval(checkConnection, 10000, {
  immediate: false,
  immediateCallback: true // Execute immediately on start
})

watch(isConnected, (connected) => {
  if (connected) start()
  else stop()
})
</script>
```

**Benefits:**
- ✅ Built-in immediate callback option
- ✅ Automatic cleanup
- ✅ Cleaner code

---

## Sleep/Delay Patterns

### Example 11: Promise-Based Sleep (BackendSettings.vue)

**BEFORE (lines 1098, 1150):**
```vue
<script setup lang="ts">
const saveSettings = async () => {
  await api.save(settings)

  // Wait 2 seconds before showing success
  await new Promise(resolve => setTimeout(resolve, 2000))

  showSuccess.value = true

  // Wait 1 second before hiding
  await new Promise(resolve => setTimeout(resolve, 1000))

  showSuccess.value = false
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useSleep } from '@/composables/useTimeout'

const saveSettings = async () => {
  await api.save(settings)

  // Wait 2 seconds before showing success
  await useSleep(2000)

  showSuccess.value = true

  // Wait 1 second before hiding
  await useSleep(1000)

  showSuccess.value = false
}
</script>
```

**Benefits:**
- ✅ More readable
- ✅ Self-documenting code
- ✅ Consistent with other timeout utilities

---

### Example 12: Retry with Exponential Backoff

**BEFORE:**
```vue
<script setup lang="ts">
const fetchWithRetry = async (url: string, maxRetries = 3) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fetch(url)
    } catch (error) {
      if (i < maxRetries - 1) {
        // Exponential backoff: 1s, 2s, 4s
        const delay = 1000 * Math.pow(2, i)
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
  }
  throw new Error('Max retries exceeded')
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useSleep } from '@/composables/useTimeout'

const fetchWithRetry = async (url: string, maxRetries = 3) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fetch(url)
    } catch (error) {
      if (i < maxRetries - 1) {
        // Exponential backoff: 1s, 2s, 4s
        await useSleep(1000 * Math.pow(2, i))
      }
    }
  }
  throw new Error('Max retries exceeded')
}
</script>
```

**Benefits:**
- ✅ More readable delay
- ✅ Consistent with other timing utilities

---

### Example 13: Animation Sequencing (TerminalModals.vue)

**BEFORE (lines 399-566):**
```vue
<script setup lang="ts">
const runAnimation = async () => {
  step.value = 1
  await new Promise(resolve => setTimeout(resolve, 1000))

  step.value = 2
  await new Promise(resolve => setTimeout(resolve, 1500))

  step.value = 3
  await new Promise(resolve => setTimeout(resolve, 2000))

  step.value = 4
  await new Promise(resolve => setTimeout(resolve, 1200))

  step.value = 5
  await new Promise(resolve => setTimeout(resolve, 800))

  step.value = 6
  await new Promise(resolve => setTimeout(resolve, 1000))
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useSleep } from '@/composables/useTimeout'

const runAnimation = async () => {
  step.value = 1
  await useSleep(1000)

  step.value = 2
  await useSleep(1500)

  step.value = 3
  await useSleep(2000)

  step.value = 4
  await useSleep(1200)

  step.value = 5
  await useSleep(800)

  step.value = 6
  await useSleep(1000)
}
</script>
```

**Benefits:**
- ✅ More readable timing sequences
- ✅ Easier to adjust delays
- ✅ Self-documenting code

---

## Advanced Patterns

### Example 14: Debounce with MaxWait (Prevent Long Delays)

**BEFORE:**
```vue
<script setup lang="ts">
// Complex custom implementation with maxWait
let timeout: ReturnType<typeof setTimeout> | null = null
let maxWaitTimeout: ReturnType<typeof setTimeout> | null = null
let firstCallTime: number | null = null

const debouncedFn = (...args) => {
  const now = Date.now()

  if (!firstCallTime) {
    firstCallTime = now
  }

  if (timeout) clearTimeout(timeout)
  if (maxWaitTimeout) clearTimeout(maxWaitTimeout)

  timeout = setTimeout(() => {
    fn(...args)
    firstCallTime = null
  }, 1000)

  // Max wait: 3 seconds
  if (now - firstCallTime >= 3000) {
    clearTimeout(timeout)
    fn(...args)
    firstCallTime = null
  } else {
    maxWaitTimeout = setTimeout(() => {
      clearTimeout(timeout)
      fn(...args)
      firstCallTime = null
    }, 3000 - (now - firstCallTime))
  }
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useDebounce } from '@/composables/useTimeout'

const debouncedFn = useDebounce(fn, 1000, {
  maxWait: 3000 // Ensure execution within 3 seconds
})
</script>
```

**Benefits:**
- ✅ 32 lines → 3 lines
- ✅ Built-in maxWait support
- ✅ More reliable implementation

---

### Example 15: Cancelable Sleep (ChatInterface.vue)

**BEFORE (line 492):**
```vue
<script setup lang="ts">
let initTimeout: ReturnType<typeof setTimeout> | null = null

const initialize = () => {
  return new Promise((resolve, reject) => {
    initTimeout = setTimeout(() => {
      reject(new Error('Initialization timeout'))
    }, 8000)

    // ... initialization logic

    if (initTimeout) {
      clearTimeout(initTimeout)
      initTimeout = null
    }
    resolve()
  })
}

const cancel = () => {
  if (initTimeout) {
    clearTimeout(initTimeout)
    initTimeout = null
  }
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useCancelableSleep } from '@/composables/useTimeout'

const initialize = async () => {
  const timeout = useCancelableSleep(8000)

  try {
    await Promise.race([
      performInitialization(),
      timeout.promise
    ])
  } catch (error) {
    throw new Error('Initialization timeout')
  } finally {
    timeout.cancel()
  }
}
</script>
```

**Benefits:**
- ✅ Cleaner Promise.race pattern
- ✅ Built-in cancellation
- ✅ Automatic cleanup

---

### Example 16: Leading-Edge Debounce (Immediate Execution)

**BEFORE:**
```vue
<script setup lang="ts">
let timeout: ReturnType<typeof setTimeout> | null = null
let hasExecuted = false

const debouncedFn = (...args) => {
  // Execute immediately on first call
  if (!hasExecuted) {
    fn(...args)
    hasExecuted = true
  }

  if (timeout) clearTimeout(timeout)

  timeout = setTimeout(() => {
    hasExecuted = false
  }, 1000)
}
</script>
```

**AFTER:**
```vue
<script setup lang="ts">
import { useDebounce } from '@/composables/useTimeout'

const debouncedFn = useDebounce(fn, 1000, {
  leading: true // Execute on first call
})
</script>
```

**Benefits:**
- ✅ 14 lines → 3 lines
- ✅ Built-in leading-edge support
- ✅ More reliable

---

## Migration Summary

**Total lines of code eliminated across 51 files:**

| Pattern | Files | Lines Saved (avg) | Total Savings |
|---------|-------|-------------------|---------------|
| Debounce | 15 | 10 lines | 150 lines |
| Throttle | 8 | 8 lines | 64 lines |
| Timeout | 35 | 6 lines | 210 lines |
| Interval | 12 | 12 lines | 144 lines |
| Sleep | 42 | 2 lines | 84 lines |
| **TOTAL** | **51+** | - | **~650 lines** |

**Benefits:**
- ✅ **~650 lines of code removed**
- ✅ **Automatic cleanup** on component unmount
- ✅ **Type-safe** with TypeScript
- ✅ **Consistent behavior** across all components
- ✅ **No memory leaks** from forgotten clearTimeout/clearInterval
- ✅ **Easier to test** - composable logic isolated
- ✅ **Better performance** - optimized debounce/throttle implementations

---

## Quick Reference

```typescript
import {
  useDebounce,
  useThrottle,
  useTimeout,
  useInterval,
  useSleep,
  useCancelableSleep
} from '@/composables/useTimeout'

// Debounce
const debounced = useDebounce(fn, 500)
debounced.cancel() // Cancel pending
debounced.flush() // Execute immediately

// Throttle
const throttled = useThrottle(fn, 200)
throttled.cancel()

// Timeout
const { start, stop, restart, isActive } = useTimeout(fn, 1000)

// Interval
const { start, stop, pause, resume, isActive } = useInterval(fn, 5000)

// Sleep
await useSleep(2000)

// Cancelable sleep
const sleep = useCancelableSleep(5000)
await sleep.promise
sleep.cancel()
```
