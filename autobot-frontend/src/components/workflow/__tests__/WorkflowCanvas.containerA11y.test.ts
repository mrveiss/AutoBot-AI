// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14687: an org-group container is a backdrop nothing can open, so it must
 * not present as an activatable control: not a button, not a Tab stop, no
 * pressed state, and mouse / keyboard / context menu all agree.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

const NODES: CanvasNode[] = [
  { id: 'org-group:r', type: 'org-group', position: { x: 0, y: 0 }, data: { label: 'Unit', width: 600, height: 400 }, connections: [] },
  { id: 'p1', type: 'org-person', position: { x: 20, y: 60 }, data: { label: 'Ada', title: 'CTO' }, connections: [] },
]
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountCanvas = () =>
  mount(WorkflowCanvas, { props: { nodes: NODES, selectedNodeId: null, readonly: true }, global: { plugins: [i18n] } })
const node = (w: ReturnType<typeof mountCanvas>, id: string) => w.get(`[data-node-id="${id}"]`)

describe('container nodes do not advertise an action they lack (#14687)', () => {
  it('is a labelled group, not a button, with no pressed state', () => {
    const el = node(mountCanvas(), 'org-group:r')
    expect(el.attributes('role')).toBe('group')
    expect(el.attributes('aria-pressed')).toBeUndefined()
    expect(el.attributes('aria-label')).toBeTruthy()
  })

  it('is never the Tab stop, even when it is first in reading order', () => {
    const w = mountCanvas()
    expect(node(w, 'org-group:r').attributes('tabindex')).toBe('-1')
    expect(node(w, 'p1').attributes('tabindex')).toBe('0')
    expect(node(w, 'p1').attributes('role')).toBe('button')
  })

  it('does nothing on click or Enter: no selection, no node-selected emit', async () => {
    const w = mountCanvas()
    await node(w, 'org-group:r').trigger('click')
    await node(w, 'org-group:r').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('node-selected')).toBeUndefined()
    expect(node(w, 'org-group:r').classes()).not.toContain('selected')
  })

  it('opens the menu without selecting the container, offering only real actions', async () => {
    const w = mountCanvas()
    await node(w, 'org-group:r').trigger('contextmenu', { clientX: 5, clientY: 5 })
    expect(w.emitted('node-selected')).toBeUndefined()
    expect(w.find('[data-testid="canvas-context-menu-item-select"]').exists()).toBe(false)
    expect(w.find('[data-testid="canvas-context-menu-item-zoom"]').exists()).toBe(true)
  })

  it('keeps its ContextMenu / Shift+F10 and Escape keys when focused', async () => {
    const w = mountCanvas()
    for (const init of [{ key: 'ContextMenu' }, { key: 'F10', shiftKey: true }]) {
      await node(w, 'org-group:r').trigger('keydown', init)
      expect(w.find('[data-testid="canvas-context-menu-item-zoom"]').exists()).toBe(true)
      await w.get('[data-testid="canvas-context-menu"]').trigger('keydown', { key: 'Escape' })
    }
    await node(w, 'p1').trigger('click')
    expect(node(w, 'p1').attributes('aria-pressed')).toBe('true')
    await node(w, 'org-group:r').trigger('keydown', { key: 'Escape' })
    expect(node(w, 'p1').attributes('aria-pressed')).toBe('false')
    expect(w.emitted('node-selected')?.at(-1)).toEqual([null])
  })

  it('arrow navigation from a person never lands on a container', async () => {
    const w = mountCanvas()
    await node(w, 'p1').trigger('keydown', { key: 'ArrowLeft' })
    expect(w.emitted('node-selected')).toBeUndefined()
    expect(node(w, 'p1').attributes('tabindex')).toBe('0')
  })
})
