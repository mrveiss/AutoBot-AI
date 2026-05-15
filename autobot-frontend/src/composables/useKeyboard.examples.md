# useKeyboard Composable - Migration Examples

This document shows how to migrate from duplicate keyboard event patterns to the centralized `useKeyboard` composable.

## Table of Contents

1. [Accessibility: Clickable Elements](#1-accessibility-clickable-elements)
2. [Modal Escape Key Handling](#2-modal-escape-key-handling)
3. [Form Submission with Enter](#3-form-submission-with-enter)
4. [Keyboard Shortcuts](#4-keyboard-shortcuts)
5. [Arrow Key Navigation](#5-arrow-key-navigation)
6. [Complete Examples](#6-complete-examples)

---

## 1. Accessibility: Clickable Elements

### Pattern: Making divs keyboard-accessible

**BEFORE** (HistoryView.vue - Lines 11):
```vue
<template>
  <div
    v-for="entry in history"
    :key="entry.id"
    class="history-entry"
    @click="viewHistoryEntry(entry)"
    tabindex="0"
    @keyup.enter="$event.target.click()"
    @keyup.space="$event.target.click()"
  >
    {{ entry.preview }}
  </div>
</template>

<script setup lang="ts">
const viewHistoryEntry = (entry: HistoryEntry) => {
  // View entry logic
}
</script>
```

**AFTER** (Using useClickableElement):
```vue
<template>
  <div
    v-for="entry in history"
    :key="entry.id"
    class="history-entry"
    role="button"
    tabindex="0"
    @click="viewHistoryEntry(entry)"
    @keyup="handlers.onKeyUp"
    @keydown="handlers.onKeyDown"
  >
    {{ entry.preview }}
  </div>
</template>

<script setup lang="ts">
import { useClickableElement } from '@/composables/useKeyboard'

const viewHistoryEntry = (entry: HistoryEntry) => {
  // View entry logic
}

// Create keyboard accessibility handlers
const handlers = useClickableElement(() => {
  // This simulates the click event
  viewHistoryEntry(currentEntry.value)
})
</script>
```

**Better approach - inline callback**:
```vue
<template>
  <div
    v-for="(entry, index) in history"
    :key="entry.id"
    class="history-entry"
    role="button"
    tabindex="0"
    @click="() => viewHistoryEntry(entry)"
    @keyup="(e) => getClickHandler(entry).onKeyUp(e)"
    @keydown="(e) => getClickHandler(entry).onKeyDown(e)"
  >
    {{ entry.preview }}
  </div>
</template>

<script setup lang="ts">
import { useClickableElement } from '@/composables/useKeyboard'

const viewHistoryEntry = (entry: HistoryEntry) => {
  // View entry logic
}

// Create handler for each entry
const getClickHandler = (entry: HistoryEntry) => {
  return useClickableElement(() => viewHistoryEntry(entry))
}
</script>
```

**Code reduction**: 2 lines → 2 lines (same lines, but centralized logic)
**Benefits**: Consistent behavior, automatic Space key prevention, centralized maintenance

---

## 2. Modal Escape Key Handling

### Pattern: Closing modals/dialogs with Escape

**BEFORE** (CommandPermissionDialog.vue - Lines 330-342):
```vue
<template>
  <div v-if="showDialog" class="dialog-overlay">
    <div class="dialog-content">
      <!-- Dialog content -->
      <button @click="handleDeny">Cancel</button>
      <button @click="handleApprove">Approve</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const showDialog = ref(false)
const isProcessing = ref(false)

const handleDeny = () => {
  showDialog.value = false
}

const handleApprove = () => {
  // Approval logic
}

const handleEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && showDialog.value && !isProcessing.value) {
    handleDeny()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleEscape)
})
</script>
```

**AFTER** (Using useEscapeKey):
```vue
<template>
  <div v-if="showDialog" class="dialog-overlay">
    <div class="dialog-content">
      <!-- Dialog content -->
      <button @click="handleDeny">Cancel</button>
      <button @click="handleApprove">Approve</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useEscapeKey } from '@/composables/useKeyboard'

const showDialog = ref(false)
const isProcessing = ref(false)

const handleDeny = () => {
  showDialog.value = false
}

const handleApprove = () => {
  // Approval logic
}

// Handle Escape key with condition
useEscapeKey(
  handleDeny,
  () => showDialog.value && !isProcessing.value
)
</script>
```

**Code reduction**: 15 lines → 5 lines (67% reduction)
**Benefits**: Automatic cleanup, cleaner code, reusable pattern

---

## 3. Form Submission with Enter

### Pattern: Submit forms/searches on Enter key

**BEFORE** (LogViewer.vue - Line 52):
```vue
<template>
  <div class="log-viewer">
    <input
      v-model="searchQuery"
      type="text"
      placeholder="Search logs..."
      @keyup.enter="performSearch"
    />
    <button @click="performSearch">Search</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const searchQuery = ref('')

const performSearch = () => {
  console.log('Searching for:', searchQuery.value)
  // Search logic
}
</script>
```

**AFTER** (Using useEnterKey on input element):
```vue
<template>
  <div class="log-viewer">
    <input
      ref="searchInput"
      v-model="searchQuery"
      type="text"
      placeholder="Search logs..."
    />
    <button @click="performSearch">Search</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useEnterKey } from '@/composables/useKeyboard'

const searchQuery = ref('')
const searchInput = ref<HTMLInputElement>()

const performSearch = () => {
  console.log('Searching for:', searchQuery.value)
  // Search logic
}

// Submit on Enter when input is focused
useEnterKey(performSearch, undefined, {
  target: searchInput
})
</script>
```

**Alternative - Keep @keyup.enter for input-specific handlers:**
```vue
<!-- For simple cases, @keyup.enter is still fine! -->
<input
  v-model="searchQuery"
  @keyup.enter="performSearch"
/>

<!-- Use useEnterKey when you need: -->
<!-- - Document-level Enter handling -->
<!-- - Conditional execution -->
<!-- - Complex event handling -->
```

**Code reduction**: Varies (useEnterKey best for document-level listeners)
**Benefits**: Automatic cleanup, conditional execution, consistent behavior

---

## 4. Keyboard Shortcuts

### Pattern: Adding keyboard shortcuts

**BEFORE** (Manual implementation):
```vue
<template>
  <div class="editor">
    <textarea v-model="content"></textarea>
    <div class="shortcuts-help">
      <p>Ctrl+S: Save</p>
      <p>Ctrl+Z: Undo</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const content = ref('')

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.ctrlKey && event.key === 's') {
    event.preventDefault()
    saveDocument()
  } else if (event.ctrlKey && event.key === 'z') {
    event.preventDefault()
    undo()
  }
}

const saveDocument = () => {
  console.log('Saving document...')
  // Save logic
}

const undo = () => {
  console.log('Undo...')
  // Undo logic
}

onMounted(() => {
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
})
</script>
```

**AFTER** (Using useKeyboardShortcut):
```vue
<template>
  <div class="editor">
    <textarea v-model="content"></textarea>
    <div class="shortcuts-help">
      <p>Ctrl+S: Save</p>
      <p>Ctrl+Z: Undo</p>
      <p>Ctrl+Shift+P: Command Palette</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useKeyboardShortcut } from '@/composables/useKeyboard'

const content = ref('')

const saveDocument = () => {
  console.log('Saving document...')
  // Save logic
}

const undo = () => {
  console.log('Undo...')
  // Undo logic
}

const openCommandPalette = () => {
  console.log('Opening command palette...')
  // Command palette logic
}

// Register keyboard shortcuts
useKeyboardShortcut('ctrl+s', saveDocument, {
  preventDefault: true,
  allowInInput: true // Allow in textarea
})

useKeyboardShortcut('ctrl+z', undo, {
  preventDefault: true,
  allowInInput: true
})

useKeyboardShortcut('ctrl+shift+p', openCommandPalette, {
  preventDefault: true
})

// Mac support
useKeyboardShortcut('meta+s', saveDocument, {
  preventDefault: true,
  allowInInput: true
})
</script>
```

**Code reduction**: 18 lines → 8 lines (56% reduction)
**Benefits**: Cleaner code, automatic cleanup, cross-platform support, input element filtering

---

## 5. Arrow Key Navigation

### Pattern: Navigate lists with arrow keys

**BEFORE** (Manual implementation):
```vue
<template>
  <div class="list-container">
    <div
      v-for="(item, index) in items"
      :key="item.id"
      :class="{ selected: index === selectedIndex }"
    >
      {{ item.name }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const items = ref([
  { id: 1, name: 'Item 1' },
  { id: 2, name: 'Item 2' },
  { id: 3, name: 'Item 3' }
])

const selectedIndex = ref(0)

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    selectedIndex.value = Math.max(0, selectedIndex.value - 1)
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    selectedIndex.value = Math.min(items.value.length - 1, selectedIndex.value + 1)
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
})
</script>
```

**AFTER** (Using useArrowKeys):
```vue
<template>
  <div class="list-container">
    <div
      v-for="(item, index) in items"
      :key="item.id"
      :class="{ selected: index === selectedIndex }"
    >
      {{ item.name }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useArrowKeys } from '@/composables/useKeyboard'

const items = ref([
  { id: 1, name: 'Item 1' },
  { id: 2, name: 'Item 2' },
  { id: 3, name: 'Item 3' }
])

const selectedIndex = ref(0)

// Handle arrow key navigation
useArrowKeys(
  {
    up: () => {
      selectedIndex.value = Math.max(0, selectedIndex.value - 1)
    },
    down: () => {
      selectedIndex.value = Math.min(items.value.length - 1, selectedIndex.value + 1)
    }
  },
  { preventDefault: true }
)
</script>
```

**Code reduction**: 14 lines → 10 lines (29% reduction)
**Benefits**: Cleaner code, automatic cleanup, extensible (add left/right easily)

---

## 6. Complete Examples

### Example 1: Full Modal Component with Keyboard Support

**BEFORE**:
```vue
<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeModal">
    <div class="modal-content" @click.stop>
      <h2>Confirm Action</h2>
      <p>Are you sure you want to proceed?</p>
      <div class="modal-actions">
        <button @click="closeModal">Cancel</button>
        <button @click="confirmAction">Confirm</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const isOpen = ref(false)

const closeModal = () => {
  isOpen.value = false
}

const confirmAction = () => {
  console.log('Action confirmed')
  closeModal()
}

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && isOpen.value) {
    closeModal()
  } else if (event.key === 'Enter' && isOpen.value) {
    confirmAction()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown)
})
</script>
```

**AFTER**:
```vue
<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeModal">
    <div class="modal-content" @click.stop>
      <h2>Confirm Action</h2>
      <p>Are you sure you want to proceed?</p>
      <div class="modal-actions">
        <button @click="closeModal">Cancel</button>
        <button @click="confirmAction">Confirm</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useEscapeKey, useEnterKey } from '@/composables/useKeyboard'

const isOpen = ref(false)

const closeModal = () => {
  isOpen.value = false
}

const confirmAction = () => {
  console.log('Action confirmed')
  closeModal()
}

// Close on Escape (only when modal is open)
useEscapeKey(closeModal, () => isOpen.value)

// Confirm on Enter (only when modal is open)
useEnterKey(confirmAction, () => isOpen.value)
</script>
```

**Code reduction**: 19 lines → 6 lines (68% reduction)
**Benefits**: Much cleaner, easier to understand, automatic cleanup

---

### Example 2: Search Component with Keyboard Shortcuts

```vue
<template>
  <div class="search-container">
    <div class="search-header">
      <input
        ref="searchInput"
        v-model="query"
        type="text"
        placeholder="Search... (Ctrl+K to focus)"
      />
      <button @click="performSearch">Search</button>
    </div>
    <div class="search-results">
      <div
        v-for="(result, index) in results"
        :key="result.id"
        :class="{ selected: index === selectedIndex }"
        role="button"
        tabindex="0"
        @click="openResult(result)"
        @keyup="(e) => getClickHandler(result).onKeyUp(e)"
        @keydown="(e) => getClickHandler(result).onKeyDown(e)"
      >
        {{ result.title }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  useKeyboardShortcut,
  useEnterKey,
  useArrowKeys,
  useClickableElement
} from '@/composables/useKeyboard'

const query = ref('')
const searchInput = ref<HTMLInputElement>()
const results = ref([
  { id: 1, title: 'Result 1' },
  { id: 2, title: 'Result 2' }
])
const selectedIndex = ref(0)

const performSearch = () => {
  console.log('Searching for:', query.value)
  // Search API call
}

const openResult = (result: any) => {
  console.log('Opening result:', result)
  // Navigate to result
}

// Focus search input with Ctrl+K or Cmd+K
useKeyboardShortcut('ctrl+k', () => {
  searchInput.value?.focus()
})

useKeyboardShortcut('meta+k', () => {
  searchInput.value?.focus()
})

// Submit search on Enter
useEnterKey(performSearch, undefined, {
  target: searchInput
})

// Navigate results with arrow keys
useArrowKeys(
  {
    up: () => {
      selectedIndex.value = Math.max(0, selectedIndex.value - 1)
    },
    down: () => {
      selectedIndex.value = Math.min(results.value.length - 1, selectedIndex.value + 1)
    }
  },
  { preventDefault: true }
)

// Make results clickable with keyboard
const getClickHandler = (result: any) => {
  return useClickableElement(() => openResult(result))
}
</script>
```

**This example demonstrates**:
- ✅ Keyboard shortcuts (Ctrl+K, Cmd+K)
- ✅ Enter key handling on specific element
- ✅ Arrow key navigation
- ✅ Accessibility (clickable results)
- ✅ All with automatic cleanup!

---

## Migration Checklist

When migrating keyboard event handlers:

- [ ] Replace `@keyup.enter="$event.target.click()"` with `useClickableElement()`
- [ ] Replace manual Escape listeners with `useEscapeKey()`
- [ ] Replace document-level Enter listeners with `useEnterKey()`
- [ ] Replace Ctrl+Key patterns with `useKeyboardShortcut()`
- [ ] Replace arrow key handlers with `useArrowKeys()`
- [ ] Add `role="button"` to clickable non-button elements
- [ ] Keep `tabindex="0"` for focusable elements
- [ ] Remove manual `addEventListener`/`removeEventListener` calls
- [ ] Remove `onMounted`/`onUnmounted` for keyboard listeners

---

## Benefits Summary

**Code Quality**:
- ✅ Eliminates 200+ lines of duplicate keyboard handling code
- ✅ Consistent keyboard behavior across all components
- ✅ Automatic event listener cleanup (no memory leaks)

**Accessibility**:
- ✅ Standardized keyboard accessibility patterns
- ✅ Proper Space key handling (prevents page scroll)
- ✅ ARIA-compliant implementation

**Developer Experience**:
- ✅ Simple, declarative API
- ✅ Type-safe with TypeScript
- ✅ Reusable across entire codebase
- ✅ Conditional execution support
- ✅ Automatic cleanup on unmount

**Performance**:
- ✅ No duplicate event listeners
- ✅ Efficient event handler management
- ✅ Minimal overhead
