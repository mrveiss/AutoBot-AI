// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13939: the canvas grew a read-only mode, a tab strip and two org node
// types so Company OS can draw its org graph on it. The workflow authoring
// behaviour must be untouched when the new props are absent, and horizontal
// panning must behave identically in an RTL locale — the canvas pans with a
// CSS transform, so an RTL document must not mirror it.

import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

const ORG_NODES: CanvasNode[] = [
  {
    id: 'org-group:ceo',
    type: 'org-group',
    position: { x: 0, y: 0 },
    data: { label: 'Ada unit', width: 600, height: 320 },
    connections: [],
  },
  {
    id: 'ceo',
    type: 'org-person',
    position: { x: 24, y: 68 },
    data: { label: 'Ada', title: 'CEO', status: 'paused', adapter_type: 'claude' },
    connections: [],
  },
]

const WORKFLOW_NODES: CanvasNode[] = [
  {
    id: 'n1',
    type: 'step',
    position: { x: 10, y: 10 },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  },
]

function makeI18n(locale: 'en' | 'ar') {
  return createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })
}

function mountCanvas(props: Record<string, unknown>, locale: 'en' | 'ar' = 'en') {
  return mount(WorkflowCanvas, {
    props: { selectedNodeId: null, ...props },
    global: { plugins: [makeI18n(locale)] },
  })
}

/** Shift-drag the canvas by (dx, dy) and return the resulting transform. */
async function panBy(wrapper: ReturnType<typeof mountCanvas>, dx: number, dy: number) {
  const area = wrapper.get('.canvas-area')
  await area.trigger('mousedown', { clientX: 100, clientY: 100, shiftKey: true, button: 0 })
  await area.trigger('mousemove', { clientX: 100 + dx, clientY: 100 + dy })
  await area.trigger('mouseup', { clientX: 100 + dx, clientY: 100 + dy })
  return wrapper.get('.canvas-content').attributes('style')
}

afterEach(() => {
  document.documentElement.removeAttribute('dir')
})

describe('WorkflowCanvas authoring mode is unchanged (#13939)', () => {
  it('keeps the authoring toolbar, ports and delete button by default', () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES })

    expect(wrapper.text()).toContain(en.workflow.canvas.addStep)
    expect(wrapper.text()).toContain(en.workflow.canvas.save)
    expect(wrapper.find('.port-in').exists()).toBe(true)
    expect(wrapper.find('.delete-btn').exists()).toBe(true)
  })

  it('renders no tab strip when the consumer supplies no tabs', () => {
    expect(mountCanvas({ nodes: WORKFLOW_NODES }).find('.canvas-tabs').exists()).toBe(false)
  })

  it('still emits node-added from the toolbar', async () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES })
    await wrapper.findAll('.tool-btn')[0].trigger('click')

    expect(wrapper.emitted('node-added')).toBeTruthy()
  })
})

describe('WorkflowCanvas read-only org mode (#13939)', () => {
  it('hides every authoring affordance', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES, readonly: true })

    expect(wrapper.text()).not.toContain(en.workflow.canvas.addStep)
    expect(wrapper.text()).not.toContain(en.workflow.canvas.save)
    expect(wrapper.find('.port-in').exists()).toBe(false)
    expect(wrapper.find('.delete-btn').exists()).toBe(false)
  })

  it('keeps pan/zoom controls available', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES, readonly: true })

    expect(wrapper.find('.canvas-area').exists()).toBe(true)
    expect(wrapper.findAll('.toolbar-right .tool-btn')).toHaveLength(3)
  })

  it('labels org nodes from their data and sizes the container', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES, readonly: true })
    const group = wrapper.get('.workflow-node.org-group')
    const person = wrapper.get('.workflow-node.org-person')

    expect(group.text()).toContain('Ada unit')
    expect(group.attributes('style')).toContain('width: 600px')
    expect(group.attributes('style')).toContain('height: 320px')
    expect(person.text()).toContain('Ada')
    expect(person.text()).toContain('CEO')
    expect(person.text()).toContain('claude')
    expect(person.find('.org-status.status-paused').exists()).toBe(true)
  })

  it('emits node-selected when an org node is clicked', async () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES, readonly: true })
    await wrapper.get('.workflow-node.org-person').trigger('click')

    expect(wrapper.emitted('node-selected')).toEqual([['ceo']])
  })

  it('renders the tab strip and emits the selected tab', async () => {
    const wrapper = mountCanvas({
      nodes: ORG_NODES,
      readonly: true,
      tabs: [
        { id: 'all', label: 'All units' },
        { id: 'ceo', label: 'Ada' },
      ],
      activeTabId: 'all',
    })
    const tabs = wrapper.findAll('.canvas-tab')

    expect(tabs).toHaveLength(2)
    expect(tabs[0].classes()).toContain('active')
    await tabs[1].trigger('click')
    expect(wrapper.emitted('tab-selected')).toEqual([['ceo']])
  })
})

describe('WorkflowCanvas panning is direction-agnostic (#13939)', () => {
  it('pans by the same transform in an RTL locale as in an LTR one', async () => {
    const ltr = mountCanvas({ nodes: ORG_NODES, readonly: true }, 'en')
    const ltrStyle = await panBy(ltr, 120, 30)

    document.documentElement.setAttribute('dir', 'rtl')
    const rtl = mountCanvas({ nodes: ORG_NODES, readonly: true }, 'ar')
    const rtlStyle = await panBy(rtl, 120, 30)

    expect(ltrStyle).toContain('translate(170px, 80px)')
    expect(rtlStyle).toBe(ltrStyle)
  })

  it('positions org nodes from the left edge regardless of document direction', () => {
    document.documentElement.setAttribute('dir', 'rtl')
    const wrapper = mountCanvas({ nodes: ORG_NODES, readonly: true }, 'ar')

    expect(wrapper.get('.workflow-node.org-person').attributes('style')).toContain('left: 24px')
  })
})
