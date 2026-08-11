// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13939: the Org Chart gained a second render of the same data — the
// existing WorkflowCanvas — behind a view-mode toggle. These tests pin both
// halves: the canvas mode (mapping, tabs, drawer wiring, read-only canvas) and
// the nested-tree mode, which stays the default and must keep hire / pause /
// resume / terminate and the detail drawer working exactly as before.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({
    companyId: { value: 'c1' },
    resolveCompanyId: () => Promise.resolve('c1'),
  }),
}))

import OrgChart from '../OrgChart.vue'
import OrgTreeNode from '../OrgTreeNode.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import { ORG_GROUP_PREFIX } from '@/composables/llc/orgCanvasGraph'

const NODES = [
  {
    id: 'ceo',
    name: 'Ada',
    title: 'CEO',
    status: 'idle',
    adapter_type: 'claude',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 1,
    budget_total: 10,
    assigned_item_count: 2,
    parent_id: null,
    children: [
      {
        id: 'dev',
        name: 'Grace',
        title: 'Engineer',
        status: 'paused',
        adapter_type: 'ollama',
        is_human: false,
        last_heartbeat: null,
        budget_spent: 0,
        budget_total: 5,
        assigned_item_count: 1,
        parent_id: 'ceo',
        children: [],
      },
    ],
  },
  {
    id: 'advisor',
    name: 'Alan',
    title: 'Advisor',
    status: 'idle',
    adapter_type: 'openai',
    is_human: true,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
]

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: {
      plugins: [i18n],
      stubs: { HireAgentModal: true },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  get.mockResolvedValue({ nodes: structuredClone(NODES) })
  post.mockResolvedValue({})
})

describe('OrgChart view-mode toggle (#13939)', () => {
  it('defaults to the nested tree — the canvas is not mounted', async () => {
    const wrapper = await mountChart()

    expect(wrapper.findComponent(OrgTreeNode).exists()).toBe(true)
    expect(wrapper.findComponent(WorkflowCanvas).exists()).toBe(false)
    expect(wrapper.get('[data-testid="org-view-tree"]').attributes('aria-pressed')).toBe('true')
  })

  it('renders the company graph on WorkflowCanvas in canvas mode', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    const canvas = wrapper.findComponent(WorkflowCanvas)
    expect(canvas.exists()).toBe(true)
    expect(wrapper.findComponent(OrgTreeNode).exists()).toBe(false)

    const ids = canvas.props('nodes').map((node) => node.id)
    expect(ids).toContain('ceo')
    expect(ids).toContain('dev')
    expect(ids).toContain(`${ORG_GROUP_PREFIX}ceo`)
  })

  it('mounts the canvas read-only — the org chart is not a workflow editor', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    expect(wrapper.findComponent(WorkflowCanvas).props('readonly')).toBe(true)
  })

  it('offers one canvas tab per unit plus "all units"', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    const canvas = wrapper.findComponent(WorkflowCanvas)
    expect(canvas.props('tabs')).toEqual([
      { id: 'all', label: en.llc.orgChart.canvasTabAll },
      { id: 'ceo', label: 'Ada' },
      { id: 'advisor', label: 'Alan' },
    ])
    expect(canvas.props('activeTabId')).toBe('all')
  })

  it('a tab selection narrows the canvas to that unit', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
    const canvas = wrapper.findComponent(WorkflowCanvas)

    canvas.vm.$emit('tab-selected', 'advisor')
    await flushPromises()

    const ids = wrapper.findComponent(WorkflowCanvas).props('nodes').map((node) => node.id)
    expect(ids).toEqual([`${ORG_GROUP_PREFIX}advisor`, 'advisor'])
  })

  it('a canvas node selection opens the same detail drawer the tree opens', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-selected', 'dev')
    await flushPromises()

    expect(wrapper.text()).toContain(en.llc.orgChart.agentDetail)
    expect(wrapper.text()).toContain('Grace')
  })

  it('a container selection is ignored — containers are not agents', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-selected', `${ORG_GROUP_PREFIX}ceo`)
    await flushPromises()

    expect(wrapper.text()).not.toContain(en.llc.orgChart.agentDetail)
  })

  it('a dragged node keeps its new position', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')

    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-moved', 'dev', { x: 900, y: 42 })
    await flushPromises()

    const moved = wrapper
      .findComponent(WorkflowCanvas)
      .props('nodes')
      .find((node) => node.id === 'dev')
    expect(moved!.position).toEqual({ x: 900, y: 42 })
  })

  it('a dragged container stays anchored to its subtree', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
    const groupId = `${ORG_GROUP_PREFIX}ceo`
    const before = wrapper
      .findComponent(WorkflowCanvas)
      .props('nodes')
      .find((node) => node.id === groupId)!.position

    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-moved', groupId, { x: 900, y: 900 })
    await flushPromises()

    const after = wrapper
      .findComponent(WorkflowCanvas)
      .props('nodes')
      .find((node) => node.id === groupId)!.position
    expect(after).toEqual(before)
  })

  it('resume from the drawer still calls the canonical endpoint in canvas mode', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-selected', 'dev')
    await flushPromises()

    await wrapper.get('[data-testid="org-drawer-pause"]').trigger('click')

    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/controls/agents/dev/resume', {})
  })
})

describe('OrgChart nested-tree mode is unregressed (#13939)', () => {
  it('renders one OrgTreeNode per root and opens the drawer on select', async () => {
    const wrapper = await mountChart()

    const roots = wrapper.findAllComponents(OrgTreeNode).filter((node) => node.props('depth') === 0)
    expect(roots).toHaveLength(2)

    roots[0].vm.$emit('select', structuredClone(NODES)[0])
    await flushPromises()
    expect(wrapper.text()).toContain(en.llc.orgChart.agentDetail)
    expect(wrapper.text()).toContain('Ada')
  })

  it('pause from the tree drawer hits the canonical pause endpoint', async () => {
    const wrapper = await mountChart()
    const root = wrapper.findAllComponents(OrgTreeNode)[0]

    root.vm.$emit('select', structuredClone(NODES)[0])
    await flushPromises()
    await wrapper.get('[data-testid="org-drawer-pause"]').trigger('click')

    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/controls/agents/ceo/pause', {})
  })

  it('terminate from the tree drawer confirms, posts and reloads', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await mountChart()

    wrapper.findAllComponents(OrgTreeNode)[0].vm.$emit('select', structuredClone(NODES)[0])
    await flushPromises()
    await wrapper.get('[data-testid="org-drawer-terminate"]').trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/controls/agents/ceo/terminate', {})
    expect(get).toHaveBeenCalledTimes(2) // reload from the source of truth
    confirmSpy.mockRestore()
  })

  it('still fetches the org chart from the company-scoped endpoint', async () => {
    await mountChart()

    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/org-chart')
  })

  it('switching back to tree restores the nested render', async () => {
    const wrapper = await mountChart()
    await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
    await wrapper.get('[data-testid="org-view-tree"]').trigger('click')

    expect(wrapper.findComponent(OrgTreeNode).exists()).toBe(true)
    expect(wrapper.findComponent(WorkflowCanvas).exists()).toBe(false)
  })
})
