// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13943: the "View As: role" lens on the Company OS canvas. These tests
// pin the hard condition from umbrella #13935 — it is a presentation filter,
// visibly marked as one, and never withholds a fetch or an endpoint — plus
// the #14064 failure shape: a lens that removes everything must still read
// as "filtered", not as "no data".

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
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import { ORG_GROUP_PREFIX } from '@/composables/llc/orgCanvasGraph'

const NODES = [
  {
    id: 'ceo',
    name: 'Ada',
    title: 'manager',
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
        title: 'worker',
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
      {
        id: 'dev2',
        name: 'Hana',
        title: 'worker',
        status: 'idle',
        adapter_type: 'ollama',
        is_human: false,
        last_heartbeat: null,
        budget_spent: 0,
        budget_total: 5,
        assigned_item_count: 0,
        parent_id: 'ceo',
        children: [],
      },
    ],
  },
  {
    id: 'advisor',
    name: 'Alan',
    title: 'lead',
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

async function mountOnCanvas() {
  const wrapper = await mountChart()
  await wrapper.get('[data-testid="org-view-canvas"]').trigger('click')
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  get.mockResolvedValue({ nodes: structuredClone(NODES) })
  post.mockResolvedValue({})
})

describe('OrgChart "View As: role" lens (#13943)', () => {
  it('offers no lens control outside canvas mode', async () => {
    const wrapper = await mountChart()

    expect(wrapper.find('[data-testid="role-lens-control"]').exists()).toBe(false)
  })

  it('offers one option per distinct role present, sorted, plus "all roles"', async () => {
    const wrapper = await mountOnCanvas()

    const options = wrapper.findAll('[data-testid="role-lens-select"] option').map((o) => o.text())
    expect(options).toEqual([en.llc.orgChart.roleLensAll, 'lead', 'manager', 'worker'])
  })

  it('selecting a role narrows the canvas to matching people, keeping containers', async () => {
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('worker')

    const ids = wrapper.findComponent(WorkflowCanvas).props('nodes').map((node) => node.id)
    expect(ids).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'dev', 'dev2'])
  })

  it('marks the lens visibly and textually as a view filter, not access control', async () => {
    const wrapper = await mountOnCanvas()
    await wrapper.get('[data-testid="role-lens-select"]').setValue('worker')
    await flushPromises()

    const banner = wrapper.get('[data-testid="role-lens-banner"]')
    expect(banner.text()).toContain('worker')
    // The umbrella's hard condition: the copy itself states access is
    // unchanged, so the control cannot be mistaken for a permission gate.
    expect(banner.text().toLowerCase()).toContain('access')
    expect(wrapper.get('[data-testid="role-lens-clear"]').exists()).toBe(true)
  })

  it('shows no banner and the full canvas when no role is selected', async () => {
    const wrapper = await mountOnCanvas()

    expect(wrapper.find('[data-testid="role-lens-banner"]').exists()).toBe(false)
    const ids = wrapper.findComponent(WorkflowCanvas).props('nodes').map((node) => node.id)
    expect(ids).toEqual(expect.arrayContaining(['ceo', 'dev', 'dev2', 'advisor']))
  })

  it('a role matching nobody inside a unit still shows the emptied container — the box is the filtered cue', async () => {
    const wrapper = await mountOnCanvas()
    await wrapper.get('[data-testid="role-lens-select"]').setValue('lead')
    await flushPromises()

    // "lead" only exists on the ungrouped "advisor" root — no person inside
    // the "ceo" unit carries it, so the unit's group container is drawn
    // empty (unaffected by the filter): the box is the "filtered, not
    // missing" cue, so WorkflowCanvas stays mounted rather than the whole
    // canvas being replaced.
    const canvas = wrapper.findComponent(WorkflowCanvas)
    expect(canvas.exists()).toBe(true)
    expect(canvas.props('nodes').map((node) => node.id)).toEqual([`${ORG_GROUP_PREFIX}ceo`, 'advisor'])
    expect(wrapper.find('[data-testid="role-lens-empty-canvas"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="role-lens-banner"]').text()).toContain('lead')
  })

  it('a lens left selected across a reload that removes its last match shows the explicit "filtered, not empty" message, never "no data"', async () => {
    // Two standalone (ungrouped, #13994) agents — no unit container for
    // either, so once "solo1" is gone nothing stands in for it.
    const before = [
      {
        id: 'solo1', name: 'Solo One', title: 'lead', status: 'idle', adapter_type: 'claude',
        is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0,
        assigned_item_count: 0, parent_id: null, children: [],
      },
      {
        id: 'solo2', name: 'Solo Two', title: 'keep', status: 'idle', adapter_type: 'claude',
        is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0,
        assigned_item_count: 0, parent_id: null, children: [],
      },
    ]
    get.mockResolvedValueOnce({ nodes: before })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await mountOnCanvas()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('lead')
    await flushPromises()
    expect(wrapper.findComponent(WorkflowCanvas).props('nodes').map((n) => n.id)).toEqual(['solo1'])

    // Terminate reloads from the source of truth (#14108) — the company
    // still has a person ("solo2"), so the top-level "empty company" state
    // never fires, but nobody left carries the still-selected "lead" role.
    get.mockResolvedValueOnce({ nodes: [before[1]] })
    wrapper.findComponent(WorkflowCanvas).vm.$emit('node-selected', 'solo1')
    await flushPromises()
    await wrapper.get('[data-testid="org-drawer-terminate"]').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(WorkflowCanvas).exists()).toBe(false)
    const empty = wrapper.get('[data-testid="role-lens-empty-canvas"]')
    expect(empty.text()).toContain('lead')
    expect(empty.text().toLowerCase()).not.toContain('empty workflow')
    confirmSpy.mockRestore()
  })

  it('clearing the lens restores every node', async () => {
    const wrapper = await mountOnCanvas()
    await wrapper.get('[data-testid="role-lens-select"]').setValue('worker')
    await flushPromises()

    await wrapper.get('[data-testid="role-lens-clear"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="role-lens-banner"]').exists()).toBe(false)
    const ids = wrapper.findComponent(WorkflowCanvas).props('nodes').map((node) => node.id)
    expect(ids).toEqual(expect.arrayContaining(['ceo', 'dev', 'dev2', 'advisor']))
  })

  it('never fetches or posts as a result of a lens selection — presentation only', async () => {
    const wrapper = await mountOnCanvas()
    get.mockClear()
    post.mockClear()

    await wrapper.get('[data-testid="role-lens-select"]').setValue('worker')
    await flushPromises()
    await wrapper.get('[data-testid="role-lens-clear"]').trigger('click')
    await flushPromises()

    expect(get).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })
})
