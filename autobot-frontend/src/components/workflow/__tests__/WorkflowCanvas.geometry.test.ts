// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14690: the renderer computed edge anchors from bare literals (240, 50, 100)
// while the layout builders used CANVAS_NODE_WIDTH. Two sources for one fact,
// agreeing only by coincidence — change the constant and every node moves
// while every edge stays anchored to the old width.
//
// A test cannot catch a literal-vs-constant swap while the two values happen
// to be equal; that is exactly why this was debt rather than a bug. What a
// test CAN pin is the relationship: an edge must start at the node's trailing
// edge and at its mid-line, expressed in terms of the constants, so that
// changing a constant moves the assertion with it.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import WorkflowCanvas from '../WorkflowCanvas.vue'
import { CANVAS_NODE_WIDTH, CANVAS_NODE_HEIGHT, CANVAS_NODE_PORT_Y } from '../canvasNode'
import type { CanvasNode } from '../canvasNode'

const SOURCE = { x: 100, y: 200 }
const TARGET = { x: 700, y: 500 }

const NODES: CanvasNode[] = [
  { id: 'a', type: 'step', position: { ...SOURCE }, data: { label: 'A' }, connections: ['b'] },
  { id: 'b', type: 'step', position: { ...TARGET }, data: { label: 'B' }, connections: [] },
]

function mountCanvas(readonly = true) {
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  return mount(WorkflowCanvas, {
    props: { nodes: NODES, selectedNodeId: null, readonly },
    global: { plugins: [i18n] },
  })
}

describe('canvas edge geometry derives from the shared constants (#14690)', () => {
  it('anchors an edge at the source node trailing edge and mid-line', () => {
    const path = mountCanvas().find('path.connection-line').attributes('d') ?? ''

    // Expressed via the constants, never as 340/250 — so if a constant
    // changes, this assertion changes with it instead of silently passing
    // against stale geometry.
    expect(path).toContain(`M${SOURCE.x + CANVAS_NODE_WIDTH},${SOURCE.y + CANVAS_NODE_PORT_Y}`)
  })

  it('lands the edge on the target node leading edge and mid-line', () => {
    const path = mountCanvas().find('path.connection-line').attributes('d') ?? ''

    expect(path).toContain(`${TARGET.x},${TARGET.y + CANVAS_NODE_PORT_Y}`)
  })

  it('keeps the port anchored at exactly half the node height', () => {
    // The relationship that was previously two independent literals. If
    // someone reintroduces a standalone 50, this is what catches the drift
    // the moment the height changes.
    expect(CANVAS_NODE_PORT_Y).toBe(CANVAS_NODE_HEIGHT / 2)
  })

  it('starts the drag line at the source node trailing edge, not a literal', async () => {
    // #14690 review: this anchor kept a bare 240 while the line directly below
    // it was converted, and nothing exercised `startConnect`, so the gap was
    // invisible. The drag line and the rendered edge must leave the node at
    // the same place — that is the property, and it is what breaks when only
    // one of the two reads the constant.
    const wrapper = mountCanvas(false)

    await wrapper.findAll('.port-out')[0].trigger('pointerdown')

    const path = wrapper.find('path.drawing-line').attributes('d') ?? ''
    expect(path).toContain(`M${SOURCE.x + CANVAS_NODE_WIDTH},${SOURCE.y + CANVAS_NODE_PORT_Y}`)
  })

  it('starts the drag line at the node leading edge for an inbound port', async () => {
    // The `port === 'out'` branch offsets by the width; the other branch must
    // stay at the node's own x, so the width constant applies to exactly one
    // of the two.
    const wrapper = mountCanvas(false)

    await wrapper.findAll('.port-in')[0].trigger('pointerdown')

    const path = wrapper.find('path.drawing-line').attributes('d') ?? ''
    expect(path).toContain(`M${SOURCE.x},${SOURCE.y + CANVAS_NODE_PORT_Y}`)
  })
})
