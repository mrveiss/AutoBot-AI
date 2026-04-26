# Composable Wave 4 — useConfirmDialog

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `useConfirmDialog` composable and `ConfirmDialog.vue` base component, replacing the manual `showConfirmDelete = ref(false)` pattern repeated across components.

**Architecture:** Module-scoped singleton (same pattern as `useToast`). `useConfirmDialog()` exposes `confirm(options): Promise<boolean>`. Internally resolves via a Promise resolve callback stored in reactive state. `ConfirmDialog.vue` reads this state and calls the resolve callback on button click. Register `ConfirmDialog` in `App.vue` so it's available globally. Master tracker: #6006.

**Tech Stack:** Vue 3, TypeScript, `ref`, `provide`/`inject` (optional — module singleton is simpler), Vitest

---

## Task 1: Create GitHub issue

- [ ] **Step 1: Create issue**

```bash
gh issue create \
  --title "feat(composables): add useConfirmDialog — confirm(options): Promise<boolean>" \
  --label "enhancement,frontend,tech-debt" \
  --body "## Overview
Create a reusable useConfirmDialog composable and ConfirmDialog.vue component.
Replaces manual showConfirmDelete = ref(false) patterns across components.

## Interface
const { confirm } = useConfirmDialog()
const ok = await confirm({ title: 'Delete?', message: 'This cannot be undone.' })
if (!ok) return

## Files
- Create: src/composables/useConfirmDialog.ts
- Create: src/components/ui/ConfirmDialog.vue
- Modify: src/App.vue (register ConfirmDialog globally)

Master tracker: #6006"
```

---

## Task 2: Write failing tests for useConfirmDialog

**Files:**
- Create: `autobot-frontend/src/composables/__tests__/useConfirmDialog.test.ts`

- [ ] **Step 1: Create worktree**

```bash
ISSUE=<issue-number>
git worktree add .worktrees/issue-$ISSUE -b issue-$ISSUE origin/Dev_new_gui
cd .worktrees/issue-$ISSUE && git branch --unset-upstream
```

- [ ] **Step 2: Write the tests**

```typescript
// autobot-frontend/src/composables/__tests__/useConfirmDialog.test.ts
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, beforeEach } from 'vitest'
import { useConfirmDialog, _resetForTest } from '../useConfirmDialog'

describe('useConfirmDialog', () => {
  beforeEach(() => {
    _resetForTest()
  })

  it('isOpen starts false', () => {
    const { isOpen } = useConfirmDialog()
    expect(isOpen.value).toBe(false)
  })

  it('confirm() opens the dialog', async () => {
    const { confirm, isOpen, onConfirm } = useConfirmDialog()
    const promise = confirm({ title: 'Delete?', message: 'Cannot undo.' })
    expect(isOpen.value).toBe(true)
    onConfirm()
    const result = await promise
    expect(result).toBe(true)
  })

  it('confirm() resolves false when cancelled', async () => {
    const { confirm, isOpen, onCancel } = useConfirmDialog()
    const promise = confirm({ title: 'Delete?', message: 'Cannot undo.' })
    expect(isOpen.value).toBe(true)
    onCancel()
    const result = await promise
    expect(result).toBe(false)
  })

  it('dialog closes after confirm', async () => {
    const { confirm, isOpen, onConfirm } = useConfirmDialog()
    const promise = confirm({ title: 'X', message: 'Y' })
    onConfirm()
    await promise
    expect(isOpen.value).toBe(false)
  })

  it('dialog closes after cancel', async () => {
    const { confirm, isOpen, onCancel } = useConfirmDialog()
    const promise = confirm({ title: 'X', message: 'Y' })
    onCancel()
    await promise
    expect(isOpen.value).toBe(false)
  })

  it('title and message are set on confirm()', () => {
    const { confirm, title, message } = useConfirmDialog()
    confirm({ title: 'Really?', message: 'This is permanent.' })
    expect(title.value).toBe('Really?')
    expect(message.value).toBe('This is permanent.')
  })

  it('uses custom labels when provided', () => {
    const { confirm, confirmLabel, cancelLabel } = useConfirmDialog()
    confirm({ title: 'X', message: 'Y', confirmLabel: 'Yes, delete', cancelLabel: 'No' })
    expect(confirmLabel.value).toBe('Yes, delete')
    expect(cancelLabel.value).toBe('No')
  })

  it('uses default labels when not provided', () => {
    const { confirm, confirmLabel, cancelLabel } = useConfirmDialog()
    confirm({ title: 'X', message: 'Y' })
    expect(confirmLabel.value).toBe('Confirm')
    expect(cancelLabel.value).toBe('Cancel')
  })
})
```

- [ ] **Step 3: Run tests — expect failure**

```bash
cd autobot-frontend && npx vitest run src/composables/__tests__/useConfirmDialog.test.ts 2>&1 | tail -10
```
Expected: FAIL with "Cannot find module '../useConfirmDialog'".

---

## Task 3: Implement useConfirmDialog.ts

**Files:**
- Create: `autobot-frontend/src/composables/useConfirmDialog.ts`

- [ ] **Step 1: Write the composable**

```typescript
// autobot-frontend/src/composables/useConfirmDialog.ts
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import type { Ref } from 'vue'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
}

export interface UseConfirmDialogReturn {
  isOpen: Ref<boolean>
  title: Ref<string>
  message: Ref<string>
  confirmLabel: Ref<string>
  cancelLabel: Ref<string>
  confirm: (options: ConfirmOptions) => Promise<boolean>
  onConfirm: () => void
  onCancel: () => void
}

// Module-level singleton — same pattern as useToast
const isOpen = ref(false)
const title = ref('')
const message = ref('')
const confirmLabel = ref('Confirm')
const cancelLabel = ref('Cancel')
let _resolve: ((value: boolean) => void) | null = null

export function useConfirmDialog(): UseConfirmDialogReturn {
  const confirm = (options: ConfirmOptions): Promise<boolean> => {
    title.value = options.title
    message.value = options.message
    confirmLabel.value = options.confirmLabel ?? 'Confirm'
    cancelLabel.value = options.cancelLabel ?? 'Cancel'
    isOpen.value = true
    return new Promise<boolean>((resolve) => {
      _resolve = resolve
    })
  }

  const onConfirm = (): void => {
    isOpen.value = false
    _resolve?.(true)
    _resolve = null
  }

  const onCancel = (): void => {
    isOpen.value = false
    _resolve?.(false)
    _resolve = null
  }

  return { isOpen, title, message, confirmLabel, cancelLabel, confirm, onConfirm, onCancel }
}

// Test helper — resets singleton state between tests
export function _resetForTest(): void {
  isOpen.value = false
  title.value = ''
  message.value = ''
  confirmLabel.value = 'Confirm'
  cancelLabel.value = 'Cancel'
  _resolve = null
}

export default useConfirmDialog
```

- [ ] **Step 2: Run tests — expect pass**

```bash
cd autobot-frontend && npx vitest run src/composables/__tests__/useConfirmDialog.test.ts
```
Expected: all 8 tests PASS.

- [ ] **Step 3: Commit composable**

```bash
git add autobot-frontend/src/composables/useConfirmDialog.ts \
        autobot-frontend/src/composables/__tests__/useConfirmDialog.test.ts
git commit -m "feat(composables): add useConfirmDialog singleton — confirm(options): Promise<boolean> (#ISSUE)"
```

---

## Task 4: Create ConfirmDialog.vue

**Files:**
- Create: `autobot-frontend/src/components/ui/ConfirmDialog.vue`

- [ ] **Step 1: Write the component**

```vue
<!-- autobot-frontend/src/components/ui/ConfirmDialog.vue -->
<!-- Copyright (c) 2025 mrveiss -->
<template>
  <Teleport to="body">
    <div v-if="isOpen" class="confirm-dialog-overlay" role="dialog" aria-modal="true" :aria-labelledby="titleId">
      <div class="confirm-dialog">
        <h2 :id="titleId" class="confirm-dialog__title">{{ title }}</h2>
        <p class="confirm-dialog__message">{{ message }}</p>
        <div class="confirm-dialog__actions">
          <button
            class="confirm-dialog__btn confirm-dialog__btn--cancel"
            @click="onCancel"
          >{{ cancelLabel }}</button>
          <button
            class="confirm-dialog__btn confirm-dialog__btn--confirm"
            @click="onConfirm"
            autofocus
          >{{ confirmLabel }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const { isOpen, title, message, confirmLabel, cancelLabel, onConfirm, onCancel } = useConfirmDialog()
const titleId = 'confirm-dialog-title'
</script>

<style scoped>
.confirm-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.confirm-dialog {
  background: var(--color-bg-primary, #fff);
  border-radius: 8px;
  padding: 24px;
  min-width: 320px;
  max-width: 480px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
.confirm-dialog__title {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--color-text-primary, #111);
}
.confirm-dialog__message {
  font-size: 0.9375rem;
  color: var(--color-text-secondary, #555);
  margin: 0 0 24px;
}
.confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.confirm-dialog__btn {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 0.9375rem;
  cursor: pointer;
  border: none;
}
.confirm-dialog__btn--cancel {
  background: var(--color-bg-secondary, #f0f0f0);
  color: var(--color-text-primary, #111);
}
.confirm-dialog__btn--confirm {
  background: var(--color-error, #dc2626);
  color: #fff;
}
</style>
```

- [ ] **Step 2: Commit the component**

```bash
git add autobot-frontend/src/components/ui/ConfirmDialog.vue
git commit -m "feat(ui): add ConfirmDialog.vue base component driven by useConfirmDialog singleton (#ISSUE)"
```

---

## Task 5: Register ConfirmDialog in App.vue

**Files:**
- Modify: `autobot-frontend/src/App.vue`

- [ ] **Step 1: Add ConfirmDialog to App.vue template**

In `src/App.vue`, find where global UI components like `<ToastContainer />` are registered. Add after:

```html
<!-- Global confirm dialog — driven by useConfirmDialog() singleton -->
<ConfirmDialog />
```

- [ ] **Step 2: Import ConfirmDialog in App.vue script**

```typescript
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
```

Add to the `components` object if using Options API, or just import if using `<script setup>`.

- [ ] **Step 3: Type-check**

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep "ConfirmDialog\|App.vue"
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/src/App.vue
git commit -m "feat(app): register ConfirmDialog globally in App.vue (#ISSUE)"
```

---

## Task 6: Document usage pattern

- [ ] **Step 1: Verify the composable is in COMPOSABLE_HTTP_PATTERNS.md or equivalent docs**

```bash
ls autobot-frontend/src/docs/ 2>/dev/null || ls docs/developer/ | grep -i composable
```

- [ ] **Step 2: Add usage note to docs/developer/COMPOSABLE_HTTP_PATTERNS.md (if it exists)**

Add a section:
```markdown
## Confirm Dialogs

Use `useConfirmDialog` instead of `showConfirmDelete = ref(false)`:

```typescript
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const { confirm } = useConfirmDialog()

async function handleDelete(id: string) {
  if (!await confirm({ title: 'Delete item?', message: 'This cannot be undone.' })) return
  await deleteItem(id)
}
```

`ConfirmDialog.vue` is registered globally in `App.vue` — no local import needed in components.
```

- [ ] **Step 3: Commit docs**

```bash
git add docs/
git commit -m "docs(composables): document useConfirmDialog usage pattern (#ISSUE)"
```

---

## Final verification for Wave 4

- [ ] Composable file exists: `autobot-frontend/src/composables/useConfirmDialog.ts`
- [ ] Component exists: `autobot-frontend/src/components/ui/ConfirmDialog.vue`
- [ ] All 8 tests pass:

```bash
cd autobot-frontend && npx vitest run src/composables/__tests__/useConfirmDialog.test.ts
```

- [ ] `ConfirmDialog` is in `App.vue`:

```bash
grep "ConfirmDialog" autobot-frontend/src/App.vue
```
Expected: at least 2 lines (import + template usage).

- [ ] Type-check clean:

```bash
cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -c "error TS"
```
Expected: 0 new errors.
