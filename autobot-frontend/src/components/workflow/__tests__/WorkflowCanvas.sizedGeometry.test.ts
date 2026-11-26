// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14008: edge anchors and the connection-drop hit test read a node's own
 * extent (a sized org-group carries data.width/height) instead of assuming
 * the default 240x100 box.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import { CANVAS_NODE_WIDTH, CANVAS_NODE_PORT_Y } from '../canvasNode'
import type { CanvasNode } from '../canvasNode'
import { firePointer } from './pointerTestUtils'

const SIZED = { width: 900, height: 480 }
const small = (id: string, x: number, y: number, connections: string[] = []): CanvasNode => ({
  id, type: 'step', position: { x, y }, data: { label: id }, connections,
})
const sized = (id: string, x: number, y: number, connections: string[] = []): CanvasNode => ({
  id, type: 'org-group', position: { x, y }, data: { label: id, ...SIZED }, connections,
})
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountCanvas = (nodes: CanvasNode[], readonly = true) =>
  mount(WorkflowCanvas, { props: { nodes, selectedNodeId: null, readonly }, global: { plugins: [i18n] } })

describe('edges anchor on the real extent of a sized node (#14008)', () => {
  it('leaves a sized source at its own trailing edge and mid-line', () => {
    const d = mountCanvas([sized('a', 100, 200, ['b']), small('b', 1500, 200)]).get('path.connection-line').attributes('d') ?? ''
    expect(d).toContain(`M${100 + SIZED.width},${200 + SIZED.height / 2}`)
    expect(d).toContain(`1500,${200 + CANVAS_NODE_PORT_Y}`)
  })

  it('keeps the default box for an unsized node', () => {
    const d = mountCanvas([small('a', 100, 200, ['b']), small('b', 700, 500)]).get('path.connection-line').attributes('d') ?? ''
    expect(d).toContain(`M${100 + CANVAS_NODE_WIDTH},${200 + CANVAS_NODE_PORT_Y}`)
  })
})

describe('a connection dropped on a tall sized node hits it (#14008)', () => {
  // pan defaults to (50, 50), zoom 1, and jsdom rects are at the origin, so a
  // pointer at client (x + 50, y + 50) is canvas point (x, y).
  async function drop(target: CanvasNode, canvasY: number) {
    const w = mountCanvas([small('src', 0, 0), target], false)
    await firePointer(w.get('[data-node-id="src"] .port-out').element, 'pointerdown', { clientX: 50, clientY: 50 })
    await firePointer(w.get('.canvas-area').element, 'pointerup', { clientX: 400 + 50, clientY: canvasY + 50 })
    return w.emitted('nodes-connected')
  }

  it('connects when the drop is below the old 100px box but inside the real height', async () => {
    expect(await drop(sized('big', 300, 0), 300)).toEqual([['src', 'big']])
  })

  it('does not connect when the drop is below the real height', async () => {
    expect(await drop(sized('big', 300, 0), SIZED.height + 50)).toBeUndefined()
  })
})
