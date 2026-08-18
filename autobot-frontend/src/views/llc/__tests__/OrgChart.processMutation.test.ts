// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14549: the canvas showed a workflow-to-role attachment but could not
// change it. These guard the mutation half of that surface: attach (a form
// on the canvas) and detach (a control on the process node itself), both
// against the endpoints `RolesView.vue` already uses.
//
// The one most worth stating up front: `processNodesLoaded` guards the lazy
// fetch `fetchProcessNodes` runs on canvas-open. A mutation has to clear that
// guard before it refetches, or the "refetch" hits the guard, does nothing,
// and the canvas keeps showing the pre-mutation list while looking correct.
// Every attach/detach test below asserts the GET call count, not just the
// mutation call, so that specific failure mode cannot pass silently.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
const ROLES = [{ id: 'r1', name: 'Head of Sales' }, { id: 'r2', name: 'SRE' }]

/** GET responses. `processes` is swapped for the SECOND process-nodes call, so
 * a test can tell the pre-mutation list apart from the post-mutation one. */
function respond(processes: unknown = PROCESSES, afterProcesses: unknown = processes): void {
  let processCalls = 0
  get.mockImplementation((url: string) => {
    if (url.includes('/process-nodes')) {
      processCalls += 1
      return Promise.resolve({ nodes: processCalls === 1 ? processes : afterProcesses })
    }
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/api/llc/roles/')) return Promise.resolve(ROLES)
    return Promise.resolve({ nodes: [] })
  })
}

function processFetchCount(): number {
  return get.mock.calls.filter((c) => String(c[0]).includes('/process-nodes')).length
}

async function mountChart() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, OrgPeopleList: true } },
  })
  await flushPromises()
  return wrapper
}

async function openCanvas(wrapper: Awaited<ReturnType<typeof mountChart>>) {
  await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
  await flushPromises()
}

describe('OrgChart process attach/detach (#14549)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
    push.mockReset()
  })

  it('detaches a process node from its own control and the node disappears', async () => {
    respond(PROCESSES, [])
    del.mockResolvedValue(undefined)
    const wrapper = await mountChart()
    await openCanvas(wrapper)
    expect(processFetchCount()).toBe(1)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('process-detached', 'r1', 'wf-quarterly')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows/wf-quarterly')
    // The refetch must actually re-run, not hit the `processNodesLoaded` guard
    // and silently keep the stale list.
    expect(processFetchCount()).toBe(2)
    const nodes = canvas.props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(0)
  })

  it('attaches a workflow to a role from the canvas form and the node appears', async () => {
    respond([], PROCESSES)
    post.mockResolvedValue(undefined)
    const wrapper = await mountChart()
    await openCanvas(wrapper)
    expect(processFetchCount()).toBe(1)

    await wrapper.find('[data-testid="process-attach-role-select"]').setValue('r1')
    await wrapper.find('[data-testid="process-attach-workflow-input"]').setValue('wf-quarterly')
    await wrapper.find('[data-testid="process-attach-submit"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1/r1/workflows', {
      workflow_id: 'wf-quarterly',
    })
    expect(processFetchCount()).toBe(2)
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(1)
  })

  it('a failed detach surfaces an error and leaves the graph unchanged', async () => {
    respond(PROCESSES)
    del.mockRejectedValue(new Error('HTTP 409: workflow still running'))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('process-detached', 'r1', 'wf-quarterly')
    await flushPromises()

    expect(wrapper.find('[data-testid="process-mutation-error"]').text()).toBe(
      'HTTP 409: workflow still running',
    )
    // No optimistic mutation and no reload attempted on failure: the list the
    // canvas draws from is exactly what it was before the click.
    expect(processFetchCount()).toBe(1)
    const nodes = canvas.props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(1)
  })

  it('a failed attach surfaces an error and does not add a node', async () => {
    respond(PROCESSES)
    post.mockRejectedValue(new Error('HTTP 400: unknown workflow id'))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    await wrapper.find('[data-testid="process-attach-role-select"]').setValue('r2')
    await wrapper.find('[data-testid="process-attach-workflow-input"]').setValue('wf-new')
    await wrapper.find('[data-testid="process-attach-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="process-mutation-error"]').text()).toBe(
      'HTTP 400: unknown workflow id',
    )
    expect(processFetchCount()).toBe(1)
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-process')).toHaveLength(1)
  })
})
