// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14749: multi-select, marquee and the context menu were live on the readonly
 * Company OS org chart (`OrgChart.vue` mounts this canvas `readonly`), where
 * `node-selected` and the menu's detach actions reach real handlers. Each entry
 * point is asserted at the handler, once readonly and once not, so a gate that
 * is removed - or a new entry point that skips it - fails here.
 *
 * Deliberately NOT gated, and pinned by the process/tool detach tests: the
 * card's own detach buttons (an LLC action, not an authoring one).
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

const NODES: CanvasNode[] = [step('n1', 10, 10), step('n2', 300, 10)]
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountCanvas(readonly: boolean) {
  return mount(WorkflowCanvas, {
    props: { nodes: NODES, selectedNodeId: null, readonly },
    global: { plugins: [i18n] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const menu = (w: Wrapper) => w.find('[data-testid="canvas-context-menu"]')
const lastSelected = (w: Wrapper) => w.emitted('node-selected')?.at(-1)

describe('shift-click and shift-Enter toggle a multi-selection only when not readonly (#14749)', () => {
  it.each([
    ['click', (w: Wrapper) => node(w, 'n2').trigger('click', { shiftKey: true })],
    ['Enter', (w: Wrapper) => node(w, 'n2').trigger('keydown', { key: 'Enter', shiftKey: true })],
  ])('shift+%s', async (_label, shiftActivate) => {
    const editable = mountCanvas(false)
    await node(editable, 'n1').trigger('click')
    await shiftActivate(editable)
    expect(editable.find('[data-testid="canvas-selection-status"]').exists()).toBe(true)
    expect(node(editable, 'n2').classes()).toContain('multi-selected')
    expect(lastSelected(editable)).toEqual([null]) // two selected: no single node

    const readonly = mountCanvas(true)
    await node(readonly, 'n1').trigger('click')
    await shiftActivate(readonly)
    expect(readonly.find('[data-testid="canvas-selection-status"]').exists()).toBe(false) // never more than one
    expect(lastSelected(readonly)).toEqual(['n2']) // a plain selection, as an unmodified click
  })
})

describe('a left-press on empty canvas starts a marquee only when not readonly (#14749)', () => {
  async function drag(w: Wrapper): Promise<void> {
    const area = w.get('.canvas-area').element
    await firePointer(area, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
    await firePointer(area, 'pointermove', { clientX: 20, clientY: 20 })
    await firePointer(area, 'pointermove', { clientX: 400, clientY: 200 })
  }

  it('draws the rectangle and selects when editable', async () => {
    const w = mountCanvas(false)
    await drag(w)
    expect(w.find('[data-testid="canvas-marquee"]').exists()).toBe(true)
    expect(node(w, 'n1').classes()).toContain('multi-selected')
  })

  it('draws nothing and selects nothing when readonly', async () => {
    const w = mountCanvas(true)
    await drag(w)
    expect(w.find('[data-testid="canvas-marquee"]').exists()).toBe(false)
    expect(node(w, 'n1').classes()).not.toContain('multi-selected')
    expect(w.emitted('node-selected')).toBeUndefined()
  })
})

describe('the context menu opens only when not readonly (#14749)', () => {
  const entryPoints: [string, (w: Wrapper) => Promise<unknown>][] = [
    ['right-click', (w) => node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })],
    ['the ContextMenu key', (w) => node(w, 'n1').trigger('keydown', { key: 'ContextMenu' })],
    ['Shift+F10', (w) => node(w, 'n1').trigger('keydown', { key: 'F10', shiftKey: true })],
    ['the node menu button', (w) => node(w, 'n1').get('[data-testid="node-menu-btn"]').trigger('click')],
  ]

  it.each(entryPoints)('%s opens the menu when editable', async (_label, open) => {
    const w = mountCanvas(false)
    await open(w)
    expect(menu(w).exists()).toBe(true)
  })

  it.each(entryPoints.slice(0, 3))('%s opens nothing when readonly', async (_label, open) => {
    const w = mountCanvas(true)
    await open(w)
    expect(menu(w).exists()).toBe(false)
    expect(w.emitted('node-selected')).toBeUndefined()
  })

  it('the node menu button is not rendered when readonly', () => {
    expect(mountCanvas(true).find('[data-testid="node-menu-btn"]').exists()).toBe(false)
    expect(mountCanvas(false).find('[data-testid="node-menu-btn"]').exists()).toBe(true)
  })
})
