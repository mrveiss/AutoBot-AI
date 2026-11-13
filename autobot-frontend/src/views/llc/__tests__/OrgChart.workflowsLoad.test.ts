// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21242: the org chart lists the company's workflows for the canvas only. A reader who stays in tree
// mode pays for no `/api/llc/workflows/` request, even when the company id resolves after mount, and
// entering the canvas lists them once. A company that cannot be resolved is a failure the canvas says
// so about, not an empty chart.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post: vi.fn(), delete: vi.fn() }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

// Starts empty, as the real composable does; `resolveCompanyId` fills it in after the view mounted.
const companyRef = ref('')
const resolveCompanyId = vi.fn()
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({ companyId: companyRef, resolveCompanyId }),
}))

import OrgChart from '../OrgChart.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

// One root node: a non-empty hierarchy is what lets the canvas branch of the template render at all
// (an empty `tree` shows the empty state instead, outside People mode).
const PEOPLE = [
  {
    id: 'ceo',
    node_id: 'n-ceo',
    name: 'Ada',
    title: 'CEO',
    status: 'idle',
    adapter_type: 'claude',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children: [],
  },
]

function respond(): void {
  get.mockImplementation((url: string) => {
    if (url.startsWith('/api/llc/workflows/')) return Promise.resolve([])
    if (url.endsWith('/members')) return Promise.resolve({ members: [], viewer_can_manage: false })
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/involved')) return Promise.resolve({ with_role: [], unassigned: [] })
    if (url.endsWith('/teams')) return Promise.resolve({ teams: [] })
    if (url.includes('/executor-rollup')) return Promise.resolve({ cells: [] })
    return Promise.resolve({ nodes: [] })
  })
}

function workflowGets(): string[] {
  return get.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith('/api/llc/workflows/'))
}

function teamsGets(): string[] {
  return get.mock.calls.map((c) => String(c[0])).filter((u) => u.endsWith('/teams'))
}

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  resolveCompanyId.mockReset()
  companyRef.value = ''
  respond()
})

describe('OrgChart company workflows load only with the canvas (#21242)', () => {
  it('tree mode issues no workflows request when the company resolves late; canvas entry issues one', async () => {
    resolveCompanyId.mockImplementation(async () => {
      await Promise.resolve()
      companyRef.value = 'c1'
      return 'c1'
    })
    const wrapper = await mountChart()

    expect(companyRef.value).toBe('c1')
    expect(workflowGets()).toEqual([])

    await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
    await flushPromises()

    expect(workflowGets()).toEqual(['/api/llc/workflows/c1'])
  })

  // Guards the late-company load, not `autoLoad` (test 1 above is the one that fails without it): the
  // canvas is opened while the company is still unknown, so entry itself lists nothing, and the id
  // arriving afterwards must still produce the one request instead of being missed.
  it('a company that resolves while the canvas is already open is listed once', async () => {
    let resolveLate!: (id: string) => void
    resolveCompanyId.mockImplementation(() => new Promise<string>((r) => (resolveLate = r)))
    const wrapper = await mountChart()
    await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
    await flushPromises()
    expect(workflowGets()).toEqual([])

    companyRef.value = 'c1'
    resolveLate('c1')
    await flushPromises()

    expect(workflowGets()).toEqual(['/api/llc/workflows/c1'])
  })
})

describe('OrgChart process nodes when the company cannot be resolved (#21242)', () => {
  it('records the failure for the unavailable banner instead of hiding it', async () => {
    // A company id is shown, but resolving it throws: the failure must not be mistaken for a company switch.
    companyRef.value = 'c1'
    resolveCompanyId.mockResolvedValue('c1')
    const wrapper = await mountChart()
    // The People sources load (and are guarded) first, so the rejection below reaches only the process nodes.
    await wrapper.find('[data-testid="org-view-people"]').trigger('click')
    await flushPromises()
    // Both People sources answered, so `peopleLoaded` is set and canvas entry never re-enters
    // `loadPeopleSources` (it awaits the company with no try/catch); one request each so far.
    expect(teamsGets()).toEqual(['/api/llc/companies/c1/teams'])
    resolveCompanyId.mockRejectedValue(new Error('HTTP 503: companies unavailable'))
    await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
    await flushPromises()

    // The canvas branch rendered (non-empty chart), and canvas entry did not re-request the teams.
    expect(wrapper.find('[data-testid="org-canvas"]').exists()).toBe(true)
    expect(teamsGets()).toHaveLength(1)
    expect(wrapper.find('[data-testid="canvas-processes-unavailable"]').exists()).toBe(true)
  })
})
