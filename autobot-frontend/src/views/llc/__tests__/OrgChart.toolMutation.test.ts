// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14597: the canvas showed a role-to-tool attachment only as a list in the
// Roles tab, with no presence on Company OS. These guard the canvas half of
// that surface: fetch (with the failed-vs-empty distinction that has been a
// real defect three times in this area — #14064, #13617, #14556), attach (a
// form on the canvas) and detach (a control on the tool node itself), all
// against the endpoints `RolesView.vue` already uses. Mirrors
// `OrgChart.processMutation.test.ts` for the tool sibling.
//
// The one most worth stating up front: `toolNodesLoaded` guards the lazy
// fetch `fetchToolNodes` runs on canvas-open. A mutation has to clear that
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

const TOOLS = [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' }]
const ROLES = [{ id: 'r1', name: 'Head of Sales' }, { id: 'r2', name: 'SRE' }]

/** GET responses. `tools` is swapped for the SECOND tool-nodes call, so a test
 * can tell the pre-mutation list apart from the post-mutation one. */
function respond(tools: unknown = TOOLS, afterTools: unknown = tools): void {
  let toolCalls = 0
  get.mockImplementation((url: string) => {
    if (url.includes('/tool-nodes')) {
      toolCalls += 1
      return Promise.resolve({ nodes: toolCalls === 1 ? tools : afterTools })
    }
    if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
    if (url.includes('/api/llc/roles/')) return Promise.resolve(ROLES)
    return Promise.resolve({ nodes: [] })
  })
}

function toolFetchCount(): number {
  return get.mock.calls.filter((c) => String(c[0]).includes('/tool-nodes')).length
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

describe('OrgChart tool attach/detach (#14597)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
    push.mockReset()
  })

  // A failed fetch and an empty answer are different claims, and a plain
  // absence of nodes on the canvas renders them identically. The pair below
  // is deliberate: neither test can pass on its own if the distinction is
  // dropped, because one demands the notice and the other forbids it.
  it('says "could not load" when the tool-nodes request fails, never "no tools"', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/tool-nodes')) return Promise.reject(new Error('HTTP 503: upstream'))
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      if (url.includes('/api/llc/roles/')) return Promise.resolve(ROLES)
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(wrapper.find('[data-testid="canvas-tools-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="canvas-no-tools"]').exists()).toBe(false)
    // Positive companion: the form is still there, so the assertion above
    // cannot be satisfied by the view having failed to render at all.
    expect(wrapper.find('[data-testid="tool-attach-form"]').exists()).toBe(true)
  })

  it('says "no tools" when the request answers with none, not "could not load"', async () => {
    respond([])
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    expect(wrapper.find('[data-testid="canvas-no-tools"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="canvas-tools-unavailable"]').exists()).toBe(false)
  })

  it('shows neither banner before the request has answered', async () => {
    // The company has people but no roles/tools sources have resolved yet at
    // the instant canvas mode opens — asserted via a controlled promise so
    // the assertion runs before the tool-nodes request settles.
    let resolveTools: (v: unknown) => void = () => {}
    get.mockImplementation((url: string) => {
      if (url.includes('/tool-nodes')) return new Promise((r) => { resolveTools = r })
      if (url.includes('/org-chart')) return Promise.resolve({ nodes: PEOPLE })
      if (url.includes('/api/llc/roles/')) return Promise.resolve(ROLES)
      return Promise.resolve({ nodes: [] })
    })
    const wrapper = await mountChart()
    await wrapper.find('[data-testid="org-view-canvas"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="canvas-tools-unavailable"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="canvas-no-tools"]').exists()).toBe(false)

    resolveTools({ nodes: [] })
    await flushPromises()
    expect(wrapper.find('[data-testid="canvas-no-tools"]').exists()).toBe(true)
  })

  it('renders a role with no tools without an error or an empty-looking box', async () => {
    respond([])
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    // No org-tool node at all — never an empty container claiming "no tools
    // exist" for a role that simply carries none.
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(0)
    expect(wrapper.find('[data-testid="canvas-no-tools"]').exists()).toBe(true)
  })

  it('disables the submit button while an attach is in flight, so it cannot post twice', async () => {
    respond([], TOOLS)
    let resolvePost: () => void = () => {}
    post.mockImplementation(() => new Promise<void>((r) => { resolvePost = () => r() }))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    await wrapper.find('[data-testid="tool-attach-role-select"]').setValue('r1')
    await wrapper.find('[data-testid="tool-attach-name-input"]').setValue('web_search')
    const submit = wrapper.find('[data-testid="tool-attach-submit"]')
    await submit.trigger('click')
    // Second click while the first is still in flight.
    await submit.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="tool-attach-submit"]').attributes('disabled')).toBeDefined()

    resolvePost()
    await flushPromises()
  })

  it('does not delete the same attachment twice when detached rapidly', async () => {
    respond(TOOLS, [])
    let resolveDel: () => void = () => {}
    del.mockImplementation(() => new Promise<void>((r) => { resolveDel = () => r() }))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('tool-detached', 'r1', 'web_search')
    canvas.vm.$emit('tool-detached', 'r1', 'web_search')
    await flushPromises()

    expect(del).toHaveBeenCalledTimes(1)
    resolveDel()
    await flushPromises()
  })

  it('detaches a tool from its own control and the node disappears', async () => {
    respond(TOOLS, [])
    del.mockResolvedValue(undefined)
    const wrapper = await mountChart()
    await openCanvas(wrapper)
    expect(toolFetchCount()).toBe(1)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('tool-detached', 'r1', 'web_search')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1/tools/web_search')
    // The refetch must actually re-run, not hit the `toolNodesLoaded` guard
    // and silently keep the stale list.
    expect(toolFetchCount()).toBe(2)
    const nodes = canvas.props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(0)
  })

  it('attaches a tool to a role from the canvas form and the node appears', async () => {
    respond([], TOOLS)
    post.mockResolvedValue(undefined)
    const wrapper = await mountChart()
    await openCanvas(wrapper)
    expect(toolFetchCount()).toBe(1)

    await wrapper.find('[data-testid="tool-attach-role-select"]').setValue('r1')
    await wrapper.find('[data-testid="tool-attach-name-input"]').setValue('web_search')
    await wrapper.find('[data-testid="tool-attach-submit"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1/r1/tools', { tool_name: 'web_search' })
    expect(toolFetchCount()).toBe(2)
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(1)
  })

  it('a failed detach surfaces an error and leaves the graph unchanged', async () => {
    respond(TOOLS)
    del.mockRejectedValue(new Error('HTTP 409: tool still in use'))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const canvas = wrapper.findComponent(WorkflowCanvas)
    canvas.vm.$emit('tool-detached', 'r1', 'web_search')
    await flushPromises()

    expect(wrapper.find('[data-testid="tool-mutation-error"]').text()).toBe(
      'HTTP 409: tool still in use',
    )
    // No optimistic mutation and no reload attempted on failure.
    expect(toolFetchCount()).toBe(1)
    const nodes = canvas.props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(1)
  })

  it('a failed attach surfaces an error and does not add a node', async () => {
    respond(TOOLS)
    post.mockRejectedValue(new Error('HTTP 400: unknown tool'))
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    await wrapper.find('[data-testid="tool-attach-role-select"]').setValue('r2')
    await wrapper.find('[data-testid="tool-attach-name-input"]').setValue('bogus_tool')
    await wrapper.find('[data-testid="tool-attach-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="tool-mutation-error"]').text()).toBe(
      'HTTP 400: unknown tool',
    )
    expect(toolFetchCount()).toBe(1)
    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(1)
  })

  it('a tool used by several roles is one node, not one per role', async () => {
    respond([
      { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'web_search' },
      { role_id: 'r2', role_name: 'SRE', tool_name: 'web_search' },
    ])
    const wrapper = await mountChart()
    await openCanvas(wrapper)

    const nodes = wrapper.findComponent(WorkflowCanvas).props('nodes') as { type: string }[]
    expect(nodes.filter((n) => n.type === 'org-tool')).toHaveLength(1)
  })
})
