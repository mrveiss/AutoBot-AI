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

function respond(processes: unknown = PROCESSES): void {
  get.mockImplementation((url: string) => {
    if (url.includes('/process-nodes')) return Promise.resolve({ nodes: processes })
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    return Promise.resolve({ nodes: [] })
  })
}

async function mountChart() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
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
})
