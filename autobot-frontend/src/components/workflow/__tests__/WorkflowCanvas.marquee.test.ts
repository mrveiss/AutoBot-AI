// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14612: marquee (rubber-band) selection — `marqueeAnchor`/`marqueeCurrent`/
 * `marqueePending`/`marqueeActive`/`startMarquee`/`marqueeStyle` were
 * implemented and never exercised by a test. This covers:
 *   - a left-press-and-drag starting on genuinely empty canvas draws the
 *     rectangle and selects exactly the nodes it overlaps.
 *   - a press starting ON a node is a drag, never a marquee — the marquee
 *     rectangle must never appear and the node must still move normally.
 *   - a marquee gesture is not a selection click (#14079/#14610's own
 *     `movedThisGesture` suppression) — the browser's synthesized `click`,
 *     which pointer capture does NOT retarget, can still land on whichever
 *     node the drag ends over, and must not be allowed to collapse the
 *     marquee's own multi-selection down to just that node.
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

// Canvas mounts with the default pan (50, 50) and zoom (1), and jsdom's
// `getBoundingClientRect` returns an all-zero rect for `.canvas-area` — so a
// node's on-screen box is `(50 + x, 50 + y)` to `(50 + x + 240, 50 + y + 100)`
// (240x100 is `CANVAS_NODE_WIDTH`/the fixed node footprint).
const NODES: CanvasNode[] = [
  step('n1', 10, 10), // screen (60,60)-(300,160)
  step('n2', 300, 10), // screen (350,60)-(590,160)
  step('n3', 900, 900), // screen (950,950)-(1190,1050) — well outside the marquee below
]

function mountCanvas(nodes: CanvasNode[] = NODES) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null },
    global: { plugins: [createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const area = (w: Wrapper) => w.get('.canvas-area')
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const marqueeEl = (w: Wrapper) => w.find('[data-testid="canvas-marquee"]')

describe('a marquee drag on empty canvas selects the nodes it overlaps (#14612)', () => {
  it('draws the rectangle and selects only the nodes inside it', async () => {
    const w = mountCanvas()

    await firePointer(area(w).element, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
    expect(marqueeEl(w).exists()).toBe(false) // not yet past the move threshold

    await firePointer(area(w).element, 'pointermove', { clientX: 20, clientY: 20 })
    expect(marqueeEl(w).exists()).toBe(true)

    await firePointer(area(w).element, 'pointermove', { clientX: 400, clientY: 200 })
    expect(marqueeEl(w).attributes('style')).toContain('width: 400px')
    expect(marqueeEl(w).attributes('style')).toContain('height: 200px')

    // n1 and n2 both intersect the (0,0)-(400,200) screen rectangle; n3 does
    // not (it sits at screen (950,950)+, far outside).
    expect(node(w, 'n1').classes()).toContain('multi-selected')
    expect(node(w, 'n2').classes()).toContain('multi-selected')
    expect(node(w, 'n3').classes()).not.toContain('multi-selected')

    await firePointer(area(w).element, 'pointerup', { clientX: 400, clientY: 200 })

    expect(marqueeEl(w).exists()).toBe(false)
    expect(w.emitted('node-selected')?.at(-1)).toEqual([null]) // 2 selected — no single node to open
  })

  it('selects nothing and never draws a rectangle for a plain click with no movement', async () => {
    const w = mountCanvas()

    await firePointer(area(w).element, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
    await firePointer(area(w).element, 'pointerup', { clientX: 0, clientY: 0 })

    expect(marqueeEl(w).exists()).toBe(false)
    expect(node(w, 'n1').classes()).not.toContain('multi-selected')
    expect(w.emitted('node-selected')).toBeUndefined()
  })
})

describe('a press starting on a node is a drag, never a marquee (#14612)', () => {
  it('never shows the marquee rectangle while dragging a node', async () => {
    const w = mountCanvas()

    await firePointer(node(w, 'n1').element, 'pointerdown', { clientX: 100, clientY: 100, button: 0 })
    await firePointer(node(w, 'n1').element, 'pointermove', { clientX: 140, clientY: 100 })
    expect(marqueeEl(w).exists()).toBe(false)

    await firePointer(area(w).element, 'pointerup', { clientX: 140, clientY: 100 })
    expect(marqueeEl(w).exists()).toBe(false)

    // The drag itself still worked normally.
    const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    expect(moves.some(([id]) => id === 'n1')).toBe(true)
  })
})

describe('a marquee gesture is not a selection click (#14079/#14610/#14612)', () => {
  it('does not let a click that lands on a node after the drag collapse the marquee selection', async () => {
    // Reproduces the real browser sequence: `capturePointer` retargets
    // `pointerup` to `.canvas-area`, but NOT the `click` the browser
    // synthesizes afterwards — that still hit-tests normally and can land on
    // whichever node the pointer physically ended over. The marquee already
    // selected n1 and n2 live in `onPointerMove`; a click reaching a node
    // afterwards must be suppressed exactly like a pan/drag's own click is.
    const w = mountCanvas()

    await firePointer(area(w).element, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
    await firePointer(area(w).element, 'pointermove', { clientX: 20, clientY: 20 })
    await firePointer(area(w).element, 'pointermove', { clientX: 400, clientY: 200 })
    await firePointer(area(w).element, 'pointerup', { clientX: 400, clientY: 200 })
    expect(node(w, 'n1').classes()).toContain('multi-selected')
    expect(node(w, 'n2').classes()).toContain('multi-selected')
    expect(w.emitted('node-selected')).toHaveLength(1)

    // The browser's synthesized click, landing on n1 (which sits under the
    // point the drag ended at).
    await node(w, 'n1').trigger('click')

    // Still both selected — the click must have been suppressed, not treated
    // as a fresh plain-click replacing the whole selection with just n1.
    expect(node(w, 'n1').classes()).toContain('multi-selected')
    expect(node(w, 'n2').classes()).toContain('multi-selected')
    expect(w.emitted('node-selected')).toHaveLength(1)
  })
})
