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

  // An empty picker and a picker that could not load are different claims, and
  // the dropdown alone renders them identically (#14064's shape). The pair
  // below is deliberate: neither test can pass on its own if the distinction is
  // dropped, because one demands the notice and the other forbids it.
  it('says so when the roles request did not answer', async () => {
    respond()
    get.mockImplementation((url: string) => {
      if (url.includes('/process-nodes')) return Promise.resolve({ nodes: PROCESSES })
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      if (url.includes('/api/llc/roles/')) return Promise.reject(new Error('HTTP 503: upstream'))
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(wrapper.find('[data-testid="process-attach-roles-unavailable"]').exists()).toBe(true)
    // Positive companion: the form is still there, so the assertion above
    // cannot be satisfied by the view having failed to render at all.
    expect(wrapper.find('[data-testid="process-attach-form"]').exists()).toBe(true)
  })

  it('stays silent when the roles request answers with none', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/process-nodes')) return Promise.resolve({ nodes: PROCESSES })
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      if (url.includes('/api/llc/roles/')) return Promise.resolve([])
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(wrapper.find('[data-testid="process-attach-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="process-attach-roles-unavailable"]').exists()).toBe(false)
  })

  // The guards below are not decoration: each one is reachable, and each
  // prevents a request that would otherwise be malformed or duplicated.
  // What actually stops a double POST here is the submit button's disabled
  // binding, not the handler's in-flight guard — so that is what this asserts.
  // (The handler keeps its own guard as defence for callers that are not the
  // button; nothing in the UI can reach it, and it is left uncovered rather
  // than reached by a contrived call that would prove nothing.)
  it('disables the submit button while an attach is in flight, so it cannot post twice', async () => {
    respond([], PROCESSES)
    let resolvePost: () => void = () => {}
    post.mockImplementation(() => new Promise<void>((r) => { resolvePost = () => r() }))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    await wrapper.find('[data-testid="process-attach-role-select"]').setValue('r1')
    await wrapper.find('[data-testid="process-attach-workflow-input"]').setValue('wf-quarterly')
    const submit = wrapper.find('[data-testid="process-attach-submit"]')
    await submit.trigger('click')
    // Second click while the first is still in flight.
    await submit.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    expect(
      wrapper.find('[data-testid="process-attach-submit"]').attributes('disabled'),
    ).toBeDefined()

    // Not asserting it re-enables on success: the handler clears the workflow
    // field once the attach lands, so the button is legitimately disabled again
    // for that reason instead.
    resolvePost()
    await flushPromises()
  })

  it('does not delete the same attachment twice when detached rapidly', async () => {
    respond(PROCESSES, [])
    let resolveDel: () => void = () => {}
    del.mockImplementation(() => new Promise<void>((r) => { resolveDel = () => r() }))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('process-detached', 'r1', 'wf-quarterly')
    canvas.vm.$emit('process-detached', 'r1', 'wf-quarterly')
    await flushPromises()

    expect(del).toHaveBeenCalledTimes(1)
    resolveDel()
    await flushPromises()
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
