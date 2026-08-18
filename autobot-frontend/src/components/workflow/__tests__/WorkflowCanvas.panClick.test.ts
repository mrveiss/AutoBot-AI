// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14079: every shift-drag pan that started on a node ended with that node's
// drawer open over the canvas the user had just panned.
//
// A pan translates the canvas by the pointer delta, so the node the gesture
// started on stays under the cursor. `mouseup` lands on it, the browser fires
// `click`, and `@click.stop="selectNode(node.id)"` emits `node-selected`.
//
// The suppression has to be narrow in two directions, and both are asserted
// here: a shift-click that never moves is still a selection, and a pan that
// ends over empty canvas must not swallow the user's NEXT click on a node.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

const NODES: CanvasNode[] = [
  {
    id: 'ceo',
    type: 'org-person',
    position: { x: 40, y: 40 },
    data: { title: 'Ada', rule: 'idle' },
    connections: [],
  },
]

function mountCanvas() {
  const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
  return mount(WorkflowCanvas, {
    props: { nodes: NODES, selectedNodeId: null, readonly: true },
    global: { plugins: [i18n] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>

const node = (w: Wrapper) => w.find('.workflow-node')
const area = (w: Wrapper) => w.find('.canvas-area')
const selections = (w: Wrapper) => w.emitted('node-selected') ?? []

/** Shift-drag from `from` to `to`, starting on whichever element is given. */
async function panFrom(w: Wrapper, start: ReturnType<typeof node>, dx: number): Promise<void> {
  await start.trigger('mousedown', { shiftKey: true, clientX: 100, clientY: 100, button: 0 })
  await area(w).trigger('mousemove', { clientX: 100 + dx, clientY: 100 + dx })
  await area(w).trigger('mouseup', { clientX: 100 + dx, clientY: 100 + dx })
}

describe('a pan gesture is not a selection (#14079)', () => {
  it('does not select the node a pan started on', async () => {
    const w = mountCanvas()
    await panFrom(w, node(w), 70)
    // The click the browser fires when the pointer comes up over the node.
    await node(w).trigger('click')

    expect(selections(w)).toHaveLength(0)
  })

  it('still selects on a plain click', async () => {
    const w = mountCanvas()
    await node(w).trigger('mousedown', { clientX: 100, clientY: 100, button: 0 })
    await node(w).trigger('mouseup', { clientX: 100, clientY: 100 })
    await node(w).trigger('click')

    expect(selections(w)).toEqual([['ceo']])
  })

  it('still selects on a shift-click that never moves', async () => {
    // Shift is the pan modifier, but a press that does not move is not a pan.
    // Keying the suppression on the modifier instead of on movement would
    // silently make shift-click stop working.
    const w = mountCanvas()
    await node(w).trigger('mousedown', { shiftKey: true, clientX: 100, clientY: 100, button: 0 })
    await node(w).trigger('mouseup', { clientX: 100, clientY: 100 })
    await node(w).trigger('click')

    expect(selections(w)).toEqual([['ceo']])
  })

  it('does not swallow the click after a pan that ended on empty canvas', async () => {
    // The failure mode of clearing the flag on the click it suppresses: this
    // pan is followed by no node click at all, so the flag would still be set
    // when the user next clicks a node.
    const w = mountCanvas()
    await area(w).trigger('mousedown', { shiftKey: true, clientX: 10, clientY: 10, button: 0 })
    await area(w).trigger('mousemove', { clientX: 90, clientY: 90 })
    await area(w).trigger('mouseup', { clientX: 90, clientY: 90 })

    await node(w).trigger('mousedown', { clientX: 100, clientY: 100, button: 0 })
    await node(w).trigger('click')

    expect(selections(w)).toEqual([['ceo']])
  })
})
