# useClipboard Examples

Comprehensive migration guide and examples for the `useClipboard` composable.

## Table of Contents
- [Basic Usage](#basic-usage)
- [Migration Examples](#migration-examples)
- [Helper Functions](#helper-functions)
- [Advanced Features](#advanced-features)
- [UI Patterns](#ui-patterns)

---

## Basic Usage

### Example 1: Simple Copy Button

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const someText = ref('Hello, World!')

const { copy, copied } = useClipboard()

const handleCopy = () => {
  copy(someText.value)
}
</script>

<template>
  <div>
    <p>{{ someText }}</p>
    <button @click="handleCopy">
      <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
      {{ copied ? 'Copied!' : 'Copy' }}
    </button>
  </div>
</template>
```

---

## Migration Examples

### Migration 1: ChatMessages.vue - Copy Message

**BEFORE (Manual Implementation - 15 lines):**

```vue
<script setup lang="ts">
const copyMessage = async (message: ChatMessage) => {
  try {
    await navigator.clipboard.writeText(message.content)
    // Could show a toast notification here
  } catch (error) {
    // Fallback for older browsers
    const textArea = document.createElement('textarea')
    textArea.value = message.content
    document.body.appendChild(textArea)
    textArea.select()
    document.execCommand('copy')
    document.body.removeChild(textArea)
  }
}
</script>

<template>
  <button @click="copyMessage(message)">
    <i class="fas fa-copy"></i>
  </button>
</template>
```

**AFTER (Using useClipboard - 5 lines):**

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard({
  onSuccess: () => console.log('Message copied!'),
  onError: (err) => console.error('Failed to copy:', err)
})
</script>

<template>
  <button @click="copy(message.content)">
    <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
  </button>
</template>
```

**Improvements:**
- ✅ Reduced from ~15 lines to ~5 lines (67% reduction)
- ✅ Automatic fallback handling
- ✅ Visual feedback with `copied` state
- ✅ Built-in callbacks for success/error
- ✅ No manual DOM manipulation

---

### Migration 2: Terminal.vue - Copy Terminal Output

**BEFORE (Manual Implementation):**

```vue
<script setup lang="ts">
const copyTerminalOutput = async () => {
  const output = terminalLines.value
    .map(line => line.prefix + line.content)
    .join('\n')

  try {
    await navigator.clipboard.writeText(output)
    statusMessage.value = 'Terminal output copied!'
    setTimeout(() => {
      statusMessage.value = ''
    }, 2000)
  } catch (error) {
    statusMessage.value = 'Failed to copy output'
    console.error('Copy failed:', error)
  }
}
</script>

<template>
  <button @click="copyTerminalOutput" title="Copy Output">
    <i class="fas fa-copy"></i>
  </button>
  <div v-if="statusMessage">{{ statusMessage }}</div>
</template>
```

**AFTER (Using useClipboard):**

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied, error } = useClipboard({
  copiedDuration: 2000
})

const copyTerminalOutput = () => {
  const output = terminalLines.value
    .map(line => line.prefix + line.content)
    .join('\n')

  copy(output)
}
</script>

<template>
  <button @click="copyTerminalOutput" title="Copy Output">
    <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
  </button>
  <div v-if="copied" class="success">Output copied!</div>
  <div v-if="error" class="error">Failed to copy</div>
</template>
```

**Benefits:**
- Automatic state management (no manual statusMessage)
- Auto-reset after 2 seconds
- Error state automatically tracked
- Visual feedback built-in

---

### Migration 3: KnowledgeSearch.vue - Copy Document

**BEFORE:**

```vue
<script setup lang="ts">
const copyDocument = async () => {
  if (!selectedDocument.value) return

  try {
    await navigator.clipboard.writeText(selectedDocument.value.content)
    // Show success somehow
  } catch (error) {
    console.error('Failed to copy:', error)
  }
}
</script>

<template>
  <button @click="copyDocument">Copy Document</button>
</template>
```

**AFTER:**

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard()

const copyDocument = () => {
  if (!selectedDocument.value) return
  copy(selectedDocument.value.content)
}
</script>

<template>
  <button @click="copyDocument" :disabled="!selectedDocument">
    <i :class="copied ? 'fas fa-check-circle' : 'fas fa-copy'"></i>
    {{ copied ? 'Copied!' : 'Copy Document' }}
  </button>
</template>
```

---

### Migration 4: SecretsManager.vue - Copy Secret Value

**BEFORE:**

```vue
<script setup lang="ts">
const copySecretValue = async () => {
  if (!viewingSecret.value) return

  try {
    await navigator.clipboard.writeText(viewingSecret.value.value);
    // Success feedback needed
  } catch (error) {
    console.error('Copy failed:', error)
  }
}
</script>

<template>
  <button @click="copySecretValue">
    <i class="fas fa-copy"></i>
    Copy Value
  </button>
</template>
```

**AFTER (With Security Warning):**

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard({
  copiedDuration: 3000,
  onSuccess: () => {
    console.warn('Secret copied to clipboard - clear clipboard after use!')
  }
})

const copySecretValue = () => {
  if (!viewingSecret.value) return
  copy(viewingSecret.value.value)
}
</script>

<template>
  <button @click="copySecretValue" :disabled="!viewingSecret">
    <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
    {{ copied ? 'Copied! (3s)' : 'Copy Value' }}
  </button>
  <p v-if="copied" class="warning">Secret copied - clear clipboard after use!</p>
</template>
```

---

### Migration 5: ResearchBrowser.vue - Copy URL

**BEFORE:**

```vue
<script setup lang="ts">
const copyUrl = async () => {
  try {
    await navigator.clipboard.writeText(currentUrl.value)
  } catch (error) {
    console.error('Failed to copy URL:', error)
  }
}
</script>

<template>
  <button @click="copyUrl">Copy URL</button>
</template>
```

**AFTER (With Message Helper):**

```vue
<script setup lang="ts">
import { useClipboardWithMessage } from '@/composables/useClipboard'

const {
  copy,
  message,
  messageType
} = useClipboardWithMessage(
  'URL copied!',
  'Failed to copy URL'
)
</script>

<template>
  <button @click="copy(currentUrl)">
    <i class="fas fa-copy"></i>
    Copy URL
  </button>
  <div v-if="message" :class="messageType">
    {{ message }}
  </div>
</template>
```

---

## Helper Functions

### Helper 1: useClipboardWithMessage

For simple copy operations with automatic success/error messages:

```vue
<script setup lang="ts">
import { useClipboardWithMessage } from '@/composables/useClipboard'

const { copy, message, messageType } = useClipboardWithMessage()
</script>

<template>
  <div>
    <button @click="copy('Text to copy')">Copy</button>
    <div v-if="message" :class="[messageType, 'message']">
      {{ message }}
    </div>
  </div>
</template>

<style scoped>
.message.success {
  color: green;
}

.message.error {
  color: red;
}
</style>
```

### Helper 2: useClipboardElement

For copying DOM element content:

```vue
<script setup lang="ts">
import { useClipboardElement } from '@/composables/useClipboard'

const codeElement = ref<HTMLElement>()
const { copyElement, copied } = useClipboardElement()
</script>

<template>
  <div>
    <pre ref="codeElement">
const example = 'code'
console.log(example)
    </pre>
    <button @click="copyElement(codeElement)">
      <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
      {{ copied ? 'Copied!' : 'Copy Code' }}
    </button>
  </div>
</template>
```

---

## Advanced Features

### Example 1: Copy with Callbacks

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'
import { useToast } from '@/composables/useToast' // Assuming this exists

const toast = useToast()

const { copy } = useClipboard({
  onSuccess: (text) => {
    toast.success(`Copied ${text.length} characters`)
  },
  onError: (err) => {
    toast.error(`Failed to copy: ${err.message}`)
  }
})
</script>

<template>
  <button @click="copy(longText)">Copy Long Text</button>
</template>
```

### Example 2: Custom Copy Duration

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

// Show "Copied!" for 5 seconds
const { copy, copied } = useClipboard({
  copiedDuration: 5000
})

// Disable auto-reset
const { copy: copyPermanent, copied: copiedPermanent } = useClipboard({
  copiedDuration: 0
})
</script>

<template>
  <button @click="copy(text)">
    {{ copied ? 'Copied! (5s)' : 'Copy' }}
  </button>

  <button @click="copyPermanent(text)">
    {{ copiedPermanent ? '✓ Copied' : 'Copy (Permanent)' }}
  </button>
</template>
```

### Example 3: Manual Reset

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied, resetCopied } = useClipboard({
  copiedDuration: 0  // Disable auto-reset
})

const handleCopyAndClose = async () => {
  await copy(text)
  // Manually reset before closing
  resetCopied()
  closeModal()
}
</script>

<template>
  <button @click="handleCopyAndClose">
    Copy and Close
  </button>
</template>
```

### Example 4: Browser Support Detection

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, isSupported } = useClipboard()

const handleCopy = () => {
  if (!isSupported.value) {
    console.warn('Clipboard API not supported, using fallback')
  }
  copy(text)
}
</script>

<template>
  <div>
    <button @click="handleCopy">Copy</button>
    <p v-if="!isSupported" class="warning">
      Using legacy clipboard method
    </p>
  </div>
</template>
```

### Example 5: Legacy Mode (For Testing)

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

// Force legacy mode for testing fallback
const { copy, isSupported } = useClipboard({
  legacyMode: true
})

console.log(isSupported.value)  // false (forced legacy)
</script>

<template>
  <button @click="copy(text)">
    Copy (Legacy Mode)
  </button>
</template>
```

---

## UI Patterns

### Pattern 1: Copy Button with Icon

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard()
</script>

<template>
  <button @click="copy(text)" class="copy-btn">
    <i :class="copied ? 'fas fa-check text-green-500' : 'fas fa-copy'"></i>
    <span>{{ copied ? 'Copied!' : 'Copy' }}</span>
  </button>
</template>

<style scoped>
.copy-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #ccc;
  border-radius: 0.25rem;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  background: #f5f5f5;
}
</style>
```

### Pattern 2: Inline Copy Button

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard()
</script>

<template>
  <div class="code-block">
    <pre>{{ codeSnippet }}</pre>
    <button @click="copy(codeSnippet)" class="copy-btn-overlay">
      <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
    </button>
  </div>
</template>

<style scoped>
.code-block {
  position: relative;
  background: #f5f5f5;
  padding: 1rem;
  border-radius: 0.5rem;
}

.copy-btn-overlay {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  padding: 0.5rem;
  background: white;
  border: 1px solid #ddd;
  border-radius: 0.25rem;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.copy-btn-overlay:hover {
  opacity: 1;
}
</style>
```

### Pattern 3: Copy List Items

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const items = ref([
  { id: 1, text: 'Item 1' },
  { id: 2, text: 'Item 2' },
  { id: 3, text: 'Item 3' }
])

const { copy, copiedText } = useClipboard()
</script>

<template>
  <ul>
    <li v-for="item in items" :key="item.id" class="list-item">
      <span>{{ item.text }}</span>
      <button
        @click="copy(item.text)"
        class="copy-btn-small"
      >
        <i
          :class="copiedText === item.text
            ? 'fas fa-check text-green-500'
            : 'fas fa-copy'"
        ></i>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  border-bottom: 1px solid #eee;
}

.copy-btn-small {
  padding: 0.25rem 0.5rem;
  background: none;
  border: none;
  cursor: pointer;
  color: #666;
  transition: color 0.2s;
}

.copy-btn-small:hover {
  color: #333;
}
</style>
```

### Pattern 4: Copy with Tooltip

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'
import { ref, watch } from 'vue'

const { copy, copied } = useClipboard()

const tooltipText = ref('Click to copy')

watch(copied, (isCopied) => {
  tooltipText.value = isCopied ? 'Copied!' : 'Click to copy'
})
</script>

<template>
  <button
    @click="copy(text)"
    :title="tooltipText"
    class="copy-btn-tooltip"
  >
    <i class="fas fa-copy"></i>
  </button>
</template>
```

### Pattern 5: Copy with Animation

```vue
<script setup lang="ts">
import { useClipboard } from '@/composables/useClipboard'

const { copy, copied } = useClipboard()
</script>

<template>
  <button
    @click="copy(text)"
    class="copy-btn-animated"
    :class="{ copied }"
  >
    <transition name="fade" mode="out-in">
      <i v-if="copied" key="check" class="fas fa-check"></i>
      <i v-else key="copy" class="fas fa-copy"></i>
    </transition>
    <span>{{ copied ? 'Copied!' : 'Copy' }}</span>
  </button>
</template>

<style scoped>
.copy-btn-animated {
  transition: background-color 0.3s;
}

.copy-btn-animated.copied {
  background-color: #10b981;
  color: white;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
```

---

## Best Practices

### 1. Always Provide Visual Feedback

```vue
<!-- ❌ BAD: No feedback -->
<button @click="copy(text)">Copy</button>

<!-- ✅ GOOD: Clear feedback -->
<button @click="copy(text)">
  <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
  {{ copied ? 'Copied!' : 'Copy' }}
</button>
```

### 2. Handle Errors Gracefully

```vue
<script setup lang="ts">
const { copy, copied, error } = useClipboard({
  onError: (err) => {
    console.error('Copy failed:', err)
    // Show user-friendly error message
  }
})
</script>

<template>
  <button @click="copy(text)">Copy</button>
  <div v-if="error" class="error">
    Failed to copy. Please try again.
  </div>
</template>
```

### 3. Validate Before Copying

```vue
<script setup lang="ts">
const { copy } = useClipboard()

const handleCopy = () => {
  if (!text.value || text.value.trim() === '') {
    console.warn('Nothing to copy')
    return
  }
  copy(text.value)
}
</script>
```

### 4. Use Callbacks for Side Effects

```vue
<script setup lang="ts">
const { copy } = useClipboard({
  onSuccess: (text) => {
    // Log analytics
    analytics.track('text_copied', { length: text.length })

    // Show toast
    toast.success('Copied to clipboard')
  }
})
</script>
```

---

## Summary

### When to Use useClipboard

| Use Case | Pattern | Benefits |
|----------|---------|----------|
| Copy text | `copy(text)` | Automatic fallback, state tracking |
| Copy button | `copied` state | Built-in UI feedback |
| Copy DOM element | `useClipboardElement()` | Extract text from any element |
| Success messages | `useClipboardWithMessage()` | Automatic message handling |
| Error handling | `onError` callback | Centralized error handling |

### Migration Checklist

- [ ] Identify clipboard operations in component
- [ ] Replace manual `navigator.clipboard` calls with `useClipboard()`
- [ ] Remove manual fallback implementation
- [ ] Remove manual state management (`copied`, `error`)
- [ ] Update template to use `copied` state
- [ ] Test on modern and legacy browsers
- [ ] Verify error handling works
- [ ] Check visual feedback is clear
