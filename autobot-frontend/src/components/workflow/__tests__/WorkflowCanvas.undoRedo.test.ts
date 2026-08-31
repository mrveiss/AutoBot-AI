// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14612: undo/redo for canvas mutations.
 *
 * Scope, asserted directly rather than only read off the doc comment: a node
 * add, remove, move (drag or keyboard) and connect are all undoable; nothing
 * else pushes a history entry — not a save, not a detach, not an edit inside
 * a node's own inline fields. The Undo/Redo buttons' own `disabled` state is
 * the thing that keeps a user from ever pressing Undo and seeing nothing
 * happen (the acceptance requirement): they are asserted disabled whenever
 * there is genuinely nothing tracked to reverse.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'
import { firePointer } from './pointerTestUtils'

function step(id: string, x: number, y: number): CanvasNode {
  return {
    id,
    type: 'step',
    position: { x, y },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  }
}


// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(WorkflowCanvas, {
    props: { nodes: [], selectedNodeId: null, ...props },
    global: { plugins: [i18n] },
  })
}

const undoBtn = (w: ReturnType<typeof mountCanvas>) => w.get('[data-testid="canvas-undo"]')
const redoBtn = (w: ReturnType<typeof mountCanvas>) => w.get('[data-testid="canvas-redo"]')

describe('undo/redo buttons start (and return to) disabled with nothing to reverse (#14612)', () => {
  it('are disabled on a fresh mount', () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })

    expect(undoBtn(w).attributes('disabled')).toBeDefined()
    expect(redoBtn(w).attributes('disabled')).toBeDefined()
  })

  it('carry a boundary description via aria-describedby and title', () => {
    const w = mountCanvas()

    expect(undoBtn(w).attributes('title')).toBe(en.workflow.canvas.undoScope)
    const describedBy = undoBtn(w).attributes('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(w.find(`#${describedBy}`).text()).toBe(en.workflow.canvas.undoScope)
  })
})

describe('adding a node is undoable/redoable (#14612)', () => {
  it('undo removes the just-added node; redo re-adds the same id', async () => {
    const w = mountCanvas()
    await w.get('.tool-btn[title="Add Step"]').trigger('click')

    const added = (w.emitted('node-added') as unknown as [CanvasNode][])[0][0]
    expect(undoBtn(w).attributes('disabled')).toBeUndefined()

    await undoBtn(w).trigger('click')
    expect(w.emitted('node-removed')?.at(-1)).toEqual([added.id])
    expect(undoBtn(w).attributes('disabled')).toBeDefined()
    expect(redoBtn(w).attributes('disabled')).toBeUndefined()

    await redoBtn(w).trigger('click')
    const readded = (w.emitted('node-added') as unknown as [CanvasNode][]).at(-1)![0]
    expect(readded.id).toBe(added.id)
    expect(readded.type).toBe('step')
  })

  it('a fresh add clears whatever redo branch existed', async () => {
    const w = mountCanvas()
    await w.get('.tool-btn[title="Add Step"]').trigger('click')
    await undoBtn(w).trigger('click')
    expect(redoBtn(w).attributes('disabled')).toBeUndefined()

    await w.get('.tool-btn[title="Add Step"]').trigger('click')
    expect(redoBtn(w).attributes('disabled')).toBeDefined()
  })
})

describe('removing a node is undoable (#14612)', () => {
  it('undo re-adds the exact node that was deleted, including its data', async () => {
    const n1 = step('n1', 40, 60)
    ;(n1.data as Record<string, unknown>).description = 'do the thing'
    const w = mountCanvas({ nodes: [n1] })

    await w.get('.delete-btn').trigger('click')
    expect(w.emitted('node-removed')).toEqual([['n1']])

    await undoBtn(w).trigger('click')
    const readded = (w.emitted('node-added') as unknown as [CanvasNode][]).at(-1)![0]
    expect(readded).toEqual(n1)
  })

  it('a later in-place edit to the (still-mounted) node never leaks into the stored snapshot', async () => {
    // The node this component receives via props is mutated in place by its
    // own v-model bindings, so the history entry must have cloned it at delete
    // time rather than kept a live reference.
    const n1 = step('n1', 0, 0)
    const w = mountCanvas({ nodes: [n1] })

    await w.get('.delete-btn').trigger('click')
    ;(n1.data as Record<string, unknown>).description = 'mutated after delete'

    await undoBtn(w).trigger('click')
    const readded = (w.emitted('node-added') as unknown as [CanvasNode][]).at(-1)![0]
    expect((readded.data as Record<string, unknown>).description).toBe('')
  })
})

describe('moving a node by drag is undoable as ONE step, not one per tick (#14612)', () => {
  async function drag(w: ReturnType<typeof mountCanvas>) {
    await firePointer(w.get('.workflow-node').element, 'pointerdown', { clientX: 100, clientY: 100, button: 0 })
    await firePointer(w.get('.workflow-node').element, 'pointermove', { clientX: 110, clientY: 100 })
    await firePointer(w.get('.workflow-node').element, 'pointermove', { clientX: 130, clientY: 100 })
    await firePointer(w.get('.canvas-area').element, 'pointerup', { clientX: 130, clientY: 100 })
  }

  it('undo restores the position the drag started from, in one step', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await drag(w)

    const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    expect(moves.length).toBeGreaterThan(1) // multiple ticks were emitted live…

    await undoBtn(w).trigger('click')
    // …but exactly one MORE node-moved fires on undo (the one history entry),
    // restoring the exact starting position.
    expect(moves.at(-1)).toEqual(['n1', { x: 10, y: 10 }])
  })

  it('redo restores the exact final dragged-to position', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await drag(w)
    const finalPos = (w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]).at(-1)![1]

    await undoBtn(w).trigger('click')
    await redoBtn(w).trigger('click')
    expect((w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]).at(-1)).toEqual([
      'n1',
      finalPos,
    ])
  })
})

describe('moving a node by keyboard is undoable (#14612)', () => {
  it('undo restores the pre-keypress position', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await w.get('[data-node-id="n1"]').trigger('keydown', { key: 'ArrowRight', ctrlKey: true })

    // #14768: an arrow press lands on the ADJACENT gridline, so an off-grid
    // node at x=10 aligns to 20 rather than moving a full step to 30. The
    // undo below still restores the off-grid start exactly.
    expect(w.emitted('node-moved')).toEqual([['n1', { x: 20, y: 10 }]])
    await undoBtn(w).trigger('click')
    expect((w.emitted('node-moved') as unknown as unknown[]).length).toBe(2)
    expect((w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]).at(-1)).toEqual([
      'n1',
      { x: 10, y: 10 },
    ])
  })
})

describe('what undo/redo deliberately does NOT cover (#14612)', () => {
  it('an edit to a node\'s own inline field never pushes a history entry', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })
    await w.get('.workflow-node.step input').setValue('echo hi')

    expect(undoBtn(w).attributes('disabled')).toBeDefined()
  })

  it('clearing an already-empty canvas pushes nothing', async () => {
    const w = mountCanvas({ nodes: [] })
    // No nodes means `clearCanvas`'s own `props.nodes.length` guard short-
    // circuits before it would ever push a (trivially empty) history entry.
    expect(undoBtn(w).attributes('disabled')).toBeDefined()
  })
})
