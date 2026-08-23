// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The canvas grid: does it describe the plane the nodes sit on, and do nodes
 * land on it?
 *
 * #14765 — the grid was painted on `.canvas-area` (the fixed viewport) while
 *   the pan/zoom transform lives on its child `.canvas-content`, so it
 *   neither panned nor zoomed. At 2x the squares stayed 20 screen px while
 *   every node doubled. Nothing compensated, and no test could tell.
 * #14768 — a 20px grid was drawn and then ignored: dragged positions were
 *   arbitrary floats, so a hand-arranged graph never aligned to the grid the
 *   user was looking at.
 * #14726 — the node width the browser rendered lived in the CSS, and every
 *   TypeScript computation was an attempt to predict it.
 *
 * These assert the *rendered* metrics and the *emitted* positions, not the
 * constants — a test that reads `CANVAS_GRID_SIZE` back out of the module it
 * came from proves nothing about what the canvas does with it.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import { CANVAS_GRID_SIZE, CANVAS_NODE_WIDTH, type CanvasNode } from '../canvasNode'
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
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(WorkflowCanvas, {
    props: {
      nodes: [step('n1', 10, 10), step('n2', 300, 10)],
      selectedNodeId: null,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

/** The grid metrics as rendered onto `.canvas-area` by `canvasGridStyle`. */
function gridMetrics(w: ReturnType<typeof mountCanvas>) {
  const el = w.get('.canvas-area').element as HTMLElement
  return { size: el.style.backgroundSize, origin: el.style.backgroundPosition }
}

/** The leading number of a CSS length, so assertions are float-tolerant. */
function px(value: string): number {
  return Number.parseFloat(value)
}

/** The `scale()` factor currently applied to `.canvas-content`. */
function scaleOf(w: ReturnType<typeof mountCanvas>): number {
  const transform = w.get('.canvas-content').attributes('style') ?? ''
  return Number.parseFloat(/scale\(([\d.]+)\)/.exec(transform)?.[1] ?? 'NaN')
}

/**
 * Drag n1 by (dx, dy) screen px and return the last emitted position.
 * `altKey` exercises the free-placement bypass.
 */
async function dragN1(
  w: ReturnType<typeof mountCanvas>,
  dx: number,
  dy: number,
  modifiers: Record<string, unknown> = {},
) {
  const node = w.get('[data-node-id="n1"]')
  await firePointer(node.element, 'pointerdown', { clientX: 100, clientY: 100, button: 0, ...modifiers })
  await firePointer(w.get('.canvas-area').element, 'pointermove', {
    clientX: 100 + dx, clientY: 100 + dy, ...modifiers,
  })
  await firePointer(w.get('.canvas-area').element, 'pointerup', {
    clientX: 100 + dx, clientY: 100 + dy, ...modifiers,
  })
  const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][] | undefined
  return moves?.filter(([id]) => id === 'n1').at(-1)?.[1]
}

describe('the grid is world content, not chrome (#14765)', () => {
  it('binds its pitch and origin to the camera rather than to the viewport', () => {
    const w = mountCanvas()

    // At the default zoom of 1 and the default pan of (50, 50), the grid pitch
    // is one cell and the origin sits at the pan offset.
    const { size, origin } = gridMetrics(w)
    expect(px(size)).toBeCloseTo(CANVAS_GRID_SIZE, 5)
    expect(origin).toBe('50px 50px')
  })

  it('scales its pitch with zoom, so a cell keeps covering one cell of world', async () => {
    const w = mountCanvas()

    await w.get('.tool-btn[aria-label="Zoom in"]').trigger('click')

    const scale = scaleOf(w)

    expect(scale).toBeGreaterThan(1)
    // The pitch the grid renders at must be the world pitch through the same
    // scale the nodes went through — otherwise the grid stops describing the
    // plane they sit on, which is the whole defect.
    expect(px(gridMetrics(w).size)).toBeCloseTo(CANVAS_GRID_SIZE * scale, 5)
  })

  it('moves its origin with the pan', async () => {
    const w = mountCanvas()
    const area = w.get('.canvas-area')

    await firePointer(area.element, 'pointerdown', { clientX: 100, clientY: 100, shiftKey: true, button: 0 })
    await firePointer(area.element, 'pointermove', { clientX: 220, clientY: 130, shiftKey: true })
    await firePointer(area.element, 'pointerup', { clientX: 220, clientY: 130, shiftKey: true })

    // Pan started at (50, 50) and the gesture moved (+120, +30).
    expect(w.get('.canvas-content').attributes('style')).toContain('translate(170px, 80px)')
    expect(gridMetrics(w).origin).toBe('170px 80px')
  })
})

describe('the CSS reads its geometry from the constants (#14726)', () => {
  it('renders node width from CANVAS_NODE_WIDTH rather than a CSS literal', () => {
    const w = mountCanvas()

    const node = w.get('[data-node-id="n1"]').element as HTMLElement
    expect(node.style.width).toBe(`${CANVAS_NODE_WIDTH}px`)
  })
})

describe('dragging snaps to the grid (#14768)', () => {
  it('lands a dragged node on a grid multiple', async () => {
    const w = mountCanvas()

    // n1 starts at x=10 (off-grid) and the pointer moves +33px, so the raw
    // drop is x=43 — a value no gridline sits on.
    const pos = await dragN1(w, 33, 0)

    expect(pos).toBeDefined()
    expect(pos!.x % CANVAS_GRID_SIZE).toBe(0)
    expect(pos!.y % CANVAS_GRID_SIZE).toBe(0)
  })

  it('does NOT snap while Alt is held — the grid is a default, not a cage', async () => {
    const w = mountCanvas()

    const pos = await dragN1(w, 33, 0, { altKey: true })

    expect(pos).toEqual({ x: 43, y: 10 })
  })

  it('keeps a multi-selection rigid: the followers move by the leader\'s snapped delta', async () => {
    const w = mountCanvas()
    await w.get('[data-node-id="n1"]').trigger('click')
    await w.get('[data-node-id="n2"]').trigger('click', { shiftKey: true })

    await dragN1(w, 33, 0)

    const moves = w.emitted('node-moved') as unknown as [string, { x: number; y: number }][]
    const n1 = moves.filter(([id]) => id === 'n1').at(-1)![1]
    const n2 = moves.filter(([id]) => id === 'n2').at(-1)![1]

    // #14612's invariant survives snapping: n2 moved by exactly the delta the
    // snapped leader moved, from its own start (300, 10) — NOT by its own
    // independent snap, which would deform the selection.
    expect(n2.x - 300).toBe(n1.x - 10)
    expect(n2.y - 10).toBe(n1.y - 10)
  })
})

describe('keyboard moves align to the grid (#14768)', () => {
  it('aligns an off-grid node to the ADJACENT gridline, not a full step past it', async () => {
    const w = mountCanvas({ nodes: [step('n1', 10, 10)] })

    await w.get('[data-node-id="n1"]').trigger('keydown', { key: 'ArrowRight', ctrlKey: true })

    // From x=10 the next line is 20. `snapToGrid(10 + 20)` would have said 40,
    // skipping the line the press was reaching for.
    expect(w.emitted('node-moved')).toEqual([['n1', { x: 20, y: 10 }]])
  })

  it('advances exactly one cell once aligned', async () => {
    const w = mountCanvas({ nodes: [step('n1', 20, 20)] })

    await w.get('[data-node-id="n1"]').trigger('keydown', { key: 'ArrowRight', ctrlKey: true })

    expect(w.emitted('node-moved')).toEqual([['n1', { x: 20 + CANVAS_GRID_SIZE, y: 20 }]])
  })

  it('leaves the idle axis alone — a horizontal press never re-aligns y', async () => {
    const w = mountCanvas({ nodes: [step('n1', 20, 13)] })

    await w.get('[data-node-id="n1"]').trigger('keydown', { key: 'ArrowRight', ctrlKey: true })

    expect(w.emitted('node-moved')).toEqual([['n1', { x: 40, y: 13 }]])
  })
})
