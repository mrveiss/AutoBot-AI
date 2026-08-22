// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14611: zoom-to-node, fit-to-selection/filter, and the inbound deep link's
 * own viewport jump.
 *
 * jsdom's `getBoundingClientRect` returns an all-zero rect unless mocked, so
 * every test here fixes the canvas area's on-screen size explicitly — without
 * it the pan/zoom math would be deterministic but meaningless (dividing by a
 * zero-sized viewport).
 *
 * `.canvas-content`'s own inline `transform` style is the one place pan/zoom
 * become observable from outside the component (there is no `defineExpose`),
 * so every assertion reads it rather than the internal `pan`/`zoom` refs.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import {
  CANVAS_NODE_WIDTH,
  CANVAS_NODE_HEIGHT,
  CANVAS_FIT_PADDING,
  type CanvasNode,
} from '../canvasNode'

// #14726: every expectation below derives from these rather than restating
// `240` / `100` / `60`. The old literals meant this suite would keep passing
// if `CANVAS_NODE_HEIGHT` changed and the fit-to-view code moved with it —
// the assertion would be checking the geometry the canvas no longer has.
const NODE_W = CANVAS_NODE_WIDTH
const NODE_H = CANVAS_NODE_HEIGHT
const PAD = CANVAS_FIT_PADDING * 2

const VIEW_WIDTH = 1000
const VIEW_HEIGHT = 700

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: VIEW_WIDTH,
    height: VIEW_HEIGHT,
    top: 0,
    left: 0,
    right: VIEW_WIDTH,
    bottom: VIEW_HEIGHT,
    x: 0,
    y: 0,
    toJSON() {
      return this
    },
  } as DOMRect)
})

afterEach(() => {
  vi.restoreAllMocks()
})

function node(id: string, x: number, y: number): CanvasNode {
  return {
    id,
    type: 'org-person',
    position: { x, y },
    data: { label: id, title: 'role' },
    connections: [],
  }
}

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(WorkflowCanvas, {
    props: { nodes: [node('a', 0, 0), node('b', 2000, 1000)], selectedNodeId: null, readonly: true, ...props },
    global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
}

/** Parses `.canvas-content`'s inline transform into { x, y, scale }. */
function transform(wrapper: ReturnType<typeof mountCanvas>): { x: number; y: number; scale: number } {
  const style = wrapper.get('.canvas-content').attributes('style') ?? ''
  const match = style.match(/translate\(([-\d.]+)px, ([-\d.]+)px\) scale\(([-\d.]+)\)/)
  if (!match) throw new Error(`could not parse transform from "${style}"`)
  return { x: Number(match[1]), y: Number(match[2]), scale: Number(match[3]) }
}

describe('reset stays fixed (#14611: a second control, not a change to it)', () => {
  it('resetZoom keeps its exact pan(50,50)/zoom(1), unaffected by the new fit button', async () => {
    const wrapper = mountCanvas()
    // Perturb the view first, so "reset" is actually observed doing something.
    await wrapper.get('[data-testid="canvas-fit-view"]').trigger('click')
    expect(transform(wrapper)).not.toEqual({ x: 50, y: 50, scale: 1 })

    await wrapper.get('.tool-btn[aria-label="Fit to view"]').trigger('click')
    expect(transform(wrapper)).toEqual({ x: 50, y: 50, scale: 1 })
  })
})

describe('fit to selection or filter (#14611)', () => {
  it('fits the selected node, clamped to ZOOM_MAX for a node this small on a 1000x700 view', async () => {
    // A single node, plus `CANVAS_FIT_PADDING` each side, fills far less than
    // the viewport — the fit would want to zoom in past 2x, so `clampZoom`'s
    // own ZOOM_MAX must win at the shipped geometry.
    const wrapper = mountCanvas({ selectedNodeId: 'a' })

    await wrapper.get('[data-testid="canvas-fit-view"]').trigger('click')

    const result = transform(wrapper)
    expect(result.scale).toBe(2)
    // Centred on node 'a' (at 0,0 → its own centre) at scale 2.
    expect(result.x).toBeCloseTo(VIEW_WIDTH / 2 - (NODE_W / 2) * 2, 5)
    expect(result.y).toBeCloseTo(VIEW_HEIGHT / 2 - (NODE_H / 2) * 2, 5)
  })

  it('fits every drawn node — which, when a filter has narrowed `nodes`, IS the filter — when nothing is selected', async () => {
    // Nodes 'a' (0,0) and 'b' (2000,1000): the box is the spread plus one
    // node's own extent on each axis.
    const wrapper = mountCanvas({ selectedNodeId: null })

    await wrapper.get('[data-testid="canvas-fit-view"]').trigger('click')

    const boxW = 2000 + NODE_W
    const boxH = 1000 + NODE_H
    const expectedScale = Math.min((VIEW_WIDTH - PAD) / boxW, (VIEW_HEIGHT - PAD) / boxH)
    const result = transform(wrapper)
    expect(result.scale).toBeCloseTo(expectedScale, 5)
    expect(result.x).toBeCloseTo(VIEW_WIDTH / 2 - (boxW / 2) * expectedScale, 5)
    expect(result.y).toBeCloseTo(VIEW_HEIGHT / 2 - (boxH / 2) * expectedScale, 5)
  })

  it('respects clampZoom\'s ZOOM_MIN floor rather than zooming out further for a huge spread', async () => {
    const wrapper = mountCanvas({
      nodes: [node('a', 0, 0), node('b', 100000, 60000)],
      selectedNodeId: null,
    })

    await wrapper.get('[data-testid="canvas-fit-view"]').trigger('click')

    expect(transform(wrapper).scale).toBe(0.3)
  })

  it('is reachable with an accessible label, and never gated on readonly', () => {
    const readonlyWrapper = mountCanvas({ readonly: true })
    const authoringWrapper = mountCanvas({ readonly: false })

    expect(readonlyWrapper.get('[data-testid="canvas-fit-view"]').attributes('aria-label')).toBe(
      en.workflow.canvas.fitToSelection,
    )
    expect(authoringWrapper.find('[data-testid="canvas-fit-view"]').exists()).toBe(true)
  })
})

describe('the inbound deep link\'s viewport jump (#14611 focus-node-id prop)', () => {
  it('zooms to FOCUS_ZOOM and centres on the named node once mounted', async () => {
    const wrapper = mountCanvas({ focusNodeId: 'a' })
    await nextTick()
    await nextTick()

    const result = transform(wrapper)
    expect(result.scale).toBe(1)
    expect(result.x).toBeCloseTo(VIEW_WIDTH / 2 - NODE_W / 2, 5)
    expect(result.y).toBeCloseTo(VIEW_HEIGHT / 2 - NODE_H / 2, 5)
  })

  it('is a no-op when the id names nothing currently drawn — never moves the viewport to nowhere', async () => {
    const wrapper = mountCanvas({ focusNodeId: 'does-not-exist' })
    await nextTick()
    await nextTick()

    // Left exactly at the component's own default — no jump attempted.
    expect(transform(wrapper)).toEqual({ x: 50, y: 50, scale: 1 })
  })

  it('moves keyboard focus onto the node too, for a screen-reader user landing on the link', async () => {
    const wrapper = mount(WorkflowCanvas, {
      props: {
        nodes: [node('a', 0, 0)],
        selectedNodeId: null,
        readonly: true,
        focusNodeId: 'a',
      },
      global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
      attachTo: document.body,
    })
    await nextTick()
    await nextTick()

    expect(wrapper.get('[data-node-id="a"]').element).toBe(document.activeElement)
  })
})
