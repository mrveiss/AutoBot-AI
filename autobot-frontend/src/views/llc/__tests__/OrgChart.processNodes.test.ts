// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13963: process nodes on the Org Chart canvas — the contextual entrance to
// the absorbed automation module.
//
// Every test here pins something I got wrong first, so each exists because the
// invariant was already broken once:
//
//  * fetching on mount broke `OrgChart.people`'s "does not fetch until opened"
//    contract. Process nodes render only on the canvas, so they load when the
//    canvas is opened.
//  * merging processes into `canvasNodes` (and into `layoutKey`) rebuilt the
//    graph when they arrived and discarded dragged positions — #13996's defect,
//    reintroduced. They are derived and merged at render time instead.
//  * the fetch trusted whatever shape came back, so a response of another shape
//    rendered as nonsense nodes rather than as nothing.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const push = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

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
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'

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

const PROCESSES = [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }]

// #21242: the company's workflows, which tell "none attached" from "nothing attachable".
const WORKFLOWS = [{ workflow_id: 'wf-quarterly', name: 'Quarterly', kind: 'workflow' }]

function respond(processes: unknown = PROCESSES, workflows: unknown = WORKFLOWS): void {
  get.mockImplementation((url: string) => {
    if (url.startsWith('/api/llc/workflows/')) return Promise.resolve(workflows)
    if (url.includes('/process-nodes')) return Promise.resolve({ nodes: processes })
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    return Promise.resolve({ nodes: [] })
  })
}

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  await flushPromises()
  return wrapper
}

function processUrls(): string[] {
  return get.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/process-nodes'))
}

async function openCanvas(wrapper: Awaited<ReturnType<typeof mountChart>>) {
  await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
}

describe('OrgChart process nodes (#13963)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    push.mockReset()
  })

  it('does not fetch processes until the canvas is opened', async () => {
    respond()
    await mountChart()

    expect(processUrls()).toHaveLength(0)
  })

  it('fetches them once when the canvas is opened, not on every toggle', async () => {
    respond()
    const wrapper = await mountChart()

    await openCanvas(wrapper)
    expect(processUrls()).toHaveLength(1)

    await wrapper.find('[data-testid="org-view-tree"]').trigger('click')
    await flushPromises()
    await openCanvas(wrapper)

    expect(processUrls()).toHaveLength(1)
  })

  it('draws a process node on the canvas alongside the people', async () => {
    respond()
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(1)
    // The people are still there — processes are added, not substituted.
    expect(nodes.some((n) => n.type === 'org-person')).toBe(true)
  })

  it('ignores a response whose rows are not process nodes', async () => {
    // A misrouted mock or a changed contract must yield no nodes, not garbage
    // ones. This is what an earlier draft got wrong: it rendered the org-chart
    // payload as processes.
    respond(PEOPLE)
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(0)
  })

  it('keeps a dragged position when processes arrive afterwards', async () => {
    // #13996: `canvasNodes` holds dragged positions and must not be rebuilt by
    // a later fetch. Processes are derived, so their arrival cannot disturb it.
    respond()
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('node-moved', 'ceo', { x: 900, y: 42 })
    await flushPromises()

    // A second canvas entry would re-run the fetch if it were not once-only.
    await wrapper.find('[data-testid="org-view-tree"]').trigger('click')
    await flushPromises()
    await openCanvas(wrapper)

    const nodes = canvas.props('nodes') as { id: string; position: { x: number; y: number } }[]
    const moved = nodes.find((n) => n.id === 'ceo')
    expect(moved?.position).toEqual({ x: 900, y: 42 })
  })

  it('opens the workflow the clicked process node names', async () => {
    respond()
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    const nodes = canvas.props('nodes') as { id: string; type: string }[]
    const process = nodes.find((n) => n.type === 'org-process')
    canvas.vm.$emit('node-selected', process?.id ?? '')
    await flushPromises()

    expect(push).toHaveBeenCalledWith({
      name: 'automation-section',
      params: { companyId: 'c1', section: 'runner' },
      query: { workflow: 'wf-quarterly' },
    })
  })

  it('opens the drawer, not the router, for a person node', async () => {
    respond()
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('node-selected', 'ceo')
    await flushPromises()

    expect(push).not.toHaveBeenCalled()
  })

  it('keeps the people graph when the process fetch fails', async () => {
    // The org chart is still correct without the process nodes, so a failed
    // secondary fetch must not blank it or surface as a page error — #14104's
    // `peopleUnavailable` precedent. An absent source rendering as "no org
    // chart" is the failure this guards.
    get.mockImplementation((url: string) => {
      if (url.startsWith('/api/llc/workflows/')) return Promise.resolve([])
      if (url.includes('/process-nodes')) return Promise.reject(new Error('HTTP 500: boom'))
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.some((n) => n.type === 'org-person')).toBe(true)
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(0)
    // #21242: and it says the processes are unavailable, rather than drawing an empty chart.
    expect(wrapper.find('[data-testid="canvas-processes-unavailable"]').exists()).toBe(true)
  })

  it('retries the fetch on a later canvas visit after a failure', async () => {
    // The once-only guard is set on success, not on attempt: a transient
    // failure must not permanently hide this company's processes.
    let attempt = 0
    get.mockImplementation((url: string) => {
      if (url.startsWith('/api/llc/workflows/')) return Promise.resolve([])
      if (url.includes('/process-nodes')) {
        attempt += 1
        return attempt === 1
          ? Promise.reject(new Error('HTTP 503: try again'))
          : Promise.resolve({ nodes: PROCESSES })
      }
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    await wrapper.find('[data-testid="org-view-tree"]').trigger('click')
    await flushPromises()
    await openCanvas(wrapper)

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(1)
    expect(wrapper.find('[data-testid="canvas-processes-unavailable"]').exists()).toBe(false)
  })
})

// #21242: an empty process canvas is one of three different things.
describe('OrgChart process banners (#21242)', () => {
  const BANNERS = ['unavailable', 'noneAttached', 'nothingAttachable']
  const shown = (wrapper: Awaited<ReturnType<typeof mountChart>>) =>
    BANNERS.filter((b) => wrapper.find(`[data-testid="canvas-processes-${b}"]`).exists())

  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    push.mockReset()
  })

  it('says none are attached when workflows exist but no role runs one', async () => {
    respond([], WORKFLOWS)
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(shown(wrapper)).toEqual(['noneAttached'])
  })

  it('says there is nothing to attach when the company has no workflows', async () => {
    respond([], [])
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(shown(wrapper)).toEqual(['nothingAttachable'])
  })

  it('says the processes are unavailable when the fetch failed, not that none are attached', async () => {
    get.mockImplementation((url: string) => {
      if (url.startsWith('/api/llc/workflows/')) return Promise.resolve(WORKFLOWS)
      if (url.includes('/process-nodes')) return Promise.reject(new Error('HTTP 500: boom'))
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(shown(wrapper)).toEqual(['unavailable'])
  })

  it('says nothing while there are process nodes, and nothing before the canvas is opened', async () => {
    respond()
    const wrapper = await mountChart()
    expect(shown(wrapper)).toEqual([])

    await openCanvas(wrapper)
    expect(shown(wrapper)).toEqual([])
  })
})
