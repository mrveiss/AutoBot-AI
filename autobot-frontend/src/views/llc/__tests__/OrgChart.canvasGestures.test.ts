// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #14749 AC1: the Company OS org chart mounts the canvas `readonly`, but right-click, the `...` menu
// button, shift-click and the marquee are all live there. They must never reach a mutation: the only
// route to a detach is the card's own button, and only for a viewer who may manage the company. The
// real OrgChart and the real canvas; every assertion is made at the request layer (`del`/`post`).
//
// The rectangle of the marquee below covers the whole canvas on purpose: node positions come from the
// org layout, so a rectangle that depends on them would assert the layout and not the gesture.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()
const push = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, delete: del }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
// The attach form's selects are the kit's select menu, whose popper does not run in jsdom.
vi.mock('reka-ui', async () => (await import('@/test/rekaSelectStub')).rekaSelectStub())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ params: { companyId: 'c1' }, query: {} }),
}))
const companyRef = ref('c1')
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: companyRef,
    resolveCompanyId: () => Promise.resolve(companyRef.value),
  }),
}))

import OrgChart from '../OrgChart.vue'
import { firePointer } from '@/components/workflow/__tests__/pointerTestUtils'

const PEOPLE = [
  {
    id: 'ceo', node_id: 'n-ceo', name: 'Ada', title: 'CEO', status: 'idle', adapter_type: 'claude',
    is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0, assigned_item_count: 0,
    parent_id: null, children: [],
  },
]
const PROCESSES = [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }]
const TOOLS = [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' }]
const PROCESS_NODE = 'process:r1:wf-quarterly'
const TOOL_NODE = 'tool:web_search'
const PROCESS_DETACH_URL = '/api/llc/roles/c1/r1/workflows/wf-quarterly'
const TOOL_DETACH_URL = '/api/llc/roles/c1/r1/tools/web_search'

const members = (viewerCanManage: boolean) => ({
  members: [{ user_id: 'u1', display_name: 'Ada', role: viewerCanManage ? 'owner' : 'member' }],
  viewer_can_manage: viewerCanManage,
})

/** GET answers; the second process-nodes call answers `[]`, as after a detach. */
function respond(viewerCanManage: boolean): void {
  let processCalls = 0
  get.mockImplementation((url: string) => {
    if (url.startsWith('/api/llc/workflows/')) return Promise.resolve([])
    if (url.includes('/process-nodes')) {
      processCalls += 1
      return Promise.resolve({ nodes: processCalls === 1 ? PROCESSES : [] })
    }
    if (url.includes('/tool-nodes')) return Promise.resolve({ nodes: TOOLS })
    if (url.includes('/members')) return Promise.resolve(members(viewerCanManage))
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/api/llc/roles/')) return Promise.resolve([{ id: 'r1', name: 'Head of Sales' }])
    return Promise.resolve({ nodes: [] })
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mounted: VueWrapper[] = []

async function canvasChart(viewerCanManage = true) {
  respond(viewerCanManage)
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  mounted.push(wrapper)
  await flushPromises()
  await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
  return wrapper
}

type Wrapper = Awaited<ReturnType<typeof canvasChart>>
const node = (w: Wrapper, id: string) => w.get(`[data-node-id="${id}"]`)
const menu = (w: Wrapper) => w.find('[data-testid="canvas-context-menu"]')
const menuItemIds = (w: Wrapper) =>
  w.findAll('[role="menuitem"]').map((el) => (el.attributes('data-testid') ?? '').replace('canvas-context-menu-item-', ''))
const mutating = (id: string) => id === 'delete' || id.startsWith('detach')
const multiSelected = (w: Wrapper) => w.findAll('.workflow-node.multi-selected')

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  del.mockReset()
  push.mockReset()
  del.mockResolvedValue(undefined)
  post.mockResolvedValue(undefined)
})

afterEach(() => {
  while (mounted.length > 0) mounted.pop()!.unmount()
})

describe('the readonly org chart canvas never reaches a mutation from a gesture (#14749)', () => {
  it.each([
    ['right-click on a process node', PROCESS_NODE, (w: Wrapper) => node(w, PROCESS_NODE).trigger('contextmenu', { clientX: 10, clientY: 10 })],
    ['the ... button of a process node', PROCESS_NODE, (w: Wrapper) => node(w, PROCESS_NODE).get('[data-testid="node-menu-btn"]').trigger('click')],
    ['right-click on a tool node', TOOL_NODE, (w: Wrapper) => node(w, TOOL_NODE).trigger('contextmenu', { clientX: 10, clientY: 10 })],
    ['the ... button of a tool node', TOOL_NODE, (w: Wrapper) => node(w, TOOL_NODE).get('[data-testid="node-menu-btn"]').trigger('click')],
  ])('%s opens a menu with no detach or delete and sends no request', async (_label, _nodeId, open) => {
    const w = await canvasChart()
    expect(menu(w).exists()).toBe(false)
    expect(del).not.toHaveBeenCalled()

    await open(w)
    await flushPromises()

    expect(menu(w).exists()).toBe(true)
    expect(menuItemIds(w).length).toBeGreaterThan(0)
    expect(menuItemIds(w).filter(mutating)).toEqual([])
    expect(del).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('shift-click adds a node to the selection and sends no request', async () => {
    const w = await canvasChart()
    await node(w, PROCESS_NODE).trigger('click')
    expect(node(w, TOOL_NODE).classes()).not.toContain('multi-selected')

    await node(w, TOOL_NODE).trigger('click', { shiftKey: true })
    await flushPromises()

    expect(node(w, TOOL_NODE).classes()).toContain('multi-selected')
    expect(del).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('a marquee over the canvas selects the nodes and sends no request', async () => {
    const w = await canvasChart()
    const area = w.get('.canvas-area').element
    const drawn = w.findAll('.workflow-node').length
    expect(drawn).toBeGreaterThan(0)
    expect(multiSelected(w)).toHaveLength(0)

    await firePointer(area, 'pointerdown', { clientX: 0, clientY: 0, button: 0 })
    await firePointer(area, 'pointermove', { clientX: 20, clientY: 20 })
    await firePointer(area, 'pointermove', { clientX: 5000, clientY: 5000 })
    await firePointer(area, 'pointerup', { clientX: 5000, clientY: 5000 })
    await flushPromises()

    expect(multiSelected(w)).toHaveLength(drawn)
    expect(del).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })
})

describe('the card\'s own detach button is the one route to a detach (#14749)', () => {
  it('deletes the process attachment once, from the button of a viewer who may manage', async () => {
    const w = await canvasChart(true)
    expect(del).not.toHaveBeenCalled()

    await node(w, PROCESS_NODE).get('[data-testid="process-detach-btn"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledTimes(1)
    expect(del).toHaveBeenCalledWith(PROCESS_DETACH_URL)
  })

  it('deletes the tool attachment once, from the button of a viewer who may manage', async () => {
    const w = await canvasChart(true)
    expect(del).not.toHaveBeenCalled()

    await node(w, TOOL_NODE).get('[data-testid="tool-detach-btn"]').trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledTimes(1)
    expect(del).toHaveBeenCalledWith(TOOL_DETACH_URL)
  })

  it('shows a viewer who may not manage no detach button, and the menu still offers none', async () => {
    const w = await canvasChart(false)
    // The nodes are drawn, so the absence below is not an unrendered canvas.
    expect(node(w, PROCESS_NODE).exists()).toBe(true)
    expect(node(w, TOOL_NODE).exists()).toBe(true)

    expect(w.find('[data-testid="process-detach-btn"]').exists()).toBe(false)
    expect(w.find('[data-testid="tool-detach-btn"]').exists()).toBe(false)
    await node(w, PROCESS_NODE).trigger('contextmenu', { clientX: 10, clientY: 10 })
    expect(menuItemIds(w).filter(mutating)).toEqual([])
    expect(del).not.toHaveBeenCalled()
  })
})
