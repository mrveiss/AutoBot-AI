// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14749: the Company OS org chart mounts this canvas `readonly`. The context
 * menu stays reachable there - it is how per-node zoom, open-workflow and
 * fit-selection are reached - but offers only view actions. The mutating ones
 * (`delete`, `detach-process`, `detach-tool-*`) are not offered, so a menu
 * trigger can never reach `process-detached` / `tool-detached` from a readonly
 * canvas. Multi-select and marquee stay live on readonly because fit-selection,
 * a view action, needs a multi-selection and they are its only route to one.
 *
 * Each entry point is asserted once readonly and once not. Adding an action
 * means classifying it in `VIEW_ACTIONS` / `isMutating` below.
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
import { buildProcessCanvasNodes, buildToolCanvasNodes } from '@/composables/llc/orgCanvasGraph'

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

function mountCanvas(readonly: boolean, nodes: CanvasNode[] = NODES) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null, readonly },
    global: { plugins: [i18n] },
  })
}

type Wrapper = ReturnType<typeof mountCanvas>
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const menu = (w: Wrapper) => w.find('[data-testid="canvas-context-menu"]')
const item = (w: Wrapper, id: string) => w.find(`[data-testid="canvas-context-menu-item-${id}"]`)
const itemIds = (w: Wrapper) =>
  w
    .findAll('[role="menuitem"]')
    .map((el) => (el.attributes('data-testid') ?? '').replace('canvas-context-menu-item-', ''))

const VIEW_ACTIONS = ['select', 'open-workflow', 'zoom', 'fit-selection']
const isMutating = (id: string) => id === 'delete' || id === 'detach-process' || id.startsWith('detach-tool-')

const PROCESS = buildProcessCanvasNodes([{ role_id: 'role-1', role_name: 'Head of Ops', workflow_id: 'wf-1' }], 0)
const TOOL = buildToolCanvasNodes(
  [
    { role_id: 'role-1', role_name: 'Head of Ops', tool_name: 'web_search' },
    { role_id: 'role-2', role_name: 'SRE', tool_name: 'web_search' },
  ],
  [],
  0,
)

describe('the context menu opens on every entry point, readonly or not (#14749)', () => {
  const entryPoints: [string, (w: Wrapper) => Promise<unknown>][] = [
    ['right-click', (w) => node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })],
    ['the ContextMenu key', (w) => node(w, 'n1').trigger('keydown', { key: 'ContextMenu' })],
    ['Shift+F10', (w) => node(w, 'n1').trigger('keydown', { key: 'F10', shiftKey: true })],
    ['the node menu button', (w) => node(w, 'n1').get('[data-testid="node-menu-btn"]').trigger('click')],
  ]

  it.each(entryPoints)('%s opens the full menu when editable', async (_label, open) => {
    const w = mountCanvas(false)
    await open(w)
    expect(menu(w).exists()).toBe(true)
    expect(item(w, 'delete').exists()).toBe(true)
  })

  it.each(entryPoints)('%s opens the view-only menu when readonly', async (_label, open) => {
    const w = mountCanvas(true)
    await open(w)
    expect(menu(w).exists()).toBe(true)
    expect(itemIds(w)).toEqual(['select', 'zoom'])
  })
})

describe('no mutating action appears on a readonly canvas (#14749)', () => {
  const cases: [string, CanvasNode[]][] = [
    ['a step node', NODES],
    ['an org-process node', PROCESS],
    ['an org-tool node with two roles', TOOL],
  ]

  it.each(cases)('%s: readonly offers view actions only', async (_label, nodes) => {
    const w = mountCanvas(true, nodes)
    await node(w, nodes[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    const ids = itemIds(w)
    expect(ids.length).toBeGreaterThan(0)
    expect(ids.filter(isMutating)).toEqual([])
    for (const id of ids) expect(VIEW_ACTIONS).toContain(id)
  })

  it.each(cases)('%s: the same node offers its mutation when editable', async (_label, nodes) => {
    const w = mountCanvas(false, nodes)
    await node(w, nodes[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    expect(itemIds(w).filter(isMutating).length).toBeGreaterThan(0)
  })

  it('a readonly org-process menu still opens the workflow and emits no detach', async () => {
    const w = mountCanvas(true, PROCESS)
    await node(w, PROCESS[0].id).trigger('contextmenu', { clientX: 10, clientY: 10 })
    expect(itemIds(w)).toEqual(['open-workflow', 'zoom'])
    await item(w, 'open-workflow').trigger('click')
    expect(w.emitted('node-selected')?.at(-1)).toEqual([PROCESS[0].id])
    expect(w.emitted('process-detached')).toBeUndefined()
  })
})

describe('a multi-selection stays reachable on readonly, for fit-selection (#14749)', () => {
  it.each([
    ['click', (w: Wrapper) => node(w, 'n2').trigger('click', { shiftKey: true })],
    ['Enter', (w: Wrapper) => node(w, 'n2').trigger('keydown', { key: 'Enter', shiftKey: true })],
  ])('shift+%s multi-selects, readonly or not', async (_label, shiftActivate) => {
    for (const readonly of [false, true]) {
      const w = mountCanvas(readonly)
      await node(w, 'n1').trigger('click')
      await shiftActivate(w)
      expect(node(w, 'n2').classes()).toContain('multi-selected')
    }
  })

  it('fit-selection is offered on readonly for a multi-selection, and delete is not', async () => {
    const w = mountCanvas(true)
    await node(w, 'n1').trigger('click')
    await node(w, 'n2').trigger('click', { shiftKey: true })
    await node(w, 'n1').trigger('contextmenu', { clientX: 10, clientY: 10 })
    expect(itemIds(w)).toEqual(['select', 'zoom', 'fit-selection'])
  })

  it('a left-press drag on empty canvas draws the marquee and selects, readonly or not', async () => {
    for (const readonly of [false, true]) {
      const w = mountCanvas(readonly)
      const area = w.get('.canvas-area').element
      await firePointer(area, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
      await firePointer(area, 'pointermove', { clientX: 20, clientY: 20 })
      await firePointer(area, 'pointermove', { clientX: 400, clientY: 200 })
      expect(w.find('[data-testid="canvas-marquee"]').exists()).toBe(true)
      expect(node(w, 'n1').classes()).toContain('multi-selected')
    }
  })
})
