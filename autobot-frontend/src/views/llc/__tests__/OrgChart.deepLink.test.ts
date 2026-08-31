// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14611: the inbound deep link — `?node=<id>` opens the canvas already
// focused on a node, the counterpart to #13963's outbound `?workflow=<id>`
// link. These tests pin:
//
//  * no `?node=` query leaves the view exactly as before (tree, not canvas);
//  * a real node auto-opens the canvas, focuses it, and opens the same
//    drawer a click would;
//  * a node this company does not have (removed, or the reader lacks access)
//    reads as "not found" — never as an empty or unresponsive canvas
//    (#14064/#13617/#14556's repeat conflation);
//  * "not found" cannot appear before the lazy canvas sources have actually
//    answered — an unresolved request must not look decided.

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

// A mutable query the mock reads fresh on every `useRoute()` call, so each
// test can point a fresh mount at a different `?node=` without a second
// `vi.mock` factory.
let currentQuery: Record<string, unknown> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ params: { companyId: 'c1' }, query: currentQuery }),
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

const CEO = {
  id: 'ceo',
  name: 'Ada Lovelace',
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
}

/** Resolves every request instantly — used by every test except the one
 *  pinning the "not found before the sources answer" ordering, which needs
 *  to hold `/process-nodes` open on purpose. */
function respond({ processNodesDeferred = false }: { processNodesDeferred?: boolean } = {}) {
  let resolveProcessNodes: (() => void) | null = null
  const processNodesPromise = processNodesDeferred
    ? new Promise<{ nodes: unknown[] }>((resolve) => {
        resolveProcessNodes = () => resolve({ nodes: [] })
      })
    : Promise.resolve({ nodes: [] })

  get.mockImplementation((url: string) => {
    if (url === '/api/llc/companies/c1/org-chart') return Promise.resolve({ nodes: [CEO] })
    if (url === '/api/llc/companies/c1/process-nodes') return processNodesPromise
    if (url === '/api/llc/companies/c1/tool-nodes') return Promise.resolve({ nodes: [] })
    if (url === '/api/llc/roles/c1') return Promise.resolve([])
    if (url === '/api/llc/contacts/c1/involved') return Promise.resolve({ with_role: [], unassigned: [] })
    if (url === '/api/llc/companies/c1/teams') return Promise.resolve({ teams: [] })
    if (url === '/api/llc/companies/c1/work-items/executor-rollup') return Promise.resolve({ cells: [] })
    throw new Error(`unexpected GET ${url}`)
  })
  return { resolveProcessNodes: () => resolveProcessNodes?.() }
}

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, HireAgentModal: true, OrgPeopleList: true } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  push.mockReset()
  currentQuery = {}
})

describe('no ?node= query (#14611)', () => {
  it('leaves the default tree view exactly as before', async () => {
    respond()
    const wrapper = await mountChart()

    expect(wrapper.find('[data-testid="org-canvas"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="canvas-deeplink-not-found"]').exists()).toBe(false)
  })
})

describe('a link to a real node (#14611)', () => {
  it('auto-opens the canvas, focused on the node — no not-found banner', async () => {
    currentQuery = { node: 'ceo' }
    respond()
    const wrapper = await mountChart()

    expect(wrapper.find('[data-testid="org-canvas"]').exists()).toBe(true)
    expect(wrapper.findComponent(WorkflowCanvas).props('focusNodeId')).toBe('ceo')
    expect(wrapper.find('[data-testid="canvas-deeplink-not-found"]').exists()).toBe(false)
    // Paired positive: the canvas is not empty — the node the link named is
    // actually among what it draws.
    const nodeIds = (wrapper.findComponent(WorkflowCanvas).props('nodes') as { id: string }[]).map(
      (n) => n.id,
    )
    expect(nodeIds).toContain('ceo')
  })

  it('opens the same sidebar drawer a click on the node would', async () => {
    currentQuery = { node: 'ceo' }
    respond()
    const wrapper = await mountChart()

    const sidebar = wrapper.findComponent({ name: 'CanvasNodeSidebar' })
    expect(sidebar.exists()).toBe(true)
    expect(sidebar.props('node')).toMatchObject({ id: 'ceo', name: 'Ada Lovelace' })
  })

  it('a stale/repeated query param takes the first, matching workflowIdFromQuery\'s own rule', async () => {
    currentQuery = { node: ['ceo', 'someone-else'] }
    respond()
    const wrapper = await mountChart()

    expect(wrapper.findComponent(WorkflowCanvas).props('focusNodeId')).toBe('ceo')
  })
})

describe('a link to a node this company does not have (#14611)', () => {
  it('reads as "not found", never as an empty or unresponsive canvas', async () => {
    currentQuery = { node: 'ghost' }
    respond()
    const wrapper = await mountChart()

    expect(wrapper.get('[data-testid="canvas-deeplink-not-found"]').text()).toBe(
      en.llc.orgChart.deepLinkNodeNotFound,
    )
    // Paired positive: switching to canvas mode still drew the real graph —
    // the banner is a fact about the link, not a crashed/empty render.
    const nodeIds = (wrapper.findComponent(WorkflowCanvas).props('nodes') as { id: string }[]).map(
      (n) => n.id,
    )
    expect(nodeIds).toContain('ceo')
    expect(wrapper.findComponent(WorkflowCanvas).props('focusNodeId')).toBeNull()
  })

  it('does not report "not found" until every lazy canvas source has actually answered', async () => {
    currentQuery = { node: 'ghost' }
    const { resolveProcessNodes } = respond({ processNodesDeferred: true })
    const wrapper = mount(OrgChart, {
      global: { plugins: [i18n], stubs: { CanvasNodeSidebar: true, HireAgentModal: true, OrgPeopleList: true } },
    })
    await flushPromises()

    // The tree itself, tools, roles and teams have all answered — only
    // /process-nodes is still pending — so "not found" must not have fired yet.
    expect(wrapper.find('[data-testid="canvas-deeplink-not-found"]').exists()).toBe(false)

    resolveProcessNodes()
    await flushPromises()

    expect(wrapper.get('[data-testid="canvas-deeplink-not-found"]').text()).toBe(
      en.llc.orgChart.deepLinkNodeNotFound,
    )
  })
})

describe('an empty or whitespace ?node= (#14611)', () => {
  it('is treated as no request at all, same as workflowIdFromQuery', async () => {
    currentQuery = { node: '   ' }
    respond()
    const wrapper = await mountChart()

    expect(wrapper.find('[data-testid="org-canvas"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="canvas-deeplink-not-found"]').exists()).toBe(false)
  })
})
