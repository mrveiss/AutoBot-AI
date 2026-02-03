# Frontend Accessibility Improvements

**Analysis Date**: 2025-11-09
**Status**: 🔍 Audit Complete - Ready for Implementation
**Priority**: High (WCAG 2.1 Level AA Compliance)

---

## Executive Summary

Comprehensive accessibility audit of the AutoBot Vue frontend identified significant opportunities to improve usability for users with disabilities. Current implementation shows **mixed accessibility coverage**:

| Category | Current State | Components Affected | Priority | Impact |
|----------|---------------|---------------------|----------|--------|
| **ARIA Attributes** | 140 uses across 32 files | Mixed coverage | High | Screen reader support |
| **Role Attributes** | 10 uses across 4 files | Very low | High | Semantic structure |
| **Keyboard Navigation** | 38 handlers across 24 files | Moderate | High | Keyboard-only users |
| **Focus Management** | Minimal | Modal/dialog components | Critical | Keyboard/screen reader trap |
| **Tab Order** | 14 uses across 10 files | Low | Medium | Navigation flow |

**Key Discovery**: Some components (e.g., `KnowledgeStats.vue`) demonstrate **excellent accessibility practices**, but these patterns are not consistently applied across the codebase.

---

## 1. Critical Issues (Immediate Action Required)

### 1.1 BaseModal.vue - Missing Core Accessibility ⚠️ CRITICAL

**File**: `src/components/ui/BaseModal.vue` (258 lines)
**Impact**: Affects 6+ modal/dialog components across the application

**Current State**:
- ✅ Has `aria-label="Close dialog"` on close button
- ❌ Missing `role="dialog"` on dialog element
- ❌ Missing `aria-modal="true"` attribute
- ❌ Missing `aria-labelledby` pointing to title
- ❌ No focus trap implementation
- ❌ No ESC key handler
- ❌ No focus management (return focus on close)
- ❌ Body scroll not locked when modal open
- ❌ No screen reader announcements

**WCAG Violations**:
- 2.1.2 No Keyboard Trap (Level A) - Focus can escape modal
- 4.1.2 Name, Role, Value (Level A) - Missing dialog role
- 2.4.3 Focus Order (Level A) - No focus management

**Recommended Implementation**:

```vue
<template>
  <Teleport to="body">
    <Transition name="modal-fade" @after-enter="onAfterEnter" @after-leave="onAfterLeave">
      <div
        v-if="modelValue"
        class="dialog-overlay"
        @click="handleOverlayClick"
        @keydown.esc="handleClose"
      >
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          class="dialog"
          :class="[sizeClass, { 'dialog-scrollable': scrollable }]"
          @click.stop
          tabindex="-1"
        >
          <!-- Header -->
          <div class="dialog-header">
            <h3 :id="titleId">{{ title }}</h3>
            <button
              v-if="showClose"
              class="close-btn"
              @click="handleClose"
              aria-label="Close dialog"
              type="button"
            >
              <i class="fas fa-times" aria-hidden="true"></i>
            </button>
          </div>

          <!-- Content -->
          <div :id="descriptionId" class="dialog-content">
            <slot></slot>
          </div>

          <!-- Actions -->
          <div v-if="$slots.actions" class="dialog-actions">
            <slot name="actions"></slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'

// ... existing props ...

const dialogRef = ref<HTMLElement | null>(null)
const titleId = computed(() => `modal-title-${Math.random().toString(36).substr(2, 9)}`)
const descriptionId = computed(() => `modal-desc-${Math.random().toString(36).substr(2, 9)}`)
let previousActiveElement: HTMLElement | null = null

// Focus trap implementation
const onAfterEnter = async () => {
  // Store element that had focus before modal opened
  previousActiveElement = document.activeElement as HTMLElement

  await nextTick()

  // Focus the dialog itself or first focusable element
  if (dialogRef.value) {
    const firstFocusable = dialogRef.value.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )

    if (firstFocusable) {
      firstFocusable.focus()
    } else {
      dialogRef.value.focus()
    }
  }

  // Lock body scroll
  document.body.style.overflow = 'hidden'

  // Add focus trap
  document.addEventListener('focusin', trapFocus)
}

const onAfterLeave = () => {
  // Restore focus to element that opened modal
  if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
    previousActiveElement.focus()
  }

  // Unlock body scroll
  document.body.style.overflow = ''

  // Remove focus trap
  document.removeEventListener('focusin', trapFocus)
}

const trapFocus = (event: FocusEvent) => {
  if (!dialogRef.value) return

  const focusableElements = dialogRef.value.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )

  if (focusableElements.length === 0) return

  const firstElement = focusableElements[0]
  const lastElement = focusableElements[focusableElements.length - 1]

  // If focus leaves dialog, trap it
  if (!dialogRef.value.contains(event.target as Node)) {
    firstElement.focus()
    event.preventDefault()
  }
}

// Cleanup on unmount
onUnmounted(() => {
  document.removeEventListener('focusin', trapFocus)
  document.body.style.overflow = ''
})
</script>
```

**Estimated Impact**:
- **Files Affected**: 6+ modal/dialog components
- **Users Benefited**: Keyboard-only users, screen reader users
- **Lines Changed**: ~80 lines in BaseModal.vue
- **WCAG Compliance**: Fixes 3 Level A violations

---

### 1.2 Form Components - Missing Labels and Instructions

**Components Affected**:
- `ChatInput.vue` - Textarea missing explicit label
- `KnowledgeSearch.vue` - Search input missing label
- `FileUpload.vue` - Upload button missing instructions
- `BackendSettings.vue` - 37 form fields, some missing labels

**Current Issues**:
- Placeholder text used instead of labels (WCAG 3.3.2 violation)
- No error announcements for failed validation
- No field-level help text with `aria-describedby`
- Missing required field indicators (`aria-required="true"`)

**Example Fix** (ChatInput.vue):

```vue
<!-- Before -->
<textarea
  v-model="inputText"
  placeholder="Type your message..."
  class="message-input"
  @keydown="handleKeydown"
/>

<!-- After -->
<label for="chat-input" class="sr-only">Chat message</label>
<textarea
  id="chat-input"
  v-model="inputText"
  placeholder="Type your message..."
  class="message-input"
  aria-label="Type your message here. Press Shift+Enter for new line, Enter to send"
  aria-describedby="chat-input-help"
  :aria-invalid="hasError"
  @keydown="handleKeydown"
/>
<span id="chat-input-help" class="sr-only">
  Press Enter to send your message. Press Shift+Enter to create a new line.
</span>
```

**CSS for screen-reader-only content**:

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

---

## 2. High Priority Improvements

### 2.1 Keyboard Navigation Enhancements

**Components Needing Keyboard Support**:

| Component | Current State | Missing Features | Priority |
|-----------|---------------|------------------|----------|
| `FileListTable.vue` | Clickable rows | Arrow key navigation, Enter to open | High |
| `ChatSidebar.vue` | Mouse-only | Arrow keys, Home/End keys | High |
| `KnowledgeEntries.vue` | Pagination buttons only | Arrow keys through items | Medium |
| `TerminalOutput.vue` | Scrollable | Keyboard shortcuts (Ctrl+L clear) | Medium |
| `ResearchBrowser.vue` | Click/type only | Tab navigation, keyboard shortcuts | Medium |

**Recommended Pattern** (FileListTable.vue):

```vue
<template>
  <table class="file-list-table">
    <tbody>
      <tr
        v-for="(file, index) in files"
        :key="file.name"
        :ref="el => rowRefs[index] = el"
        :tabindex="index === focusedIndex ? 0 : -1"
        :aria-selected="selectedFiles.includes(file.name)"
        role="button"
        @click="selectFile(file)"
        @keydown="handleRowKeydown($event, index)"
        @focus="focusedIndex = index"
      >
        <!-- table cells -->
      </tr>
    </tbody>
  </table>
</template>

<script setup>
const focusedIndex = ref(0)
const rowRefs = ref([])

const handleRowKeydown = (event: KeyboardEvent, index: number) => {
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      if (index < files.length - 1) {
        focusedIndex.value = index + 1
        nextTick(() => rowRefs.value[index + 1]?.focus())
      }
      break
    case 'ArrowUp':
      event.preventDefault()
      if (index > 0) {
        focusedIndex.value = index - 1
        nextTick(() => rowRefs.value[index - 1]?.focus())
      }
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      selectFile(files[index])
      break
    case 'Home':
      event.preventDefault()
      focusedIndex.value = 0
      nextTick(() => rowRefs.value[0]?.focus())
      break
    case 'End':
      event.preventDefault()
      focusedIndex.value = files.length - 1
      nextTick(() => rowRefs.value[files.length - 1]?.focus())
      break
  }
}
</script>
```

---

### 2.2 ARIA Live Regions for Dynamic Content

**Components Needing Live Regions**:

| Component | Dynamic Content | Recommended ARIA | Priority |
|-----------|----------------|------------------|----------|
| `LogViewer.vue` | Streaming logs | `aria-live="polite"` | High |
| `TerminalOutput.vue` | Command output | `aria-live="polite"` | High |
| `ChatMessages.vue` | New messages | `aria-live="polite"` | High |
| `WorkflowProgressWidget.vue` | Progress updates | `aria-live="polite"` | Medium |
| `MonitoringDashboard.vue` | Metric updates | `aria-live="polite"` | Medium |

**Example Implementation** (ChatMessages.vue):

```vue
<template>
  <div class="chat-messages">
    <!-- Messages list -->
    <div
      ref="messagesContainer"
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      aria-label="Chat conversation"
    >
      <div
        v-for="message in messages"
        :key="message.id"
        :aria-label="`Message from ${message.sender} at ${formatTime(message.timestamp)}`"
      >
        <!-- message content -->
      </div>
    </div>

    <!-- Status region for screen readers -->
    <div role="status" aria-live="polite" class="sr-only">
      {{ srStatus }}
    </div>
  </div>
</template>

<script setup>
const srStatus = ref('')

watch(() => messages.value.length, (newLength, oldLength) => {
  if (newLength > oldLength) {
    const newMessage = messages.value[newLength - 1]
    srStatus.value = `New message from ${newMessage.sender}`
    // Clear after announcement
    setTimeout(() => {
      srStatus.value = ''
    }, 1000)
  }
})
</script>
```

---

### 2.3 Icon Accessibility

**Current Issue**: 140 icon instances, many missing `aria-hidden="true"` or `aria-label`

**Pattern to Follow** (from KnowledgeStats.vue):

```vue
<!-- Decorative icons (no meaning without context) -->
<i class="fas fa-lightbulb" aria-hidden="true"></i>

<!-- Icons with meaning (standalone) -->
<button aria-label="Refresh statistics">
  <i class="fas fa-sync" aria-hidden="true"></i>
</button>

<!-- Icons with visible text (redundant) -->
<button>
  <i class="fas fa-download" aria-hidden="true"></i>
  Download
</button>
```

**Audit Required**: Review all 140 icon usages and apply correct pattern

---

## 3. Medium Priority Improvements

### 3.1 Skip Navigation Links

**Current State**: No skip links present
**Impact**: Keyboard users must tab through entire header/nav on every page

**Recommended Implementation**:

```vue
<!-- In App.vue or main layout -->
<template>
  <div id="app">
    <!-- Skip links (visible on focus) -->
    <div class="skip-links">
      <a href="#main-content" class="skip-link">Skip to main content</a>
      <a href="#chat-input" class="skip-link">Skip to chat input</a>
      <a href="#navigation" class="skip-link">Skip to navigation</a>
    </div>

    <Header />

    <main id="main-content" tabindex="-1">
      <router-view />
    </main>
  </div>
</template>

<style>
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: #000;
  color: #fff;
  padding: 8px;
  text-decoration: none;
  z-index: 9999;
}

.skip-link:focus {
  top: 0;
}
</style>
```

---

### 3.2 Focus Indicators

**Current Issue**: Default focus outlines may be suppressed by CSS

**Audit Required**: Verify all interactive elements have visible focus indicators

**Recommended Global CSS**:

```css
/* Ensure all focusable elements have clear focus indicators */
*:focus {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

/* Custom focus styles for specific components */
button:focus,
a:focus,
input:focus,
select:focus,
textarea:focus {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.5);
}

/* Never remove focus indicators globally */
/* ❌ DO NOT DO THIS: *:focus { outline: none; } */
```

---

### 3.3 Color Contrast Compliance

**Audit Required**: Verify all text meets WCAG AA contrast ratios (4.5:1 for normal text, 3:1 for large text)

**Tools**:
- Browser DevTools Lighthouse Accessibility audit
- Chrome extension: "WAVE" or "axe DevTools"
- Manual check: WebAIM Contrast Checker

**Common Issues to Check**:
- Light gray text on white backgrounds
- Primary color buttons (ensure sufficient contrast)
- Dark mode contrast (check `@media (prefers-color-scheme: dark)` sections)
- Placeholder text contrast

---

## 4. Low Priority (Nice to Have)

### 4.1 Landmark Regions

**Current State**: Limited semantic HTML structure

**Recommended Structure**:

```vue
<template>
  <div id="app">
    <header role="banner">
      <nav role="navigation" aria-label="Main navigation">
        <!-- navigation items -->
      </nav>
    </header>

    <main role="main" id="main-content">
      <section aria-labelledby="chat-heading">
        <h2 id="chat-heading">Chat Interface</h2>
        <!-- chat content -->
      </section>

      <aside role="complementary" aria-label="Knowledge base">
        <!-- sidebar content -->
      </aside>
    </main>

    <footer role="contentinfo">
      <!-- footer content -->
    </footer>
  </div>
</template>
```

---

### 4.2 Reduced Motion Support

**Current State**: Animations present, no reduced motion support

**Recommended Implementation**:

```css
/* Respect user's motion preferences */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  /* Disable modal transitions */
  .modal-fade-enter-active,
  .modal-fade-leave-active {
    transition: none !important;
  }
}
```

---

### 4.3 Keyboard Shortcut Documentation

**Recommended**: Add visible keyboard shortcut hints

**Example** (ChatInput.vue):

```vue
<template>
  <div class="chat-input">
    <textarea
      v-model="inputText"
      aria-label="Chat message"
      aria-describedby="keyboard-shortcuts"
      @keydown="handleKeydown"
    />

    <div id="keyboard-shortcuts" class="keyboard-hints">
      <small>
        <kbd>Enter</kbd> to send •
        <kbd>Shift</kbd>+<kbd>Enter</kbd> for new line •
        <kbd>Ctrl</kbd>+<kbd>K</kbd> to clear
      </small>
    </div>
  </div>
</template>

<style>
kbd {
  background: #eee;
  border: 1px solid #ccc;
  border-radius: 3px;
  padding: 2px 4px;
  font-size: 0.85em;
  font-family: monospace;
}
</style>
```

---

## 5. Implementation Roadmap

### Phase 1: Critical Fixes (1-2 days) 🔴 HIGH PRIORITY

**Goal**: Fix WCAG Level A violations

1. ✅ **BaseModal.vue** - Add dialog role, focus trap, keyboard handling (~80 lines)
2. ✅ **Form Labels** - Add explicit labels to ChatInput, search inputs (~20 lines)
3. ✅ **Icon Audit** - Add aria-hidden to decorative icons (~50 files, 2-3 lines each)
4. ✅ **SR-only CSS** - Add screen-reader-only utility class globally (~10 lines)

**Estimated Impact**:
- **Lines Changed**: ~200 lines
- **Files Affected**: ~55 files (1 base component + 50+ icon fixes + 4 forms)
- **WCAG Compliance**: Level A achieved
- **Users Benefited**: All keyboard and screen reader users

---

### Phase 2: High Priority Features (3-5 days) 🟡 MEDIUM PRIORITY

**Goal**: Improve keyboard navigation and dynamic content announcements

1. ✅ **Keyboard Navigation** - Add arrow key support to FileListTable, ChatSidebar (~100 lines)
2. ✅ **ARIA Live Regions** - Add to ChatMessages, LogViewer, TerminalOutput (~50 lines)
3. ✅ **Skip Links** - Add to main layout (~20 lines)
4. ✅ **Focus Indicators** - Audit and fix focus styles globally (~30 lines CSS)

**Estimated Impact**:
- **Lines Changed**: ~200 lines
- **Files Affected**: ~10 files
- **WCAG Compliance**: Level AA progress (keyboard navigation)
- **Users Benefited**: Keyboard-only users, screen reader users

---

### Phase 3: Polish & Compliance (1 week) 🟢 LOW PRIORITY

**Goal**: Achieve WCAG 2.1 Level AA compliance

1. ⏳ **Color Contrast Audit** - Fix contrast issues across all components
2. ⏳ **Landmark Regions** - Add semantic HTML structure app-wide
3. ⏳ **Reduced Motion** - Add prefers-reduced-motion support
4. ⏳ **Keyboard Shortcuts** - Document and display keyboard shortcuts
5. ⏳ **Automated Testing** - Integrate axe-core or vue-axe for CI/CD

**Estimated Impact**:
- **Lines Changed**: ~300-400 lines
- **Files Affected**: 20+ files
- **WCAG Compliance**: Level AA achieved
- **Users Benefited**: All users, especially those with motion sensitivity

---

## 6. Testing & Validation

### Automated Testing Tools

**Recommended Integration**:

```bash
# Install axe-core for automated accessibility testing
npm install --save-dev @axe-core/vue axe-core

# Install Cypress axe plugin
npm install --save-dev cypress-axe
```

**Example Test** (Cypress + axe):

```javascript
describe('Accessibility Tests', () => {
  it('should not have any accessibility violations on home page', () => {
    cy.visit('/')
    cy.injectAxe()
    cy.checkA11y()
  })

  it('should not have violations in modal', () => {
    cy.visit('/')
    cy.get('[data-testid="open-modal"]').click()
    cy.checkA11y('.dialog')
  })
})
```

---

### Manual Testing Checklist

**Keyboard-Only Navigation**:
- [ ] Can navigate entire app using only keyboard (Tab, Shift+Tab, Enter, Space, Arrow keys)
- [ ] All interactive elements are reachable
- [ ] Focus is visible on all elements
- [ ] Focus never gets trapped (except in modals intentionally)
- [ ] Modals can be closed with ESC key

**Screen Reader Testing** (NVDA on Windows, VoiceOver on Mac):
- [ ] All images have alt text
- [ ] Form inputs have labels
- [ ] Buttons have meaningful names
- [ ] Dynamic content is announced
- [ ] Error messages are announced
- [ ] Success messages are announced
- [ ] Modals are announced as dialogs

**Browser Extensions**:
- [ ] WAVE - Identifies accessibility errors
- [ ] axe DevTools - Comprehensive WCAG audit
- [ ] Lighthouse (Chrome DevTools) - Accessibility score >90

---

## 7. Success Metrics

### Quantitative Goals

| Metric | Current | Target (Phase 1) | Target (Phase 2) | Target (Phase 3) |
|--------|---------|------------------|------------------|------------------|
| **Lighthouse Accessibility Score** | Unknown | 70+ | 85+ | 95+ |
| **WCAG Level A Violations** | Unknown | 0 | 0 | 0 |
| **WCAG Level AA Violations** | Unknown | <20 | <10 | 0 |
| **Keyboard-Accessible Components** | ~50% | 80% | 95% | 100% |
| **Components with ARIA** | 32/80 (40%) | 50/80 (62%) | 70/80 (87%) | 80/80 (100%) |

---

### Qualitative Goals

**Phase 1 Success Criteria**:
- ✅ All modals are keyboard-accessible and screen reader friendly
- ✅ All form inputs have explicit labels
- ✅ No decorative icons confuse screen readers

**Phase 2 Success Criteria**:
- ✅ Can navigate all lists/tables with arrow keys
- ✅ Dynamic content is announced to screen readers
- ✅ Skip links allow efficient navigation

**Phase 3 Success Criteria**:
- ✅ WCAG 2.1 Level AA compliance achieved
- ✅ Automated accessibility tests in CI/CD
- ✅ User testing with assistive technology users completed

---

## 8. Resources & Best Practices

### Documentation
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [MDN Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility)
- [Vue.js Accessibility Guide](https://vuejs.org/guide/best-practices/accessibility.html)
- [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)

### Tools
- [axe DevTools Browser Extension](https://www.deque.com/axe/devtools/)
- [WAVE Browser Extension](https://wave.webaim.org/extension/)
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [Accessibility Insights](https://accessibilityinsights.io/)

### Component Examples
- **KnowledgeStats.vue** - Excellent ARIA implementation reference
- **BaseModal.vue** (after fixes) - Focus trap and dialog implementation
- **ChatInput.vue** (after fixes) - Form accessibility patterns

---

## 9. Key Takeaways

**Critical Findings**:
1. **BaseModal.vue missing critical accessibility features** - Affects 6+ components
2. **Mixed accessibility implementation** - Some components excellent (KnowledgeStats), others minimal
3. **No consistent accessibility pattern** - Each component implements differently
4. **140 ARIA attributes already present** - Good foundation to build on

**Opportunities**:
1. **Fix BaseModal once, improve 6+ components** - High ROI
2. **Extract accessibility patterns to composables** - Reusable focus trap, keyboard navigation
3. **Establish accessibility guidelines** - Prevent future regressions

**Recommendations**:
1. **Start with Phase 1 critical fixes** (1-2 days, high impact)
2. **Create accessibility composables** (useF ocusTrap, useKeyboardNav)
3. **Add automated testing** (axe-core in CI/CD)
4. **Conduct user testing** with assistive technology users

---

**Next Steps**: Review this document with the team and prioritize Phase 1 implementation. Accessibility improvements will benefit all users and are required for compliance in many jurisdictions.
