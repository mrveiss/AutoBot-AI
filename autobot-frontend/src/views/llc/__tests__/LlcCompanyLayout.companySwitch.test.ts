// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21502: the sidebar's company switch re-targets the same route with another `:companyId`, so the
// company layout's routed view used to be reused and kept the previous company's data. The layout now
// keys the routed view by the route's company; a route that handles the switch itself opts out.
//
// A real router, the real layout and the real org chart: only the HTTP client, the stores/buses the
// layout reads and the two sidebar-side components are replaced. Every GET is answered from tables
// keyed by company id, so what a view shows can only have come from the company it asked about.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent, h, onMounted, reactive } from 'vue'
import en from '@/i18n/locales/en.json'

interface CompanyData {
  agent: string
  contact: string
  team: string
  role: string
  tool: string
}

const DATA: Record<string, CompanyData> = {
  c1: { agent: 'Alpha Person', contact: 'Alpha Contact', team: 'Alpha Team', role: 'Alpha Role', tool: 'alpha_tool' },
  c2: { agent: 'Bravo Person', contact: 'Bravo Contact', team: 'Bravo Team', role: 'Bravo Role', tool: 'bravo_tool' },
}

interface Held {
  promise: Promise<unknown>
  resolve: (value: unknown) => void
}

const calls: string[] = []
const held = new Map<string, Held>()
// A company whose every request is rejected.
let failingCompany: string | null = null

const probes = vi.hoisted(() => ({ sidebar: 0, normal: 0, keep: 0 }))
const store = reactive({
  selectedCompanyId: null as string | null,
  hasCompanies: true,
  isLoading: false,
  selectCompany: vi.fn(),
  fetchCompanies: vi.fn(),
})

const NOOP = () => Promise.resolve({})
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: (url: string) => answerGet(String(url)),
    post: NOOP,
    put: NOOP,
    patch: NOOP,
    delete: NOOP,
  }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => store }))
vi.mock('@/composables/useEventBus', () => ({ useEventBus: () => ({ subscribe: () => () => undefined }) }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ notifyInfo: vi.fn(), notifyWarning: vi.fn(), notifyError: vi.fn() }),
}))
// The sidebar and the plan card are not under test; the sidebar counts its mounts for the remount case.
vi.mock('@/components/llc/LlcSidebar.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      name: 'LlcSidebar',
      setup() {
        vue.onMounted(() => {
          probes.sidebar += 1
        })
        return () => vue.h('aside')
      },
    }),
  }
})
vi.mock('@/components/llc/workflowPlanner/PlanFirstProcessCard.vue', () => ({
  default: { name: 'PlanFirstProcessCard', render: () => null },
}))

import LlcCompanyLayout from '../LlcCompanyLayout.vue'
import OrgChart from '../OrgChart.vue'
import OrgPeopleList from '@/components/llc/OrgPeopleList.vue'
import OrgProcessAttachForm from '@/components/llc/OrgProcessAttachForm.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'

const MEMBERS = {
  members: [{ user_id: 'u1', display_name: 'Owner', role: 'owner' }],
  viewer_can_manage: true,
  viewer_grantable_roles: [],
}

/** What the backend answers for `url`, from the company the URL names. */
function tableAnswer(url: string, cid: string): unknown {
  const d = DATA[cid]
  const role = `r-${cid}`
  if (url.startsWith('/api/llc/workflows/')) return []
  if (url.endsWith('/members')) return MEMBERS
  if (url.endsWith('/org-chart')) {
    return {
      nodes: [
        {
          id: `agent-${cid}`, node_id: `n-${cid}`, name: d.agent, title: 'CEO', status: 'idle',
          adapter_type: 'claude', is_human: false, last_heartbeat: null, budget_spent: 0, budget_total: 0,
          assigned_item_count: 0, parent_id: null, children: [],
        },
      ],
    }
  }
  if (url.endsWith('/executor-rollup')) return { cells: [] }
  if (url.endsWith('/process-nodes')) return { nodes: [{ role_id: role, role_name: d.role, workflow_id: `wf-${cid}` }] }
  if (url.endsWith('/tool-nodes')) return { nodes: [{ role_id: role, role_name: d.role, tool_name: d.tool }] }
  if (url.startsWith('/api/llc/roles/')) return [{ id: role, name: d.role }]
  if (url.endsWith('/involved')) {
    return { with_role: [{ id: `p-${cid}`, full_name: d.contact, role_title: null, email: null, phone: null }], unassigned: [] }
  }
  if (url.endsWith('/teams')) return { teams: [{ id: `t-${cid}`, name: d.team, member_user_ids: [] }] }
  // Anything else a child asks for gets a harmless empty shape rather than a throw.
  return {}
}

function answerGet(url: string): Promise<unknown> {
  calls.push(url)
  const cid = /\/(c[12])(?:[/?]|$)/.exec(url)?.[1] ?? ''
  const hold = held.get(url)
  if (hold) return hold.promise
  if (cid && cid === failingCompany) return Promise.reject(new Error(`${cid} is unavailable`))
  return Promise.resolve(cid ? tableAnswer(url, cid) : {})
}

function hold(url: string): Held {
  let resolve!: (value: unknown) => void
  const promise = new Promise<unknown>((r) => (resolve = r))
  const entry = { promise, resolve }
  held.set(url, entry)
  return entry
}

const probe = (key: 'normal' | 'keep') =>
  defineComponent({
    setup() {
      onMounted(() => {
        probes[key] += 1
      })
      return () => h('div')
    },
  })

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/llc/companies/:companyId',
        component: LlcCompanyLayout,
        children: [
          { path: 'org-chart', name: 'llc-company-org-chart', component: OrgChart, props: true },
          { path: 'probe-normal', name: 'probe-normal', component: probe('normal') },
          { path: 'probe-keep', name: 'probe-keep', component: probe('keep'), meta: { keepOnCompanySwitch: true } },
        ],
      },
    ],
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountAt(name: string, companyId: string) {
  const router = buildRouter()
  await router.push({ name, params: { companyId } })
  await router.isReady()
  const wrapper = mount(
    { render: () => h(RouterView) },
    { global: { plugins: [router, i18n], stubs: { HireAgentModal: true, Teleport: true } } },
  )
  await flushPromises()
  return { router, wrapper }
}

type Mounted = Awaited<ReturnType<typeof mountAt>>

async function switchTo(m: Mounted, name: string, companyId: string) {
  await m.router.push({ name, params: { companyId } })
  await flushPromises()
}

const click = async (m: Mounted, testid: string) => {
  await m.wrapper.get(`[data-testid="${testid}"]`).trigger('click')
  await flushPromises()
}

const canvasIds = (m: Mounted): string[] =>
  m.wrapper.findComponent(WorkflowCanvas).props('nodes').map((node: { id: string }) => node.id)

const requestsFor = (cid: string, from = 0): string[] =>
  calls.slice(from).filter((url) => new RegExp(`/${cid}([/?]|$)`).test(url))

beforeEach(() => {
  calls.length = 0
  held.clear()
  failingCompany = null
  probes.sidebar = 0
  probes.normal = 0
  probes.keep = 0
  store.selectCompany.mockReset()
  store.fetchCompanies.mockReset()
})

describe('the company layout remounts its routed view on a company switch (#21502)', () => {
  it('asks the new company for everything and shows none of the previous company', async () => {
    const m = await mountAt('llc-company-org-chart', 'c1')
    await click(m, 'org-view-canvas')
    await click(m, 'org-view-people')
    expect(m.wrapper.text()).toContain(DATA.c1.agent)
    expect(m.wrapper.text()).toContain(DATA.c1.contact)
    expect(requestsFor('c2')).toEqual([])

    const mark = calls.length
    await switchTo(m, 'llc-company-org-chart', 'c2')

    const afterSwitch = calls.slice(mark)
    expect(afterSwitch).toContain('/api/llc/companies/c2/org-chart')
    expect(afterSwitch).toContain('/api/llc/companies/c2/work-items/executor-rollup')
    expect(m.wrapper.text()).toContain(DATA.c2.agent)
    expect(m.wrapper.text()).not.toContain('Alpha')

    await click(m, 'org-view-canvas')
    const afterCanvas = calls.slice(mark)
    expect(afterCanvas).toEqual(
      expect.arrayContaining([
        '/api/llc/companies/c2/process-nodes',
        '/api/llc/companies/c2/tool-nodes',
        '/api/llc/roles/c2',
        '/api/llc/contacts/c2/involved',
        '/api/llc/companies/c2/teams',
      ]),
    )
    expect(canvasIds(m)).toEqual(expect.arrayContaining(['process:r-c2:wf-c2', `tool:${DATA.c2.tool}`]))
    expect(canvasIds(m)).not.toContain('process:r-c1:wf-c1')
    expect(canvasIds(m)).not.toContain(`tool:${DATA.c1.tool}`)
    expect(m.wrapper.findComponent(OrgProcessAttachForm).props('roles')).toEqual([{ id: 'r-c2', name: DATA.c2.role }])

    await click(m, 'org-view-people')
    expect(m.wrapper.text()).toContain(DATA.c2.contact)
    expect(m.wrapper.text()).not.toContain('Alpha')
    expect(m.wrapper.findComponent(OrgPeopleList).props('groups').map((g: { name: string }) => g.name)).toContain(DATA.c2.team)
    expect(requestsFor('c1', mark)).toEqual([])
  })

  it('shows none of the previous company while the new company is still loading', async () => {
    const m = await mountAt('llc-company-org-chart', 'c1')
    expect(m.wrapper.text()).toContain(DATA.c1.agent)
    const tree = hold('/api/llc/companies/c2/org-chart')

    await switchTo(m, 'llc-company-org-chart', 'c2')

    expect(calls).toContain('/api/llc/companies/c2/org-chart')
    expect(m.wrapper.text()).not.toContain('Alpha')
    expect(m.wrapper.text()).not.toContain('Bravo')

    tree.resolve(tableAnswer('/api/llc/companies/c2/org-chart', 'c2'))
    await flushPromises()
    expect(m.wrapper.text()).toContain(DATA.c2.agent)
    expect(m.wrapper.text()).not.toContain('Alpha')
  })

  it('shows the failure, not the previous company, when the new company cannot be read', async () => {
    const m = await mountAt('llc-company-org-chart', 'c1')
    expect(m.wrapper.text()).toContain(DATA.c1.agent)
    failingCompany = 'c2'

    await switchTo(m, 'llc-company-org-chart', 'c2')

    // Every loader of the view catches its own rejection (fetchTree, loadExecutorRollup, the members
    // load, the people sources' allSettled, the process/tool/roles/workflow loaders), so each rejected
    // GET below ends in a visible state and none is left unhandled.
    expect(m.wrapper.text()).toContain('c2 is unavailable')
    expect(m.wrapper.text()).not.toContain('Alpha')

    await click(m, 'org-view-people')
    const people = m.wrapper.findComponent(OrgPeopleList)
    expect(people.props('contactsFailed')).toBe(true)
    expect(people.props('teamsFailed')).toBe(true)
    expect(m.wrapper.text()).not.toContain('Alpha')
  })

  it('remounts an ordinary view, keeps an opted-out view and never remounts the sidebar', async () => {
    const m = await mountAt('probe-normal', 'c1')
    expect(probes).toEqual({ sidebar: 1, normal: 1, keep: 0 })

    await switchTo(m, 'probe-normal', 'c2')
    expect(probes).toEqual({ sidebar: 1, normal: 2, keep: 0 })

    await switchTo(m, 'probe-keep', 'c1')
    expect(probes.keep).toBe(1)
    await switchTo(m, 'probe-keep', 'c2')
    expect(probes).toEqual({ sidebar: 1, normal: 2, keep: 1 })
  })
})
