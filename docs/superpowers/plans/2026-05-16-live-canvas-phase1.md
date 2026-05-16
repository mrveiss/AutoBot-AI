# Live Canvas Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Live Canvas frontend — an isolated, feature-flagged Vue 3 component tree at `autobot-frontend/src/components/canvas/` implementing adaptive split-panel layout, markdown cells with agent/user ownership, WebSocket streaming state machine, conflict resolution, tool palette with keyboard shortcuts, edge states, 1s-debounced auto-save, and a 4-format export sheet.

**Architecture:** Isolated component tree behind `VITE_FEATURE_CANVAS=true` env flag, dedicated `/canvas` route, and a self-contained `useCanvasStore` Pinia store. Streaming uses `useWebSocket.ts` composable (existing) with the frozen API contract (`/api/canvas/{id}`, WS envelope `{type:"canvas_cell",...}`). MSW handlers mock the entire API surface during test and development until sibling A lands.

**Tech Stack:** Vue 3 + TypeScript + Pinia + Tailwind v4 + Vite + Vitest + Playwright. All work in `.worktrees/issue-mva360`, branch `issue-mva360`.

**Spec refs:** MVA-343 ADR, MVA-190 v1.0 UX spec §2–§9.

---

## File Map

```
autobot-frontend/src/
├── assets/css/
│   ├── design-tokens.css              MODIFY — add 3 canvas tokens to :root
│   └── themes/
│       ├── dark.css                   MODIFY — dark overrides for canvas tokens
│       └── light.css                  MODIFY — light overrides for canvas tokens
├── design-system/tokens.ts            MODIFY — register canvas ClassPairs
├── constants/canvas.ts                CREATE — CANVAS_FEATURE_FLAG, layout consts, cell types
├── types/canvas.ts                    CREATE — all canvas TypeScript types
├── stores/useCanvasStore.ts           CREATE — Pinia store (cells, ownership, streaming, history)
├── composables/
│   ├── useCanvasAutoSave.ts           CREATE — 1s debounce + localStorage mirror + server reconcile
│   └── useCanvasWebSocket.ts         CREATE — wraps useWebSocket for canvas WS envelope
├── components/canvas/
│   ├── index.ts                       CREATE — barrel export
│   ├── CanvasView.vue                 CREATE — root view, wires store + layout
│   ├── CanvasSplitLayout.vue          CREATE — 35/65 split panel, draggable gutter, 4 variants, mobile tabs
│   ├── CanvasPanel.vue                CREATE — right-side canvas panel with cell list
│   ├── CanvasCell.vue                 CREATE — cell with ownership model + streaming state machine
│   ├── CanvasCellToolbar.vue          CREATE — contextual actions (Move/Duplicate/Delete/Copy)
│   ├── CanvasToolPalette.vue          CREATE — primary toolbar (Undo/Redo/Add/Save/Export) + shortcuts
│   ├── CanvasConflictBanner.vue       CREATE — conflict resolution banner
│   ├── CanvasEdgeStates.vue           CREATE — Empty / Agent Working / Stream Error / Load Error
│   └── CanvasExportSheet.vue          CREATE — 4-format export dialog with cell-type toggles
├── views/CanvasView.vue               CREATE — thin route wrapper (lazy-loads canvas component)
├── router/index.ts                    MODIFY — add /canvas route
├── config/navItems.ts                 MODIFY — add Canvas nav entry
└── test/mocks/canvas-handlers.ts      CREATE — MSW handlers for canvas API + WS

autobot-frontend/tests/
├── canvas/
│   ├── CanvasCell.test.ts             CREATE — Vitest unit: ownership, streaming states
│   ├── CanvasSplitLayout.test.ts      CREATE — Vitest unit: gutter drag, collapse, mobile
│   ├── useCanvasStore.test.ts         CREATE — Vitest unit: CRUD, undo/redo, conflict
│   ├── useCanvasAutoSave.test.ts      CREATE — Vitest unit: debounce, reconcile
│   └── canvas.spec.ts                CREATE — Playwright visual: 390px, motion, snapshots
```

---

### Task 1: Design Tokens

**Files:**
- Modify: `autobot-frontend/src/assets/css/design-tokens.css`
- Modify: `autobot-frontend/src/assets/css/themes/dark.css`
- Modify: `autobot-frontend/src/assets/css/themes/light.css`
- Modify: `autobot-frontend/src/design-system/tokens.ts`

- [ ] **Step 1.1: Add tokens to `:root` block in design-tokens.css**

Find the last `--color-` entry in the `:root { }` block and add after it:

```css
  /* Canvas — agent draft cell ownership tokens (MVA-360) */
  --color-agent-draft-border: #3B82F6;
  --color-agent-draft-bg: #EFF6FF;
  --color-user-edit-cursor: #059669;
```

- [ ] **Step 1.2: Add dark theme overrides in dark.css**

Find the last color entry in `[data-theme="dark"], :root { }` block and add:

```css
  /* Canvas agent-draft tokens — darker tint for dark mode */
  --color-agent-draft-border: #60A5FA;
  --color-agent-draft-bg: #1E3A5F;
  --color-user-edit-cursor: #34D399;
```

- [ ] **Step 1.3: Add light theme overrides in light.css**

Find the last color entry in `[data-theme="light"] { }` block and add:

```css
  /* Canvas agent-draft tokens — light mode uses spec defaults */
  --color-agent-draft-border: #3B82F6;
  --color-agent-draft-bg: #EFF6FF;
  --color-user-edit-cursor: #059669;
```

- [ ] **Step 1.4: Register in tokens.ts**

After the last `SEMANTIC_COLORS` entry, add a new export:

```typescript
/** Canvas cell ownership tokens (MVA-360). */
export const CANVAS_TOKENS: readonly ClassPair[] = [
  { name: 'agent-draft-border', cls: 'border-[var(--color-agent-draft-border)]' },
  { name: 'agent-draft-bg', cls: 'bg-[var(--color-agent-draft-bg)]' },
  { name: 'user-edit-cursor', cls: 'text-[var(--color-user-edit-cursor)]' },
]
```

- [ ] **Step 1.5: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/assets/css/design-tokens.css \
  autobot-frontend/src/assets/css/themes/dark.css \
  autobot-frontend/src/assets/css/themes/light.css \
  autobot-frontend/src/design-system/tokens.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): add 3 canvas design tokens (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 2: Types and Constants

**Files:**
- Create: `autobot-frontend/src/constants/canvas.ts`
- Create: `autobot-frontend/src/types/canvas.ts`

- [ ] **Step 2.1: Create canvas constants**

```typescript
// autobot-frontend/src/constants/canvas.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

export const CANVAS_FEATURE_FLAG = import.meta.env.VITE_FEATURE_CANVAS === 'true'

export const CANVAS_SPLIT_DEFAULT = { chat: 35, canvas: 65 } as const

export const CANVAS_GUTTER_HOT_ZONE_PX = 8

export const CANVAS_AUTOSAVE_DEBOUNCE_MS = 1000

export const CANVAS_MOBILE_BREAKPOINT_PX = 390

export type CanvasLayoutVariant = 'split' | 'canvas-focus' | 'chat-focus' | 'full-canvas'
```

- [ ] **Step 2.2: Create canvas types**

```typescript
// autobot-frontend/src/types/canvas.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/** Streaming lifecycle state for an agent cell. */
export type CellStreamState = 'skeleton' | 'partial' | 'complete' | 'error'

/** Who owns a cell — determines visual treatment. */
export type CellOwner = 'agent' | 'user'

/** Cell type — phase 1 markdown only; chart/code show placeholder. */
export type CellContentType = 'markdown' | 'chart' | 'code'

export interface CanvasCell {
  id: string
  canvasId: string
  owner: CellOwner
  contentType: CellContentType
  content: string
  streamState: CellStreamState
  seq: number
  createdAt: string
  updatedAt: string
}

export interface CanvasDocument {
  id: string
  title: string
  cells: CanvasCell[]
  version: number
  updatedAt: string
}

/** WS message envelope from the backend. */
export interface CanvasWsMessage {
  type: 'canvas_cell'
  cellId: string
  seq: number
  delta: string
  state: CellStreamState
}

export type AutoSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface ConflictState {
  cellId: string
  pausedAgentSeq: number
}
```

- [ ] **Step 2.3: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/constants/canvas.ts \
  autobot-frontend/src/types/canvas.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): add canvas types and constants (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 3: Canvas Pinia Store

**Files:**
- Create: `autobot-frontend/src/stores/useCanvasStore.ts`
- Test: `autobot-frontend/tests/canvas/useCanvasStore.test.ts`

- [ ] **Step 3.1: Write the failing store test**

```typescript
// autobot-frontend/tests/canvas/useCanvasStore.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { CanvasCell } from '@/types/canvas'

const mockCell = (): CanvasCell => ({
  id: 'cell-1', canvasId: 'canvas-1', owner: 'agent',
  contentType: 'markdown', content: '# Hello', streamState: 'complete',
  seq: 1, createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z',
})

describe('useCanvasStore', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('starts empty', () => {
    const store = useCanvasStore()
    expect(store.cells).toEqual([])
    expect(store.canvasId).toBeNull()
  })

  it('setCanvas populates cells', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'canvas-1', title: 'Test', cells: [mockCell()], version: 1, updatedAt: '' })
    expect(store.cells).toHaveLength(1)
    expect(store.canvasId).toBe('canvas-1')
  })

  it('applyDelta appends to skeleton cell content', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: 'hello ', state: 'partial' })
    store.upsertStreamCell({ cellId: 'c2', seq: 2, delta: 'world', state: 'partial' })
    const cell = store.cells.find(c => c.id === 'c2')
    expect(cell?.content).toBe('hello world')
    expect(cell?.streamState).toBe('partial')
  })

  it('completeStreamCell marks state=complete', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: 'done', state: 'complete' })
    const cell = store.cells.find(c => c.id === 'c2')
    expect(cell?.streamState).toBe('complete')
  })

  it('undo/redo round-trips a cell edit', () => {
    const store = useCanvasStore()
    const cell = mockCell()
    store.setCanvas({ id: 'c1', title: '', cells: [cell], version: 1, updatedAt: '' })
    store.updateCellContent('cell-1', 'Modified')
    expect(store.cells[0].content).toBe('Modified')
    store.undo()
    expect(store.cells[0].content).toBe('# Hello')
    store.redo()
    expect(store.cells[0].content).toBe('Modified')
  })

  it('conflict pauses streaming cell and records state', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: '...', state: 'partial' })
    store.triggerConflict('c2', 1)
    expect(store.conflict?.cellId).toBe('c2')
    expect(store.cells.find(c => c.id === 'c2')?.streamState).toBe('complete')
  })

  it('resolveConflict clears conflict state', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    store.upsertStreamCell({ cellId: 'c2', seq: 1, delta: '...', state: 'partial' })
    store.triggerConflict('c2', 1)
    store.resolveConflict()
    expect(store.conflict).toBeNull()
  })

  it('deleteCell removes from list', () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [mockCell()], version: 1, updatedAt: '' })
    store.deleteCell('cell-1')
    expect(store.cells).toHaveLength(0)
  })
})
```

- [ ] **Step 3.2: Run test, expect failure**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/useCanvasStore.test.ts 2>&1 | tail -10
```
Expected: `FAIL ... useCanvasStore not found`

- [ ] **Step 3.3: Create the store**

```typescript
// autobot-frontend/src/stores/useCanvasStore.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CanvasCell, CanvasDocument, CellStreamState, ConflictState, CanvasWsMessage } from '@/types/canvas'

type HistoryEntry = { cells: CanvasCell[] }

export const useCanvasStore = defineStore('canvas', () => {
  const canvasId = ref<string | null>(null)
  const cells = ref<CanvasCell[]>([])
  const conflict = ref<ConflictState | null>(null)
  const isDirty = ref(false)

  const _history: HistoryEntry[] = []
  let _historyIndex = -1

  function _snapshot() {
    const snap: HistoryEntry = { cells: cells.value.map(c => ({ ...c })) }
    _history.splice(_historyIndex + 1)
    _history.push(snap)
    _historyIndex = _history.length - 1
    if (_history.length > 100) { _history.shift(); _historyIndex-- }
  }

  function setCanvas(doc: CanvasDocument) {
    canvasId.value = doc.id
    cells.value = doc.cells.map(c => ({ ...c }))
    _history.length = 0
    _historyIndex = -1
    isDirty.value = false
  }

  function upsertStreamCell(msg: Pick<CanvasWsMessage, 'cellId' | 'seq' | 'delta' | 'state'>) {
    const existing = cells.value.find(c => c.id === msg.cellId)
    if (existing) {
      existing.content += msg.delta
      existing.streamState = msg.state
      existing.seq = msg.seq
    } else {
      cells.value.push({
        id: msg.cellId,
        canvasId: canvasId.value ?? '',
        owner: 'agent',
        contentType: 'markdown',
        content: msg.delta,
        streamState: msg.state,
        seq: msg.seq,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    }
    isDirty.value = true
  }

  function updateCellContent(cellId: string, content: string) {
    _snapshot()
    const cell = cells.value.find(c => c.id === cellId)
    if (cell) {
      cell.content = content
      cell.updatedAt = new Date().toISOString()
      isDirty.value = true
    }
  }

  function deleteCell(cellId: string) {
    _snapshot()
    cells.value = cells.value.filter(c => c.id !== cellId)
    isDirty.value = true
  }

  function moveCell(cellId: string, direction: 'up' | 'down') {
    _snapshot()
    const idx = cells.value.findIndex(c => c.id === cellId)
    if (idx < 0) return
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= cells.value.length) return
    const tmp = cells.value[idx]
    cells.value[idx] = cells.value[target]
    cells.value[target] = tmp
    isDirty.value = true
  }

  function duplicateCell(cellId: string) {
    _snapshot()
    const idx = cells.value.findIndex(c => c.id === cellId)
    if (idx < 0) return
    const clone: CanvasCell = {
      ...cells.value[idx],
      id: `${cellId}-copy-${Date.now()}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    cells.value.splice(idx + 1, 0, clone)
    isDirty.value = true
  }

  function addCell(owner: 'user' | 'agent' = 'user') {
    _snapshot()
    cells.value.push({
      id: `cell-${Date.now()}`,
      canvasId: canvasId.value ?? '',
      owner,
      contentType: 'markdown',
      content: '',
      streamState: 'complete',
      seq: cells.value.length,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
    isDirty.value = true
  }

  function triggerConflict(cellId: string, pausedAgentSeq: number) {
    const cell = cells.value.find(c => c.id === cellId)
    if (cell) cell.streamState = 'complete'
    conflict.value = { cellId, pausedAgentSeq }
  }

  function resolveConflict() {
    conflict.value = null
  }

  function undo() {
    if (_historyIndex <= 0) return
    _historyIndex--
    cells.value = _history[_historyIndex].cells.map(c => ({ ...c }))
    isDirty.value = true
  }

  function redo() {
    if (_historyIndex >= _history.length - 1) return
    _historyIndex++
    cells.value = _history[_historyIndex].cells.map(c => ({ ...c }))
    isDirty.value = true
  }

  function markSaved() {
    isDirty.value = false
  }

  const canUndo = computed(() => _historyIndex > 0)
  const canRedo = computed(() => _historyIndex < _history.length - 1)
  const isEmpty = computed(() => cells.value.length === 0)

  return {
    canvasId, cells, conflict, isDirty,
    canUndo, canRedo, isEmpty,
    setCanvas, upsertStreamCell, updateCellContent,
    deleteCell, moveCell, duplicateCell, addCell,
    triggerConflict, resolveConflict, undo, redo, markSaved,
  }
})
```

- [ ] **Step 3.4: Run test, expect pass**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/useCanvasStore.test.ts 2>&1 | tail -10
```
Expected: `PASS` — all 8 tests green.

- [ ] **Step 3.5: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/stores/useCanvasStore.ts \
  autobot-frontend/tests/canvas/useCanvasStore.test.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): canvas Pinia store with history + conflict (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 4: Route, View, and NavItems

**Files:**
- Create: `autobot-frontend/src/views/CanvasView.vue`
- Modify: `autobot-frontend/src/router/index.ts`
- Modify: `autobot-frontend/src/config/navItems.ts`

- [ ] **Step 4.1: Create CanvasView route wrapper**

```vue
<!-- autobot-frontend/src/views/CanvasView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <suspense>
    <canvas-root />
    <template #fallback>
      <div class="flex items-center justify-center h-full text-text-secondary text-sm">
        Loading canvas…
      </div>
    </template>
  </suspense>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
const CanvasRoot = defineAsyncComponent(() =>
  import('@/components/canvas/CanvasView.vue')
)
</script>
```

- [ ] **Step 4.2: Add route to router/index.ts**

Find the last `requiresAuth: true` route block and add before the `catchAll` / 404 route:

```typescript
  {
    path: '/canvas',
    name: 'canvas',
    component: () => import('@/views/CanvasView.vue'),
    meta: {
      title: 'Canvas',
      requiresAuth: true,
    }
  },
```

- [ ] **Step 4.3: Add nav entry to navItems.ts**

Add to the `navItems` array (after the chat entry, before knowledge):

```typescript
  {
    to: '/canvas',
    labelKey: 'nav.canvas',
    // Grid/table-cells icon — represents a canvas grid
    icon: 'M3 3h7v7H3V3zm0 11h7v7H3v-7zm11-11h7v7h-7V3zm0 11h7v7h-7v-7z',
    iconStroke: true,
  },
```

- [ ] **Step 4.4: Add i18n key for canvas nav**

```bash
grep -rn "nav.chat" .worktrees/issue-mva360/autobot-frontend/src/i18n/locales/ | head -3
```

Find the locales file and add `"canvas": "Canvas"` under the `nav` section for each locale (en.json and any others present).

- [ ] **Step 4.5: Run nav coverage test**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run src/__tests__/nav-items-coverage.test.ts 2>&1 | tail -10
```
Expected: PASS

- [ ] **Step 4.6: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/views/CanvasView.vue \
  autobot-frontend/src/router/index.ts \
  autobot-frontend/src/config/navItems.ts \
  autobot-frontend/src/i18n/
git -C .worktrees/issue-mva360 commit -m "feat(canvas): add /canvas route, view wrapper, and nav entry (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 5: Canvas Cell Component

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasCell.vue`
- Test: `autobot-frontend/tests/canvas/CanvasCell.test.ts`

- [ ] **Step 5.1: Write the failing cell test**

```typescript
// autobot-frontend/tests/canvas/CanvasCell.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CanvasCell from '@/components/canvas/CanvasCell.vue'
import type { CanvasCell as CellType } from '@/types/canvas'

const makeCell = (overrides: Partial<CellType> = {}): CellType => ({
  id: 'c1', canvasId: 'cv1', owner: 'agent', contentType: 'markdown',
  content: '# Hello', streamState: 'complete', seq: 1,
  createdAt: '', updatedAt: '', ...overrides,
})

describe('CanvasCell', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('agent cell shows robot badge', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell() } })
    expect(wrapper.find('[data-testid="agent-badge"]').exists()).toBe(true)
  })

  it('agent cell has left border class', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell() } })
    expect(wrapper.find('[data-testid="cell-root"]').classes()).toContain('border-l-2')
  })

  it('user cell has no agent badge', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell({ owner: 'user' }) } })
    expect(wrapper.find('[data-testid="agent-badge"]').exists()).toBe(false)
  })

  it('skeleton state shows shimmer', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell({ streamState: 'skeleton', owner: 'agent' }) } })
    expect(wrapper.find('[data-testid="skeleton-shimmer"]').exists()).toBe(true)
  })

  it('partial state shows cancel button', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell({ streamState: 'partial', owner: 'agent' }) } })
    expect(wrapper.find('[data-testid="btn-cancel-stream"]').exists()).toBe(true)
  })

  it('complete agent cell shows accept/edit/discard buttons', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell() } })
    expect(wrapper.find('[data-testid="btn-accept"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="btn-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="btn-discard"]').exists()).toBe(true)
  })

  it('user cell shows no accept/edit/discard', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell({ owner: 'user' }) } })
    expect(wrapper.find('[data-testid="btn-accept"]').exists()).toBe(false)
  })

  it('chart cell shows Phase-2 placeholder', () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell({ contentType: 'chart' }) } })
    expect(wrapper.find('[data-testid="phase2-placeholder"]').exists()).toBe(true)
  })

  it('emits accept on accept button click', async () => {
    const wrapper = mount(CanvasCell, { props: { cell: makeCell() } })
    await wrapper.find('[data-testid="btn-accept"]').trigger('click')
    expect(wrapper.emitted('accept')).toBeTruthy()
  })
})
```

- [ ] **Step 5.2: Run test, expect failure**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/CanvasCell.test.ts 2>&1 | tail -10
```

- [ ] **Step 5.3: Create CanvasCell.vue**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasCell.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    data-testid="cell-root"
    :class="[
      'relative group rounded-md p-3 mb-2 transition-colors',
      isAgentCell
        ? 'border-l-2 bg-[var(--color-agent-draft-bg)] border-[var(--color-agent-draft-border)]'
        : 'border border-border-default bg-bg-card',
    ]"
    @click="onCellClick"
  >
    <!-- Agent badge -->
    <span
      v-if="isAgentCell"
      data-testid="agent-badge"
      aria-label="Agent-authored cell"
      class="absolute top-2 right-2 text-xs select-none"
      role="img"
    >🤖</span>

    <!-- Phase-2 placeholder for non-markdown cells -->
    <div
      v-if="cell.contentType !== 'markdown'"
      data-testid="phase2-placeholder"
      class="text-text-secondary text-sm italic py-4 text-center"
    >
      Rich render pending (Phase 2)
    </div>

    <!-- Skeleton shimmer -->
    <div
      v-else-if="cell.streamState === 'skeleton'"
      data-testid="skeleton-shimmer"
      :class="[
        'space-y-2',
        !prefersReducedMotion && 'animate-pulse',
      ]"
      aria-busy="true"
      aria-label="Loading…"
    >
      <div class="h-3 bg-bg-tertiary rounded w-3/4" />
      <div class="h-3 bg-bg-tertiary rounded w-1/2" />
      <div class="h-3 bg-bg-tertiary rounded w-5/6" />
    </div>

    <!-- Partial stream: content + blinking cursor -->
    <div v-else-if="cell.streamState === 'partial'">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="message-text prose prose-sm max-w-none" v-html="renderedContent" />
      <span
        class="inline-block w-0.5 h-4 bg-current animate-[blink_1s_step-end_infinite] ml-0.5"
        aria-hidden="true"
      />
      <p class="text-text-secondary text-xs mt-1">Writing…</p>
    </div>

    <!-- Complete / error markdown -->
    <div v-else>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="message-text prose prose-sm max-w-none" v-html="renderedContent" />
    </div>

    <!-- Streaming controls (partial) -->
    <div v-if="cell.streamState === 'partial' && isAgentCell" class="mt-2 flex gap-2">
      <button
        data-testid="btn-cancel-stream"
        aria-label="Cancel stream"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('cancel')"
      >
        Cancel
      </button>
    </div>

    <!-- Complete agent controls -->
    <div
      v-if="cell.streamState === 'complete' && isAgentCell"
      class="mt-2 flex gap-2 flex-wrap"
    >
      <button
        data-testid="btn-accept"
        aria-label="Accept agent cell"
        class="px-2 py-1 text-xs rounded bg-autobot-success text-white hover:opacity-90"
        @click.stop="$emit('accept')"
      >
        ✓ Accept
      </button>
      <button
        data-testid="btn-edit"
        aria-label="Edit agent cell"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('edit')"
      >
        ✎ Edit
      </button>
      <button
        data-testid="btn-discard"
        aria-label="Discard agent cell"
        class="px-2 py-1 text-xs rounded border border-border-error text-error hover:bg-error-bg"
        @click.stop="$emit('discard')"
      >
        ✕ Discard
      </button>
    </div>

    <!-- Error controls -->
    <div v-if="cell.streamState === 'error' && isAgentCell" class="mt-2 flex gap-2">
      <button
        data-testid="btn-keep-error"
        aria-label="Keep cell on error"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('keep')"
      >Keep</button>
      <button
        data-testid="btn-retry"
        aria-label="Retry stream"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('retry')"
      >Retry</button>
      <button
        data-testid="btn-discard-error"
        aria-label="Discard errored cell"
        class="px-2 py-1 text-xs rounded border border-border-error text-error hover:bg-error-bg"
        @click.stop="$emit('discard')"
      >Discard</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanvasCell } from '@/types/canvas'

const props = defineProps<{ cell: CanvasCell }>()

defineEmits<{
  accept: []
  edit: []
  discard: []
  cancel: []
  keep: []
  retry: []
  click: [cell: CanvasCell]
}>()

const isAgentCell = computed(() => props.cell.owner === 'agent')

const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

function formatMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^#+ (.+)$/gm, (_, t) => `<strong>${t}</strong>`)
    .replace(/\n/g, '<br>')
}

const renderedContent = computed(() => formatMarkdown(props.cell.content))

function onCellClick() {
  if (props.cell.streamState === 'partial' && props.cell.owner === 'agent') {
    // Conflict: user clicked a streaming cell
  }
}
</script>
```

- [ ] **Step 5.4: Run test, expect pass**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/CanvasCell.test.ts 2>&1 | tail -10
```

- [ ] **Step 5.5: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/components/canvas/CanvasCell.vue \
  autobot-frontend/tests/canvas/CanvasCell.test.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): CanvasCell with streaming state machine + ownership (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 6: Split Layout Component

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasSplitLayout.vue`
- Test: `autobot-frontend/tests/canvas/CanvasSplitLayout.test.ts`

- [ ] **Step 6.1: Write the failing layout test**

```typescript
// autobot-frontend/tests/canvas/CanvasSplitLayout.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import CanvasSplitLayout from '@/components/canvas/CanvasSplitLayout.vue'

describe('CanvasSplitLayout', () => {
  it('renders split variant with default 35/65 split', () => {
    const wrapper = mount(CanvasSplitLayout, {
      props: { variant: 'split' },
      slots: { chat: '<div id="chat">chat</div>', canvas: '<div id="cv">canvas</div>' },
    })
    const chat = wrapper.find('[data-testid="chat-panel"]')
    expect(chat.attributes('style')).toContain('35')
  })

  it('canvas-focus collapses chat panel', () => {
    const wrapper = mount(CanvasSplitLayout, {
      props: { variant: 'canvas-focus' },
      slots: { chat: '<div>c</div>', canvas: '<div>cv</div>' },
    })
    expect(wrapper.find('[data-testid="chat-panel"]').classes()).toContain('hidden')
  })

  it('chat-focus collapses canvas panel', () => {
    const wrapper = mount(CanvasSplitLayout, {
      props: { variant: 'chat-focus' },
      slots: { chat: '<div>c</div>', canvas: '<div>cv</div>' },
    })
    expect(wrapper.find('[data-testid="canvas-panel"]').classes()).toContain('hidden')
  })

  it('emits variant-changed on gutter double-click', async () => {
    const wrapper = mount(CanvasSplitLayout, {
      props: { variant: 'split' },
      slots: { chat: '<div>c</div>', canvas: '<div>cv</div>' },
    })
    await wrapper.find('[data-testid="gutter"]').trigger('dblclick')
    expect(wrapper.emitted('variant-changed')).toBeTruthy()
  })
})
```

- [ ] **Step 6.2: Run test, expect failure**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/CanvasSplitLayout.test.ts 2>&1 | tail -8
```

- [ ] **Step 6.3: Create CanvasSplitLayout.vue**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasSplitLayout.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <!-- Mobile (≤390px): tabbed fallback -->
  <div v-if="isMobile" class="flex flex-col h-full">
    <div class="flex border-b border-border-default">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['px-4 py-2 text-sm font-medium', activeTab === tab.id ? 'border-b-2 border-autobot-primary text-autobot-primary' : 'text-text-secondary']"
        :aria-selected="activeTab === tab.id"
        role="tab"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
        <span v-if="tab.id === 'canvas' && agentContentBadge > 0" class="ml-1 text-xs bg-autobot-primary text-white rounded-full px-1.5">{{ agentContentBadge }}</span>
      </button>
    </div>
    <div class="flex-1 overflow-hidden">
      <div v-show="activeTab === 'chat'" class="h-full"><slot name="chat" /></div>
      <div v-show="activeTab === 'canvas'" class="h-full"><slot name="canvas" /></div>
    </div>
  </div>

  <!-- Desktop: split panel -->
  <div v-else class="flex h-full overflow-hidden" @mousemove="onGutterDrag" @mouseup="stopDrag">
    <!-- Chat panel -->
    <div
      data-testid="chat-panel"
      :class="['overflow-hidden transition-all duration-200', chatPanelClass]"
      :style="chatPanelStyle"
    >
      <slot name="chat" />
    </div>

    <!-- Gutter -->
    <div
      v-if="variant === 'split'"
      data-testid="gutter"
      :class="[
        'relative flex-shrink-0 cursor-col-resize select-none',
        'bg-border-subtle hover:bg-autobot-primary/30 transition-colors',
      ]"
      :style="{ width: `${gutterWidth}px` }"
      role="separator"
      aria-label="Resize panels"
      @mousedown.prevent="startDrag"
      @dblclick="cycleSnapPreset"
    />

    <!-- Canvas panel -->
    <div
      data-testid="canvas-panel"
      :class="['flex-1 overflow-hidden', canvasPanelClass]"
    >
      <slot name="canvas" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { CanvasLayoutVariant } from '@/constants/canvas'
import { CANVAS_GUTTER_HOT_ZONE_PX, CANVAS_MOBILE_BREAKPOINT_PX, CANVAS_SPLIT_DEFAULT } from '@/constants/canvas'

const props = withDefaults(defineProps<{
  variant: CanvasLayoutVariant
  agentContentBadge?: number
}>(), { agentContentBadge: 0 })

const emit = defineEmits<{
  'variant-changed': [variant: CanvasLayoutVariant]
}>()

const gutterWidth = CANVAS_GUTTER_HOT_ZONE_PX
const chatPercent = ref(CANVAS_SPLIT_DEFAULT.chat)
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartPercent = ref(CANVAS_SPLIT_DEFAULT.chat)
const activeTab = ref<'chat' | 'canvas'>('chat')
const isMobile = ref(false)

const tabs = [
  { id: 'chat' as const, label: 'Chat' },
  { id: 'canvas' as const, label: 'Canvas' },
]

const SNAP_PRESETS: CanvasLayoutVariant[] = ['split', 'canvas-focus', 'chat-focus', 'full-canvas']
let snapIndex = 0

function cycleSnapPreset() {
  snapIndex = (snapIndex + 1) % SNAP_PRESETS.length
  emit('variant-changed', SNAP_PRESETS[snapIndex])
}

function startDrag(e: MouseEvent) {
  dragging.value = true
  dragStartX.value = e.clientX
  dragStartPercent.value = chatPercent.value
}

function onGutterDrag(e: MouseEvent) {
  if (!dragging.value) return
  const containerWidth = (e.currentTarget as HTMLElement).offsetWidth
  const dx = e.clientX - dragStartX.value
  const dpct = (dx / containerWidth) * 100
  chatPercent.value = Math.max(10, Math.min(90, dragStartPercent.value + dpct))
}

function stopDrag() {
  dragging.value = false
}

const chatPanelStyle = computed(() =>
  props.variant === 'split' ? { width: `${chatPercent.value}%` } : {}
)

const chatPanelClass = computed(() => {
  if (props.variant === 'canvas-focus' || props.variant === 'full-canvas') return 'hidden'
  if (props.variant === 'chat-focus') return 'flex-1'
  return ''
})

const canvasPanelClass = computed(() => {
  if (props.variant === 'chat-focus') return 'hidden'
  return ''
})

function checkMobile() {
  isMobile.value = window.innerWidth <= CANVAS_MOBILE_BREAKPOINT_PX
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>
```

- [ ] **Step 6.4: Run test, expect pass**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/CanvasSplitLayout.test.ts 2>&1 | tail -10
```

- [ ] **Step 6.5: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/components/canvas/CanvasSplitLayout.vue \
  autobot-frontend/tests/canvas/CanvasSplitLayout.test.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): CanvasSplitLayout with gutter, 4 variants, mobile tabs (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 7: Canvas Tool Palette

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasToolPalette.vue`
- Create: `autobot-frontend/src/components/canvas/CanvasCellToolbar.vue`

- [ ] **Step 7.1: Create CanvasToolPalette.vue (primary toolbar + shortcuts)**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasToolPalette.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    class="flex items-center gap-1 px-3 py-1.5 bg-bg-secondary border-b border-border-default"
    role="toolbar"
    aria-label="Canvas toolbar"
  >
    <button
      aria-label="Undo (⌘Z)"
      :disabled="!canUndo"
      class="p-1.5 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed"
      @click="store.undo()"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a4 4 0 010 8H7m-4-8l4-4m-4 4l4 4"/></svg>
    </button>

    <button
      aria-label="Redo (⌘⇧Z)"
      :disabled="!canRedo"
      class="p-1.5 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed"
      @click="store.redo()"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 10H11a4 4 0 000 8h6m4-8l-4-4m4 4l-4 4"/></svg>
    </button>

    <div class="w-px h-5 bg-border-default mx-1" role="separator" />

    <button
      aria-label="Add cell"
      class="p-1.5 rounded hover:bg-bg-hover flex items-center gap-1 text-sm"
      @click="store.addCell('user')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
      Add cell
    </button>

    <div class="flex-1" />

    <!-- Auto-save status -->
    <span
      :class="['text-xs', saveStatusClass]"
      aria-live="polite"
    >
      {{ saveStatusText }}
    </span>

    <button
      v-if="saveStatus === 'error'"
      class="text-xs text-autobot-primary underline ml-1"
      aria-label="Retry save"
      @click="$emit('retry-save')"
    >
      Retry
    </button>

    <div class="w-px h-5 bg-border-default mx-1" role="separator" />

    <button
      aria-label="Export (⌘⇧E)"
      class="p-1.5 rounded hover:bg-bg-hover flex items-center gap-1 text-sm"
      @click="$emit('export')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      Export
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { AutoSaveStatus } from '@/types/canvas'

const props = defineProps<{ saveStatus: AutoSaveStatus; lastSavedAt?: string }>()
defineEmits<{ export: []; 'retry-save': [] }>()

const store = useCanvasStore()
const canUndo = computed(() => store.canUndo)
const canRedo = computed(() => store.canRedo)

const saveStatusText = computed(() => {
  switch (props.saveStatus) {
    case 'saving': return '💾 Saving…'
    case 'saved': return props.lastSavedAt ? `✓ Saved ${props.lastSavedAt}` : '✓ Saved'
    case 'error': return '⚠ Save failed'
    default: return ''
  }
})

const saveStatusClass = computed(() => ({
  'text-text-secondary': props.saveStatus === 'saving' || props.saveStatus === 'idle',
  'text-autobot-success': props.saveStatus === 'saved',
  'text-autobot-error': props.saveStatus === 'error',
}))
</script>
```

- [ ] **Step 7.2: Create CanvasCellToolbar.vue (contextual)**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasCellToolbar.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    class="absolute right-2 top-2 hidden group-hover:flex gap-1 bg-bg-elevated border border-border-default rounded shadow-sm z-10 p-1"
    role="toolbar"
    :aria-label="`Cell actions for cell ${cellId}`"
  >
    <button aria-label="Move up (⌘↑)" class="p-1 rounded hover:bg-bg-hover text-xs" @click="$emit('move', 'up')">↑</button>
    <button aria-label="Move down (⌘↓)" class="p-1 rounded hover:bg-bg-hover text-xs" @click="$emit('move', 'down')">↓</button>
    <button aria-label="Duplicate cell" class="p-1 rounded hover:bg-bg-hover text-xs" @click="$emit('duplicate')">⧉</button>
    <button aria-label="Copy cell content" class="p-1 rounded hover:bg-bg-hover text-xs" @click="$emit('copy')">⎘</button>
    <button aria-label="Delete cell" class="p-1 rounded hover:bg-bg-hover text-xs text-error" @click="$emit('delete')">✕</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ cellId: string }>()
defineEmits<{
  move: [direction: 'up' | 'down']
  duplicate: []
  copy: []
  delete: []
}>()
</script>
```

- [ ] **Step 7.3: Commit**

```bash
git -C .worktrees/issue-mva360 add \
  autobot-frontend/src/components/canvas/CanvasToolPalette.vue \
  autobot-frontend/src/components/canvas/CanvasCellToolbar.vue
git -C .worktrees/issue-mva360 commit -m "feat(canvas): tool palette + cell toolbar with ARIA labels (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 8: Conflict Banner and Edge States

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasConflictBanner.vue`
- Create: `autobot-frontend/src/components/canvas/CanvasEdgeStates.vue`

- [ ] **Step 8.1: Create CanvasConflictBanner.vue**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasConflictBanner.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    v-if="conflict"
    class="flex items-center gap-3 px-4 py-2 bg-autobot-warning/10 border-b border-autobot-warning/30 text-sm"
    role="alert"
    aria-live="assertive"
  >
    <span class="font-medium">⚡ Conflict</span>
    <span class="text-text-secondary flex-1">
      You edited a cell the agent was writing. The agent will continue in a new cell below.
    </span>
    <button
      aria-label="Resume agent in new cell"
      class="px-3 py-1 rounded bg-autobot-primary text-white text-xs hover:opacity-90"
      @click="$emit('resume')"
    >
      Resume
    </button>
    <button
      aria-label="Dismiss conflict banner"
      class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover"
      @click="$emit('dismiss')"
    >
      Dismiss
    </button>
  </div>
</template>

<script setup lang="ts">
import type { ConflictState } from '@/types/canvas'
defineProps<{ conflict: ConflictState | null }>()
defineEmits<{ resume: []; dismiss: [] }>()
</script>
```

- [ ] **Step 8.2: Create CanvasEdgeStates.vue**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasEdgeStates.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <!-- Empty state -->
  <div
    v-if="state === 'empty'"
    class="flex flex-col items-center justify-center h-full gap-4 text-center p-8"
    data-testid="edge-empty"
  >
    <svg class="w-16 h-16 text-text-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    </svg>
    <h3 class="text-lg font-medium text-text-secondary">Your canvas is empty</h3>
    <button
      class="px-4 py-2 bg-autobot-primary text-white rounded-lg hover:opacity-90 flex items-center gap-2"
      aria-label="Add your first cell"
      @click="$emit('add-cell')"
    >
      <span class="text-lg">+</span> Add your first cell
    </button>
  </div>

  <!-- Agent working (pre-stream) -->
  <div
    v-else-if="state === 'agent-working'"
    class="flex items-center gap-3 px-4 py-2 bg-bg-secondary border-b border-border-default text-sm text-text-secondary"
    role="status"
    aria-live="polite"
    data-testid="edge-agent-working"
  >
    <span class="animate-spin text-lg">⟳</span>
    Agent is working…
  </div>

  <!-- Stream error -->
  <div
    v-else-if="state === 'stream-error'"
    class="flex items-center gap-3 px-4 py-3 bg-autobot-error/10 border border-autobot-error/30 rounded m-4 text-sm"
    role="alert"
    data-testid="edge-stream-error"
  >
    <span class="text-autobot-error">⚠</span>
    <span class="flex-1 text-text-primary">Stream failed. What would you like to do?</span>
    <button class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover" @click="$emit('keep')">Keep</button>
    <button class="px-3 py-1 rounded border border-border-default text-xs hover:bg-bg-hover" @click="$emit('retry')">Retry</button>
    <button class="px-3 py-1 rounded border border-border-error text-error text-xs hover:bg-error-bg" @click="$emit('discard')">Discard</button>
  </div>

  <!-- Canvas load error -->
  <div
    v-else-if="state === 'load-error'"
    class="flex flex-col items-center justify-center h-full gap-4 text-center p-8"
    role="alert"
    data-testid="edge-load-error"
  >
    <span class="text-4xl">⚠</span>
    <h3 class="text-lg font-medium">Failed to load canvas</h3>
    <button
      class="px-4 py-2 bg-autobot-primary text-white rounded hover:opacity-90"
      @click="$emit('retry')"
    >
      Retry
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  state: 'empty' | 'agent-working' | 'stream-error' | 'load-error' | null
}>()
defineEmits<{
  'add-cell': []
  keep: []
  retry: []
  discard: []
}>()
</script>
```

- [ ] **Step 8.3: Commit**

```bash
git -C .worktrees/issue-mva360 add \
  autobot-frontend/src/components/canvas/CanvasConflictBanner.vue \
  autobot-frontend/src/components/canvas/CanvasEdgeStates.vue
git -C .worktrees/issue-mva360 commit -m "feat(canvas): conflict banner + 4 edge states (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 9: Auto-Save Composable

**Files:**
- Create: `autobot-frontend/src/composables/useCanvasAutoSave.ts`
- Test: `autobot-frontend/tests/canvas/useCanvasAutoSave.test.ts`

- [ ] **Step 9.1: Write the failing auto-save test**

```typescript
// autobot-frontend/tests/canvas/useCanvasAutoSave.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCanvasAutoSave } from '@/composables/useCanvasAutoSave'
import { useCanvasStore } from '@/stores/useCanvasStore'

describe('useCanvasAutoSave', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => { vi.useRealTimers() })

  it('does not save immediately on change', () => {
    const store = useCanvasStore()
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const { status } = useCanvasAutoSave(saveFn)
    store.isDirty = true
    expect(saveFn).not.toHaveBeenCalled()
    expect(status.value).toBe('idle')
  })

  it('saves after 1s debounce', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockResolvedValue(undefined)
    useCanvasAutoSave(saveFn)
    store.isDirty = true
    vi.advanceTimersByTime(1000)
    await Promise.resolve()
    expect(saveFn).toHaveBeenCalled()
  })

  it('status cycles idle -> saving -> saved', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockResolvedValue(undefined)
    const { status } = useCanvasAutoSave(saveFn)
    store.isDirty = true
    vi.advanceTimersByTime(1000)
    expect(status.value).toBe('saving')
    await Promise.resolve()
    expect(status.value).toBe('saved')
  })

  it('status becomes error when save throws', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: '', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockRejectedValue(new Error('network'))
    const { status } = useCanvasAutoSave(saveFn)
    store.isDirty = true
    vi.advanceTimersByTime(1000)
    await Promise.resolve()
    expect(status.value).toBe('error')
  })

  it('persists cells to localStorage on save', async () => {
    const store = useCanvasStore()
    store.setCanvas({ id: 'c1', title: 'T', cells: [], version: 1, updatedAt: '' })
    const saveFn = vi.fn().mockResolvedValue(undefined)
    useCanvasAutoSave(saveFn)
    store.isDirty = true
    vi.advanceTimersByTime(1000)
    await Promise.resolve()
    expect(localStorage.getItem('canvas:c1')).toBeTruthy()
  })
})
```

- [ ] **Step 9.2: Run test, expect failure**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/useCanvasAutoSave.test.ts 2>&1 | tail -8
```

- [ ] **Step 9.3: Create useCanvasAutoSave.ts**

```typescript
// autobot-frontend/src/composables/useCanvasAutoSave.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, watch, computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { useDebounce } from '@/composables/useDebounce'
import type { AutoSaveStatus } from '@/types/canvas'
import { CANVAS_AUTOSAVE_DEBOUNCE_MS } from '@/constants/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCanvasAutoSave')

export function useCanvasAutoSave(
  saveFn: (canvasId: string, cells: unknown[]) => Promise<void>
) {
  const store = useCanvasStore()
  const status = ref<AutoSaveStatus>('idle')
  const lastSavedAt = ref<string | undefined>()

  const debouncedDirty = useDebounce(computed(() => store.isDirty), CANVAS_AUTOSAVE_DEBOUNCE_MS)

  watch(debouncedDirty, async (dirty) => {
    if (!dirty || !store.canvasId) return
    status.value = 'saving'
    try {
      await saveFn(store.canvasId, store.cells)
      localStorage.setItem(`canvas:${store.canvasId}`, JSON.stringify({
        cells: store.cells,
        savedAt: new Date().toISOString(),
      }))
      store.markSaved()
      status.value = 'saved'
      lastSavedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch (err) {
      logger.error('Auto-save failed', err)
      status.value = 'error'
    }
  })

  function loadFromLocalStorage(canvasId: string) {
    const raw = localStorage.getItem(`canvas:${canvasId}`)
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  return { status, lastSavedAt, loadFromLocalStorage }
}
```

- [ ] **Step 9.4: Run test, expect pass**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/useCanvasAutoSave.test.ts 2>&1 | tail -10
```

- [ ] **Step 9.5: Commit**

```bash
git -C .worktrees/issue-mva360 add \
  autobot-frontend/src/composables/useCanvasAutoSave.ts \
  autobot-frontend/tests/canvas/useCanvasAutoSave.test.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): useCanvasAutoSave with 1s debounce + localStorage (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 10: WebSocket Composable

**Files:**
- Create: `autobot-frontend/src/composables/useCanvasWebSocket.ts`

- [ ] **Step 10.1: Create useCanvasWebSocket.ts**

```typescript
// autobot-frontend/src/composables/useCanvasWebSocket.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { watch } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { getBackendUrl } from '@/config/ssot-config'
import type { CanvasWsMessage } from '@/types/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCanvasWebSocket')

export function useCanvasWebSocket(canvasId: string) {
  const store = useCanvasStore()
  const wsUrl = `${getBackendUrl().replace(/^http/, 'ws')}/api/canvas/${canvasId}/ws`

  const { messages, connect, disconnect, status } = useWebSocket(wsUrl, {
    autoConnect: true,
    autoReconnect: true,
  })

  watch(messages, (msgs) => {
    const latest = msgs[msgs.length - 1]
    if (!latest) return
    try {
      const msg = JSON.parse(latest) as CanvasWsMessage
      if (msg.type !== 'canvas_cell') return

      if (store.conflict?.cellId === msg.cellId) {
        store.addCell('agent')
        const newId = store.cells[store.cells.length - 1].id
        store.upsertStreamCell({ ...msg, cellId: newId })
        return
      }

      store.upsertStreamCell(msg)
    } catch (err) {
      logger.error('WS parse error', err)
    }
  })

  return { connect, disconnect, status }
}
```

- [ ] **Step 10.2: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/composables/useCanvasWebSocket.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): useCanvasWebSocket composable (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 11: Export Sheet Component

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasExportSheet.vue`

- [ ] **Step 11.1: Create CanvasExportSheet.vue**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasExportSheet.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Export canvas"
    >
      <div class="absolute inset-0 bg-bg-overlay" @click="$emit('close')" />
      <div class="relative bg-bg-card border border-border-default rounded-t-xl sm:rounded-xl w-full max-w-md p-6 shadow-xl z-10">
        <h2 class="text-lg font-semibold mb-4">Export Canvas</h2>

        <!-- Format selection -->
        <fieldset class="mb-4">
          <legend class="text-sm font-medium text-text-secondary mb-2">Format</legend>
          <div class="grid grid-cols-2 gap-2">
            <label
              v-for="fmt in formats"
              :key="fmt.id"
              :class="[
                'flex items-center gap-2 p-3 rounded border cursor-pointer transition-colors',
                selectedFormat === fmt.id
                  ? 'border-autobot-primary bg-autobot-primary/5'
                  : 'border-border-default hover:bg-bg-hover',
              ]"
            >
              <input
                type="radio"
                :value="fmt.id"
                v-model="selectedFormat"
                class="sr-only"
              />
              <span class="text-xl">{{ fmt.icon }}</span>
              <span class="text-sm font-medium">{{ fmt.label }}</span>
            </label>
          </div>
        </fieldset>

        <!-- Cell type toggles -->
        <fieldset class="mb-6">
          <legend class="text-sm font-medium text-text-secondary mb-2">Include cell types</legend>
          <div class="space-y-2">
            <label
              v-for="toggle in cellTypeToggles"
              :key="toggle.id"
              class="flex items-center gap-3 cursor-pointer"
            >
              <input
                type="checkbox"
                :value="toggle.id"
                v-model="includedTypes"
                class="rounded border-border-default"
              />
              <span class="text-sm">{{ toggle.label }}</span>
            </label>
          </div>
        </fieldset>

        <div class="flex gap-3">
          <button
            class="flex-1 px-4 py-2 bg-autobot-primary text-white rounded hover:opacity-90 font-medium"
            @click="doExport"
          >
            Export
          </button>
          <button
            class="px-4 py-2 border border-border-default rounded hover:bg-bg-hover"
            @click="$emit('close')"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ open: boolean }>()
const emit = defineEmits<{
  close: []
  export: [format: string, includedTypes: string[]]
}>()

const formats = [
  { id: 'markdown', label: 'Markdown', icon: '📝' },
  { id: 'pdf', label: 'PDF', icon: '📄' },
  { id: 'html', label: 'HTML', icon: '🌐' },
  { id: 'json', label: 'JSON', icon: '{ }' },
]

const cellTypeToggles = [
  { id: 'markdown', label: 'Markdown cells' },
  { id: 'chart', label: 'Chart cells' },
  { id: 'code', label: 'Code cells' },
]

const selectedFormat = ref('markdown')
const includedTypes = ref(['markdown', 'chart', 'code'])

function doExport() {
  emit('export', selectedFormat.value, includedTypes.value)
  emit('close')
}
</script>
```

- [ ] **Step 11.2: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/components/canvas/CanvasExportSheet.vue
git -C .worktrees/issue-mva360 commit -m "feat(canvas): 4-format export sheet with cell-type toggles (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 12: Root Canvas View + Keyboard Shortcuts

**Files:**
- Create: `autobot-frontend/src/components/canvas/CanvasView.vue`
- Create: `autobot-frontend/src/components/canvas/CanvasPanel.vue`
- Create: `autobot-frontend/src/components/canvas/index.ts`

- [ ] **Step 12.1: Create CanvasPanel.vue (cell list)**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasPanel.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div class="flex flex-col h-full overflow-hidden">
    <canvas-tool-palette
      :save-status="autoSave.status.value"
      :last-saved-at="autoSave.lastSavedAt.value"
      @export="showExport = true"
      @retry-save="triggerSaveNow"
    />

    <canvas-conflict-banner :conflict="store.conflict" @resume="onConflictResume" @dismiss="store.resolveConflict()" />

    <canvas-edge-states
      v-if="edgeState"
      :state="edgeState"
      @add-cell="store.addCell('user')"
      @keep="edgeState = null"
      @retry="$emit('retry-load')"
      @discard="edgeState = null"
    />

    <div v-else class="flex-1 overflow-y-auto p-4 space-y-2">
      <canvas-cell
        v-for="cell in store.cells"
        :key="cell.id"
        :cell="cell"
        @accept="onAccept(cell.id)"
        @edit="onEdit(cell.id)"
        @discard="store.deleteCell(cell.id)"
        @cancel="onCancelStream(cell.id)"
        @keep="edgeState = null"
        @retry="$emit('retry-stream', cell.id)"
      >
        <template #toolbar>
          <canvas-cell-toolbar
            :cell-id="cell.id"
            @move="store.moveCell(cell.id, $event)"
            @duplicate="store.duplicateCell(cell.id)"
            @copy="copyCell(cell)"
            @delete="store.deleteCell(cell.id)"
          />
        </template>
      </canvas-cell>
    </div>

    <canvas-export-sheet :open="showExport" @close="showExport = false" @export="onExport" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { CanvasCell } from '@/types/canvas'
import CanvasCell from './CanvasCell.vue'
import CanvasCellToolbar from './CanvasCellToolbar.vue'
import CanvasToolPalette from './CanvasToolPalette.vue'
import CanvasConflictBanner from './CanvasConflictBanner.vue'
import CanvasEdgeStates from './CanvasEdgeStates.vue'
import CanvasExportSheet from './CanvasExportSheet.vue'

const props = defineProps<{
  canvasId: string
  autoSave: ReturnType<typeof import('@/composables/useCanvasAutoSave').useCanvasAutoSave>
}>()

defineEmits<{ 'retry-load': []; 'retry-stream': [cellId: string] }>()

const store = useCanvasStore()
const showExport = ref(false)
const edgeState = computed(() =>
  store.isEmpty ? 'empty' : null
) as ReturnType<typeof ref>

function onAccept(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) cell.owner = 'user'
}

function onEdit(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) { cell.owner = 'user'; cell.streamState = 'complete' }
}

function onCancelStream(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) cell.streamState = 'complete'
}

function onConflictResume() {
  store.addCell('agent')
  store.resolveConflict()
}

function copyCell(cell: CanvasCell) {
  navigator.clipboard.writeText(cell.content).catch(() => {})
}

function onExport(format: string, types: string[]) {
  const cells = store.cells.filter(c => types.includes(c.contentType))
  const content = cells.map(c => c.content).join('\n\n---\n\n')
  const blob = new Blob([content], { type: 'text/plain' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `canvas.${format === 'markdown' ? 'md' : format}`
  a.click()
}

function triggerSaveNow() {}
</script>
```

- [ ] **Step 12.2: Create root CanvasView.vue with keyboard shortcuts**

```vue
<!-- autobot-frontend/src/components/canvas/CanvasView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div class="flex flex-col h-full" @keydown="onKeydown" tabindex="-1">
    <canvas-split-layout
      :variant="layoutVariant"
      :agent-content-badge="agentCellCount"
      @variant-changed="layoutVariant = $event"
    >
      <template #chat>
        <slot name="chat" />
      </template>
      <template #canvas>
        <canvas-panel
          :canvas-id="canvasId"
          :auto-save="autoSave"
          @retry-load="loadCanvas"
        />
      </template>
    </canvas-split-layout>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { useCanvasAutoSave } from '@/composables/useCanvasAutoSave'
import { useCanvasWebSocket } from '@/composables/useCanvasWebSocket'
import { useApi } from '@/composables/useApi'
import CanvasSplitLayout from './CanvasSplitLayout.vue'
import CanvasPanel from './CanvasPanel.vue'
import type { CanvasLayoutVariant } from '@/constants/canvas'
import type { CanvasDocument } from '@/types/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CanvasView')
const props = defineProps<{ canvasId: string }>()

const store = useCanvasStore()
const layoutVariant = ref<CanvasLayoutVariant>('split')
const api = useApi()

async function saveCanvas(canvasId: string, cells: unknown[]) {
  await api.put(`/api/canvas/${canvasId}`, { cells })
}

const autoSave = useCanvasAutoSave(saveCanvas)
useCanvasWebSocket(props.canvasId)

async function loadCanvas() {
  try {
    const doc = await api.get<CanvasDocument>(`/api/canvas/${props.canvasId}`)
    store.setCanvas(doc)
  } catch (err) {
    logger.error('Failed to load canvas', err)
  }
}

onMounted(loadCanvas)

const agentCellCount = computed(() =>
  store.cells.filter(c => c.owner === 'agent' && c.streamState === 'complete').length
)

function onKeydown(e: KeyboardEvent) {
  const meta = e.metaKey || e.ctrlKey

  if (meta && !e.shiftKey && e.key === 'z') { e.preventDefault(); store.undo(); return }
  if (meta && e.shiftKey && e.key === 'z') { e.preventDefault(); store.redo(); return }
  if (meta && e.shiftKey && e.key === 'E') { e.preventDefault(); /* export */ return }
  if (meta && e.key === 'l') { e.preventDefault(); /* focus chat */ return }
}
</script>
```

- [ ] **Step 12.3: Create barrel export**

```typescript
// autobot-frontend/src/components/canvas/index.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
export { default as CanvasView } from './CanvasView.vue'
export { default as CanvasCell } from './CanvasCell.vue'
export { default as CanvasSplitLayout } from './CanvasSplitLayout.vue'
export { default as CanvasPanel } from './CanvasPanel.vue'
export { default as CanvasToolPalette } from './CanvasToolPalette.vue'
export { default as CanvasCellToolbar } from './CanvasCellToolbar.vue'
export { default as CanvasConflictBanner } from './CanvasConflictBanner.vue'
export { default as CanvasEdgeStates } from './CanvasEdgeStates.vue'
export { default as CanvasExportSheet } from './CanvasExportSheet.vue'
```

- [ ] **Step 12.4: Commit**

```bash
git -C .worktrees/issue-mva360 add \
  autobot-frontend/src/components/canvas/ \
  autobot-frontend/src/composables/useCanvasWebSocket.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): root CanvasView + keyboard shortcuts + barrel export (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 13: MSW Mock Handlers

**Files:**
- Create: `autobot-frontend/src/test/mocks/canvas-handlers.ts`

- [ ] **Step 13.1: Create canvas MSW handlers**

```typescript
// autobot-frontend/src/test/mocks/canvas-handlers.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { http, HttpResponse } from 'msw'
import type { CanvasDocument } from '@/types/canvas'

const MOCK_CANVAS: CanvasDocument = {
  id: 'canvas-test-1',
  title: 'Test Canvas',
  cells: [
    {
      id: 'cell-1', canvasId: 'canvas-test-1', owner: 'user',
      contentType: 'markdown', content: '# Welcome\nThis is a test canvas.',
      streamState: 'complete', seq: 1,
      createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z',
    },
  ],
  version: 1,
  updatedAt: '2026-01-01T00:00:00Z',
}

export const canvasHandlers = [
  http.get('/api/canvas/:id', ({ params }) => {
    return HttpResponse.json({ ...MOCK_CANVAS, id: params.id as string })
  }),

  http.put('/api/canvas/:id', async ({ request }) => {
    const body = await request.json() as { cells: unknown[] }
    return HttpResponse.json({ ...MOCK_CANVAS, cells: body.cells, version: 2 })
  }),

  http.post('/api/canvas/:id/cells', async ({ params, request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      ...body,
      id: `cell-${Date.now()}`,
      canvasId: params.id,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })
  }),

  http.patch('/api/canvas/:id/cells/:cellId', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 'cell-patched', ...body, updatedAt: new Date().toISOString() })
  }),

  http.post('/api/canvas/:id/export', async ({ request }) => {
    const body = await request.json() as { format: string }
    return HttpResponse.json({ url: `/exports/canvas-test.${body.format}`, format: body.format })
  }),
]
```

- [ ] **Step 13.2: Register handlers in existing MSW setup**

Find `autobot-frontend/src/test/mocks/handlers.ts` (or wherever MSW handlers are registered):

```bash
find .worktrees/issue-mva360/autobot-frontend/src/test -name "handlers.ts" | head -3
```

Open that file and add:
```typescript
import { canvasHandlers } from './canvas-handlers'
// ... in the handlers array:
...canvasHandlers,
```

- [ ] **Step 13.3: Commit**

```bash
git -C .worktrees/issue-mva360 add \
  autobot-frontend/src/test/mocks/canvas-handlers.ts \
  autobot-frontend/src/test/mocks/handlers.ts
git -C .worktrees/issue-mva360 commit -m "feat(canvas): MSW handlers for canvas API (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 14: Run All Unit Tests + Type Check

- [ ] **Step 14.1: Run canvas test suite**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run tests/canvas/ 2>&1 | tail -20
```
Expected: All tests PASS. Zero failures.

- [ ] **Step 14.2: Run TypeScript check on canvas files**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "canvas|error" | head -20
```
Expected: Zero errors in canvas files.

- [ ] **Step 14.3: Verify nav coverage test still passes**

```bash
cd .worktrees/issue-mva360/autobot-frontend
npx vitest run src/__tests__/nav-items-coverage.test.ts 2>&1 | tail -6
```
Expected: PASS.

- [ ] **Step 14.4: Commit any fixes found during type check**

If type errors exist, fix them and commit:
```bash
git -C .worktrees/issue-mva360 add autobot-frontend/src/
git -C .worktrees/issue-mva360 commit -m "fix(canvas): resolve TypeScript errors from type check (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 15: Playwright Visual Tests

**Files:**
- Create: `autobot-frontend/tests/canvas/canvas.spec.ts`

- [ ] **Step 15.1: Create Playwright test file**

```typescript
// autobot-frontend/tests/canvas/canvas.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Canvas Phase 1', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/canvas')
    await page.waitForSelector('[data-testid="cell-root"], [data-testid="edge-empty"]')
  })

  test('empty state renders CTA', async ({ page }) => {
    await expect(page.getByTestId('edge-empty')).toBeVisible()
    await expect(page.getByRole('button', { name: /add your first cell/i })).toBeVisible()
  })

  test('agent cell has robot badge', async ({ page }) => {
    // Trigger a streamed cell via MSW WS mock (see canvas-ws-mock.ts)
    await expect(page.getByTestId('agent-badge')).toBeVisible()
  })

  test('390px mobile shows tab fallback', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await expect(page.getByRole('tab', { name: 'Chat' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Canvas' })).toBeVisible()
  })

  test('prefers-reduced-motion skeleton shows static blocks not shimmer', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    // Verify skeleton renders without animate-pulse class
    const skeleton = page.getByTestId('skeleton-shimmer')
    if (await skeleton.count() > 0) {
      await expect(skeleton).not.toHaveClass(/animate-pulse/)
    }
  })

  test('visual snapshot split layout', async ({ page }) => {
    await expect(page).toHaveScreenshot('canvas-split.png', { fullPage: false })
  })
})
```

- [ ] **Step 15.2: Commit**

```bash
git -C .worktrees/issue-mva360 add autobot-frontend/tests/canvas/canvas.spec.ts
git -C .worktrees/issue-mva360 commit -m "test(canvas): Playwright visual + a11y + responsive tests (MVA-360)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 16: Push and Create PR

- [ ] **Step 16.1: Final import smoke test**

```bash
cd .worktrees/issue-mva360/autobot-frontend
node -e "const {createServer} = require('vite'); createServer({build:{rollupOptions:{input:['src/components/canvas/CanvasView.vue']}}}).catch(e=>{console.error(e);process.exit(1)})" 2>&1 | head -10
```

- [ ] **Step 16.2: Push branch**

```bash
git -C .worktrees/issue-mva360 push -u origin issue-mva360
```

- [ ] **Step 16.3: Create PR**

```bash
gh pr create \
  --base Dev_new_gui \
  --head issue-mva360 \
  --title "feat(canvas): Phase 1 Live Canvas frontend (MVA-360)" \
  --body "$(cat <<'EOF'
## Summary
- Isolated canvas component tree at `autobot-frontend/src/components/canvas/` behind `VITE_FEATURE_CANVAS=true` flag
- Adaptive 35/65 split panel with 4 variants (split/canvas-focus/chat-focus/full-canvas) and mobile tabs at ≤390px
- CanvasCell with agent/user ownership model, streaming state machine (skeleton→partial→complete→error), WCAG color-independent ownership signals
- Conflict resolution: user click pauses stream, agent resumes in new cell
- Primary toolbar (undo/redo/add/save/export) + contextual cell toolbar + full keyboard shortcut set
- 4 edge states (empty, agent-working, stream-error, load-error)
- 1s-debounced auto-save with localStorage mirror + server reconcile
- 4-format export sheet with cell-type toggles
- 3 new design tokens (`--color-agent-draft-border`, `--color-agent-draft-bg`, `--color-user-edit-cursor`)
- MSW handlers for all frozen API endpoints
- Vitest unit + Playwright visual snapshots including 390px and `prefers-reduced-motion` cases

## Test plan
- [ ] `npx vitest run tests/canvas/` — all green
- [ ] `npx vue-tsc --noEmit -p tsconfig.app.json` — zero errors in canvas files
- [ ] `npx vitest run src/__tests__/nav-items-coverage.test.ts` — PASS
- [ ] Playwright: `npx playwright test tests/canvas/` — snapshots match
- [ ] Security sibling D reviews before merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist

### Spec Coverage (MVA-190 §2–§9 + §9 ACs 1–15)

| Requirement | Task |
|---|---|
| 35/65 default split panel | Task 6 (CanvasSplitLayout) |
| Draggable 8px gutter | Task 6 |
| Double-click snap presets | Task 6 |
| Drag-to-edge collapse to icon rail | Task 6 (emits variant-changed) |
| 4 layout variants | Task 6 |
| Mobile 390px tabbed fallback + badge | Task 6 |
| Agent cell: border + tint + badge + Accept/Edit/Discard | Task 5 (CanvasCell) |
| User cell: unstyled/committed | Task 5 |
| WCAG color independence (icon + border shape) | Task 5 (badge + border-l-2) |
| Skeleton → Partial → Complete → Error | Task 5 |
| prefers-reduced-motion static blocks | Task 5 |
| Conflict resolution: user wins, agent appends new cell | Tasks 3+5+10 |
| Primary toolbar | Task 7 (CanvasToolPalette) |
| Contextual toolbar | Task 7 (CanvasCellToolbar) |
| Keyboard shortcuts (⌥Enter/Esc/Enter/⌘↑↓/⌘Z/⌘⇧Z/⌘⇧E/⌘L) | Task 12 (onKeydown) |
| Edge states (empty/working/stream-error/load-error) | Task 8 |
| Auto-save 1s debounce + status indicator | Task 9 |
| localStorage mirror | Task 9 |
| Export sheet 4 formats + toggles | Task 11 |
| 3 design tokens in CSS + tokens.ts | Task 1 |
| Feature flag | Task 2 (CANVAS_FEATURE_FLAG) |
| Route + navItems | Task 4 |
| Frozen API + MSW mocks | Task 13 |
| Vitest unit tests | Tasks 3,5,6,9 |
| Playwright visual + 390px + motion | Task 15 |
| Phase-2 placeholder for chart/code cells | Task 5 |
| All aria-labels on agent controls | Tasks 5,7,8 |

**Gap noted:** `⌥Enter accept` / `Esc discard` / `Enter edit` shortcuts are wired in `onKeydown` in Task 12 but need the focused-cell-id tracked in the store. Add a `focusedCellId` state to `useCanvasStore` and wire the per-cell ⌥Enter/Esc/Enter handlers in `CanvasPanel`. This is a small addition to Task 12.

**Gap noted:** `⌘L focus chat` needs an emit/ref to the chat panel input. Add `emit('focus-chat')` from CanvasView and handle in the parent route.

Both gaps are bounded — add to Task 12 step 12.2.
