// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14612: multi-select — `selectedIds`/`mutateSelection`/`applySelectionIntent`
 * were implemented and never exercised by a test. This covers:
 *   - shift-click adds to the selection without clearing what was already
 *     there (the `selectedNodeId` prop keeps its own pre-#14612 meaning and
 *     is never touched by the additive path).
 *   - a plain click replaces the whole selection, mirroring pre-#14612
 *     single-select behaviour exactly.
 *   - the multi-selected visual carries a shape/icon signal, not only the
 *     colour a dashed outline happens to use (#13941).
 *   - a bulk drag moves every selected node by the same delta as ONE undo
 *     step, not one per node.
 *   - the exact contract `selectedIds` (local) keeps with `selectedNodeId`
 *     (the prop `OrgChart.vue`/`WorkflowBuilderView.vue` still own): a
 *     shift-click down to a single survivor re-emits `node-selected` with
 *     it, matching plain-click semantics.
 *
 * `mountCanvas` never wires a real parent, so every place this file needs
 * the prop to reflect what a real consumer would do in response to
 * `node-selected` calls `syncSelection` explicitly — the same round trip
 * `OrgChart.onCanvasNodeSelected`/`WorkflowBuilderView`'s own handler
 * perform in production.
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

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(WorkflowCanvas, {
    props: {
      nodes: [step('n1', 10, 10), step('n2', 300, 10)],
      selectedNodeId: null,
      ...props,
    },
    global: { plugins: [createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const undoBtn = (w: Wrapper) => w.get('[data-testid="canvas-undo"]')
const nodeSelected = (w: Wrapper) => (w.emitted('node-selected') ?? []) as unknown as (string | null)[][]

/** Mirrors what `OrgChart.onCanvasNodeSelected`/`WorkflowBuilderView`'s own
 *  handler do with every `node-selected` emit: feed it straight back in as
 *  the prop. Called after any interaction whose contract this file is
 *  asserting, so the component sees the same round trip a real mount would. */
async function syncSelection(w: Wrapper): Promise<void> {
  const last = nodeSelected(w).at(-1)
  if (last) await w.setProps({ selectedNodeId: last[0] })
}

describe('shift-click adds to the selection without clearing it (#14612)', () => {
  it('keeps n1 selected (via the synced prop) after shift-clicking n2', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await syncSelection(w)
    expect(w.props('selectedNodeId')).toBe('n1')

    await node(w, 'n2').trigger('click', { shiftKey: true })

    // n1 is still the single-selection prop's target — untouched by the
    // additive click — and n2 has joined the local multi-selection.
    expect(node(w, 'n1').classes()).toContain('selected')
    expect(node(w, 'n2').classes()).toContain('multi-selected')
    expect(w.find('[data-testid="canvas-selection-status"]').text()).toContain('2')
  })

  it('toggles a shift-clicked node back out again', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await syncSelection(w)
    await node(w, 'n2').trigger('click', { shiftKey: true })
    await syncSelection(w)

    await node(w, 'n2').trigger('click', { shiftKey: true })

    expect(node(w, 'n2').classes()).not.toContain('multi-selected')
    expect(w.find('[data-testid="canvas-selection-status"]').exists()).toBe(false)
  })
})

describe('a plain click replaces the selection (#14612)', () => {
  it('drops n1 out of the selection once n2 is plain-clicked', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await syncSelection(w)
    await node(w, 'n2').trigger('click', { shiftKey: true })
    await syncSelection(w)
    expect(w.find('[data-testid="canvas-selection-status"]').text()).toContain('2')

    await node(w, 'n2').trigger('click')
    await syncSelection(w)

    expect(w.props('selectedNodeId')).toBe('n2')
    expect(node(w, 'n1').classes()).not.toContain('selected')
    expect(node(w, 'n1').classes()).not.toContain('multi-selected')
    expect(w.find('[data-testid="canvas-selection-status"]').exists()).toBe(false)
  })
})

describe('the selectedIds/selectedNodeId contract (#14612)', () => {
  it('re-emits node-selected with the survivor once a shift-toggle leaves exactly one', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await syncSelection(w)
    await node(w, 'n2').trigger('click', { shiftKey: true })
    // Two selected: the doc-comment contract says this emits null, since no
    // single node is open for the drawer.
    expect(nodeSelected(w).at(-1)).toEqual([null])
    await syncSelection(w)
    expect(w.props('selectedNodeId')).toBeNull()

    await node(w, 'n2').trigger('click', { shiftKey: true })

    // Back down to one survivor (n1) — re-emitted exactly like a plain click
    // on n1 would, not left at null.
    expect(nodeSelected(w).at(-1)).toEqual(['n1'])
  })

  it('never lets isMultiOnlySelected double up on the node selectedNodeId already owns', async () => {
    // A node can be BOTH the prop's single selection and a member of the
    // local multi-selection set at once (shift-clicking the already-selected
    // node onto itself). The badge/outline must stay off it — `.selected`
    // already carries that signal — so the two visual states never stack.
    const w = mountCanvas({ selectedNodeId: 'n1' })
    await node(w, 'n1').trigger('click', { shiftKey: true })

    expect(node(w, 'n1').classes()).toContain('selected')
    expect(node(w, 'n1').classes()).not.toContain('multi-selected')
    expect(w.find('[data-testid="node-multi-badge"]').exists()).toBe(false)
  })
})

describe('multi-selection is visible by more than colour (#13941/#14612)', () => {
  it('renders a badge icon and a distinct class on every multi-selected node, not just a hue', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await node(w, 'n2').trigger('click', { shiftKey: true })

    for (const id of ['n1', 'n2']) {
      const el = node(w, id)
      expect(el.classes()).toContain('multi-selected')
      const badge = el.get('[data-testid="node-multi-badge"]')
      expect(badge.attributes('aria-hidden')).toBe('true')
      expect(badge.find('svg, i').exists()).toBe(true)
    }
  })

  it('does not show the badge on a lone, single-click selection', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await syncSelection(w)

    expect(w.find('[data-testid="node-multi-badge"]').exists()).toBe(false)
  })
})

describe('a bulk drag moves the whole selection as ONE undo step (#14612)', () => {
  async function dragNode1(w: Wrapper) {
    await firePointer(node(w, 'n1').element, 'pointerdown', { clientX: 100, clientY: 100, button: 0 })
    await firePointer(node(w, 'n1').element, 'pointermove', { clientX: 110, clientY: 100 })
    await firePointer(node(w, 'n1').element, 'pointermove', { clientX: 130, clientY: 100 })
    await firePointer(w.get('.canvas-area').element, 'pointerup', { clientX: 130, clientY: 100 })
  }

  it('moves n2 by the same delta as the dragged n1, and undoes both in one click', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click')
    await node(w, 'n2').trigger('click', { shiftKey: true })

    await dragNode1(w)

    const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    const n1Moves = moves.filter(([id]) => id === 'n1')
    const n2Moves = moves.filter(([id]) => id === 'n2')
    expect(n1Moves.length).toBeGreaterThan(0)
    expect(n2Moves.length).toBeGreaterThan(0)
    // The pointer moved from clientX 100 to 130 (30px, at zoom 1) — n1
    // dragged 10 -> 40, and n2 must have moved by that identical 30px delta
    // from ITS OWN start (300 -> 330). That invariant is what this test
    // guards and it is unchanged by #14768.
    //
    // The y values move 10 -> 20 because a drop snaps BOTH axes, even one the
    // pointer did not move: the point of the grid is that a node is on it
    // after a drag, and an axis exempted for not having moved would leave
    // nodes half-aligned forever. n2 follows by the leader's delta (+10), so
    // the two still moved by an identical vector.
    expect(n1Moves.at(-1)![1]).toEqual({ x: 40, y: 20 })
    expect(n2Moves.at(-1)![1]).toEqual({ x: 330, y: 20 })

    expect(undoBtn(w).attributes('disabled')).toBeUndefined()
    const movesBeforeUndo = moves.length

    await undoBtn(w).trigger('click')

    // Exactly one MORE move per selected node — one gesture, one entry —
    // restoring both to where the drag started, and nothing left to undo.
    // `undo()` replays a history entry's actions in reverse, so the LAST
    // action recorded (n2, added to `dragStartPositions` after n1) restores
    // FIRST.
    const movesAfterUndo = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    expect(movesAfterUndo.length).toBe(movesBeforeUndo + 2)
    expect(movesAfterUndo.at(-2)).toEqual(['n2', { x: 300, y: 10 }])
    expect(movesAfterUndo.at(-1)).toEqual(['n1', { x: 10, y: 10 }])
    expect(undoBtn(w).attributes('disabled')).toBeDefined()
  })

  it('does not move a node that was never part of the selection', async () => {
    const w = mountCanvas()
    await node(w, 'n1').trigger('click') // n2 never joins — a lone selection.

    await dragNode1(w)

    const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    expect(moves.some(([id]) => id === 'n2')).toBe(false)
  })
})
