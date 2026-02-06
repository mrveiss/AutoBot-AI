# Icon Mappings Utility - Migration Examples

This document demonstrates how to migrate existing components to use the centralized `iconMappings.ts` utility.

---

## Table of Contents

1. [BackendSettings.vue Migration](#backendsettingsvue-migration)
2. [MonitoringDashboard.vue Migration](#monitoringdashboardvue-migration)
3. [MCPDashboard.vue Migration](#mcpdashboardvue-migration)
4. [Terminal.vue Migration](#terminalvue-migration)
5. [Quick Reference](#quick-reference)

---

## BackendSettings.vue Migration

### ❌ BEFORE (Lines 975-993)

```typescript
const getHealthIconClass = (status: string) => {
  const iconMap = {
    'healthy': 'fas fa-check-circle',
    'warning': 'fas fa-exclamation-triangle',
    'error': 'fas fa-times-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}

// NEW: Enhanced connection testing methods
const getConnectionIcon = (status: string) => {
  const iconMap = {
    'connected': 'fas fa-check-circle',
    'disconnected': 'fas fa-times-circle',
    'testing': 'fas fa-spinner fa-spin',
    'unknown': 'fas fa-question-circle'
  }
  return iconMap[status] || 'fas fa-question-circle'
}
```

**Lines to Remove**: 18 lines (975-993)

### ✅ AFTER

```typescript
import { getStatusIcon, getConnectionIcon } from '@/utils/iconMappings'

// No local functions needed! Use imported functions directly in template.
```

**Template Changes:**

```vue
<!-- BEFORE -->
<i :class="getHealthIconClass(systemHealth.status)"></i>
<i :class="getConnectionIcon(connectionStatus.status)"></i>

<!-- AFTER -->
<i :class="getStatusIcon(systemHealth.status)"></i>
<i :class="getConnectionIcon(connectionStatus.status)"></i>
```

**Savings**: 18 lines removed, 1 import added = **17 lines saved**

---

## MonitoringDashboard.vue Migration

### ❌ BEFORE (Lines 884-892)

```javascript
getStatusIcon(status) {
  switch (status) {
    case 'healthy': return 'fas fa-check-circle'
    case 'degraded': return 'fas fa-exclamation-triangle'
    case 'critical': return 'fas fa-times-circle'
    case 'offline': return 'fas fa-power-off'
    default: return 'fas fa-question-circle'
  }
},
```

**Lines to Remove**: 9 lines

### ✅ AFTER

```vue
<script setup lang="ts">
import { getStatusIcon } from '@/utils/iconMappings'
</script>

<template>
  <i :class="getStatusIcon(service.status)"></i>
</template>
```

**Savings**: 9 lines removed, 1 import added = **8 lines saved**

**Bonus**: Now supports additional statuses ('warning', 'error') automatically!

---

## MCPDashboard.vue Migration

### ❌ BEFORE (Lines 214-221)

```javascript
const getStatusIcon = (status) => {
  switch (status) {
    case 'healthy': return 'fas fa-check-circle text-success'
    case 'warning': return 'fas fa-exclamation-triangle text-warning'
    case 'error': return 'fas fa-times-circle text-danger'
    default: return 'fas fa-question-circle text-muted'
  }
}
```

**Lines to Remove**: 8 lines

### ✅ AFTER

```vue
<script setup lang="ts">
import { getStatusIcon } from '@/utils/iconMappings'
</script>

<template>
  <!-- Now with color support built-in -->
  <i :class="getStatusIcon(health.frontend.status, { withColor: true })"></i>
  <i :class="getStatusIcon(health.backend.status, { withColor: true })"></i>
  <i :class="getStatusIcon(health.api.status, { withColor: true })"></i>
  <i :class="getStatusIcon(health.websocket.status, { withColor: true })"></i>
</template>
```

**Savings**: 8 lines removed, 1 import added = **7 lines saved**

**Bonus**: Color classes now centralized and consistent!

---

## Terminal.vue Migration

### ❌ BEFORE (Computed Properties)

```typescript
const connectionIconClass = computed(() => {
  const status = connectionStatus.value
  switch (status) {
    case 'connected': return 'fas fa-check-circle text-success'
    case 'disconnected': return 'fas fa-times-circle text-danger'
    case 'connecting': return 'fas fa-spinner fa-spin text-info'
    default: return 'fas fa-question-circle text-muted'
  }
})

const statusIconClass = computed(() => {
  const status = terminalStatus.value
  switch (status) {
    case 'ready': return 'fas fa-check-circle text-success'
    case 'error': return 'fas fa-times-circle text-danger'
    case 'loading': return 'fas fa-spinner fa-spin text-info'
    default: return 'fas fa-question-circle text-muted'
  }
})
```

**Lines to Remove**: ~18 lines

### ✅ AFTER

```typescript
import { getConnectionIcon, getStatusIcon } from '@/utils/iconMappings'

// Simplified computed properties
const connectionIconClass = computed(() =>
  getConnectionIcon(connectionStatus.value, { withColor: true })
)

const statusIconClass = computed(() =>
  getStatusIcon(terminalStatus.value, { withColor: true })
)
```

**Savings**: 18 lines → 6 lines = **12 lines saved**

---

## Quick Reference

### Common Patterns

#### Pattern 1: Simple Status Icon

```vue
<!-- BEFORE -->
<i :class="status === 'healthy' ? 'fas fa-check-circle' : 'fas fa-times-circle'"></i>

<!-- AFTER -->
<i :class="getStatusIcon(status)"></i>
```

#### Pattern 2: Status Icon with Color

```vue
<!-- BEFORE -->
<i :class="[
  status === 'healthy' ? 'fas fa-check-circle text-success' :
  status === 'error' ? 'fas fa-times-circle text-danger' :
  'fas fa-question-circle text-muted'
]"></i>

<!-- AFTER -->
<i :class="getStatusIcon(status, { withColor: true })"></i>
```

#### Pattern 3: Connection Testing

```vue
<!-- BEFORE -->
<i :class="isTesting ? 'fas fa-spinner fa-spin' : 'fas fa-check-circle'"></i>

<!-- AFTER -->
<i :class="getConnectionIcon(isTesting ? 'testing' : 'connected')"></i>
```

#### Pattern 4: Action Buttons

```vue
<!-- BEFORE -->
<button>
  <i :class="isLoading ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
  Save
</button>

<!-- AFTER -->
<button>
  <i :class="getActionIcon(isLoading ? 'loading' : 'save')"></i>
  Save
</button>
```

#### Pattern 5: Custom Classes

```vue
<!-- BEFORE -->
<i class="fas fa-check-circle mr-2 text-lg"></i>

<!-- AFTER -->
<i :class="getStatusIcon('healthy', { extraClasses: 'mr-2 text-lg' })"></i>
```

---

## Migration Checklist

For each component using icon mappings:

- [ ] Import `getStatusIcon`, `getConnectionIcon`, or `getActionIcon` from `@/utils/iconMappings`
- [ ] Remove local icon mapping functions/objects
- [ ] Replace icon class logic in template with utility functions
- [ ] Add `{ withColor: true }` option if component used color classes
- [ ] Test component to ensure icons display correctly
- [ ] Remove any unused imports

---

## Statistics

**Estimated Savings Across All Components:**

| Component | Lines Before | Lines After | Saved |
|-----------|--------------|-------------|-------|
| BackendSettings.vue | 18 | 1 | 17 |
| MonitoringDashboard.vue | 9 | 1 | 8 |
| MCPDashboard.vue | 8 | 1 | 7 |
| Terminal.vue | 18 | 6 | 12 |
| ToolsTerminal.vue | ~15 | 6 | 9 |
| SystemStatusIndicator.vue | ~12 | 1 | 11 |
| MultiMachineHealth.vue | ~10 | 1 | 9 |
| ServiceItem.vue | ~8 | 1 | 7 |
| ... (6+ more components) | ~60 | 6 | 54 |
| **TOTAL** | **~158** | **~24** | **~134** |

**Total Estimated Savings: 134 lines of duplicate code eliminated**

---

## TypeScript Support

The utility includes full TypeScript support:

```typescript
import type { StatusType, ConnectionType, ActionType, IconOptions } from '@/utils/iconMappings'

// Type-safe usage
const status: StatusType = 'healthy'
const icon = getStatusIcon(status) // ✅ Type-safe

// With options
const options: IconOptions = {
  withColor: true,
  extraClasses: 'mr-2'
}
const iconWithOptions = getStatusIcon(status, options) // ✅ Type-safe
```

---

## Next Steps

1. ✅ **Created**: `iconMappings.ts` utility
2. 📋 **Next**: Migrate 2-3 components as proof-of-concept
3. 📋 **Then**: Migrate remaining components systematically
4. 📋 **Finally**: Update component development standards

---

**Created**: 2025-10-27
**Author**: AutoBot Frontend Refactoring Initiative
**Part of**: Priority 2 - Medium Impact Composables/Utilities
