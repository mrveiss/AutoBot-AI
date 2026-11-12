// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #18431 on screen: a page per role, workflow, process and meta skill, read from the company
 * model's routes. A source that cannot be read says so (it is not "no pages"), an empty company
 * says it has none, and the parts with no backend are listed as not available.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

type Params = { companyId: string }
const { get, holder } = vi.hoisted(() => ({ get: vi.fn(), holder: {} as { params?: Params } }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  holder.params = reactive<Params>({ companyId: 'c1' })
  return { useRoute: () => ({ params: holder.params }) }
})

import HandbookView from '../HandbookView.vue'

type Scope = { headers?: Record<string, string> } | undefined
type Pending = { resolve: (rows: unknown) => void; reject: (err: Error) => void }

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const ROLE_A = { id: 'r1', company_id: 'c1', name: 'Finance lead', description: 'Keeps the books.', is_system: false }
const ROLE_B = { id: 'r2', company_id: 'c1', name: 'Support agent', description: null, is_system: false }
const WORKFLOW = {
  workflow_id: 'wf-invoice', kind: 'workflow', name: 'Send invoice', status: 'active', owner_role_id: 'r1',
  trigger_type: 'manual', trigger_config: {}, created_at: '', updated_at: '',
}
const META = { ...WORKFLOW, workflow_id: 'ms-check', kind: 'meta_skill', name: 'Check totals', owner_role_id: null, trigger_type: null }
const PROCESS = {
  process_key: 'p-ledger', name: 'Reconcile ledger', description: 'Match every payment.', owner_role_id: 'r1',
  required_skills: ['bookkeeping'], created_at: '', updated_at: '',
}
const ROLE_C = { id: 'r9', company_id: 'c2', name: 'Second company lead', description: 'Runs c2.', is_system: false }
const PROCESS_C = { ...PROCESS, process_key: 'p-c2', name: 'Second company process', owner_role_id: 'r9' }
const GRAPH = {
  graph: {
    nodes: [
      { key: 's', kind: 'start' },
      { key: 'a', kind: 'process', process_key: 'p-ledger' },
      { key: 'e', kind: 'end', end_outcome: 'done' },
    ],
    transitions: [
      { from_node: 's', kind: 'success', to_node: 'a' },
      { from_node: 'a', kind: 'failure', to_node: 'e', retry_max: 2 },
    ],
  },
  validation: { errors: [], warnings: [] },
}

const orgOf = (url: string, scope: Scope): string => scope?.headers?.['X-Organization-Id'] ?? /roles\/(c\d)/.exec(url)?.[1] ?? ''

/** Requests for the held company stay pending until a test settles them. */
function serve(overrides: Record<string, unknown> = {}, hold: { company: string; pending: Pending[] } | null = null) {
  const routes: Record<string, unknown> = {
    '/api/llc/roles/c1': [ROLE_A, ROLE_B],
    '/api/llc/roles/c2': [ROLE_C],
    '/api/llc/company-os/workflows': [WORKFLOW, META],
    '/api/llc/company-os/processes': [PROCESS],
    '/api/llc/roles/c1/r1/holders?include_past=false': [{ id: 'h1', role_id: 'r1', holder_type: 'user', holder_id: 'alice' }],
    '/api/llc/roles/c1/r1/workflows': ['wf-invoice'],
    '/api/llc/roles/c1/r1/tools': ['ledger-export'],
    '/api/llc/company-os/roles/r1/skills': { role_id: 'r1', skills: [{ skill: 'bookkeeping', sources: [] }], grants: [] },
    '/api/llc/company-os/workflows/wf-invoice/graph': GRAPH,
    ...overrides,
  }
  get.mockImplementation(async (url: string, scope: Scope) => {
    if (hold && orgOf(url, scope) === hold.company) {
      return new Promise((resolve, reject) => hold.pending.push({ resolve, reject }))
    }
    const hit = routes[url]
    if (hit instanceof Error) throw hit
    if (hit === undefined) throw new Error(`HTTP 404: ${url}`)
    return hit
  })
}

async function mountView() {
  const w = mount(HandbookView, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}
const openPage = async (w: Awaited<ReturnType<typeof mountView>>, title: string) => {
  const link = w.findAll('[data-testid="handbook-page-link"]').find((l) => l.text().startsWith(title))
  await link!.trigger('click')
  await flushPromises()
}

describe('HandbookView (#18431)', () => {
  beforeEach(() => {
    get.mockReset()
    holder.params!.companyId = 'c1'
  })

  it('lists a page for every role, workflow, process and meta skill, from the model', async () => {
    serve()
    const w = await mountView()
    const titles = w.findAll('[data-testid="handbook-page-link"]').map((l) => l.text())
    expect(titles).toHaveLength(5)
    for (const name of ['Finance lead', 'Support agent', 'Send invoice', 'Check totals', 'Reconcile ledger']) {
      expect(titles.some((t) => t.startsWith(name))).toBe(true)
    }
    expect(w.findAll('[data-testid="handbook-coverage-count"]').map((c) => c.text())).toEqual([
      'Roles: 2', 'Workflows: 1', 'Processes: 1', 'Meta skills: 1',
    ])
  })

  it('lists roles and processes whose model records no description as the coverage gap', async () => {
    serve()
    const w = await mountView()
    const missing = w.get('[data-testid="handbook-coverage-missing"]').text()
    expect(missing).toContain('Support agent')
    expect(missing).not.toContain('Finance lead')
    expect(missing).not.toContain('Reconcile ledger')
  })

  it('a role page shows its description, holders, workflows, owned processes, skills and tools', async () => {
    serve()
    const w = await mountView()
    await openPage(w, 'Finance lead')
    expect(w.get('[data-testid="handbook-description"]').text()).toBe('Keeps the books.')
    expect(w.get('[data-testid="handbook-holders"]').text()).toContain('alice')
    expect(w.get('[data-testid="handbook-role-workflows"]').text()).toContain('Send invoice')
    expect(w.get('[data-testid="handbook-role-processes"]').text()).toContain('Reconcile ledger')
    expect(w.get('[data-testid="handbook-role-skills"]').text()).toContain('bookkeeping')
    expect(w.get('[data-testid="handbook-role-tools"]').text()).toContain('ledger-export')
  })

  it('a workflow page writes its graph out in words, with the owner role and trigger', async () => {
    serve()
    const w = await mountView()
    await openPage(w, 'Send invoice')
    expect(w.get('[data-testid="handbook-owner"]').text()).toBe('Owned by Finance lead')
    expect(w.get('[data-testid="handbook-trigger"]').text()).toBe('Started by hand')
    const steps = w.get('[data-testid="handbook-steps"]').text()
    expect(steps).toContain('Then: Reconcile ledger')
    expect(steps).toContain('If it fails: retry 2 times, then Finished: done')
  })

  it('a part that cannot be read is named on the page, never shown as an empty list', async () => {
    serve({ '/api/llc/roles/c1/r1/holders?include_past=false': new Error('HTTP 500: boom') })
    const w = await mountView()
    await openPage(w, 'Finance lead')
    expect(w.get('[data-testid="handbook-page-failed"]').text()).toContain('holders')
    expect(w.text()).not.toContain(en.llc.handbook.noHolders)
  })

  it('a source that cannot be read says so and is not read as an empty company', async () => {
    serve({ '/api/llc/company-os/processes': new Error('HTTP 503: model down') })
    const w = await mountView()
    expect(w.get('[data-testid="handbook-error"]').text()).toContain('model down')
    expect(w.find('[data-testid="handbook-empty"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="handbook-page-link"]')).toHaveLength(4)
  })

  it('a source that cannot be read leaves its coverage unknown, never counted as zero', async () => {
    serve({ '/api/llc/company-os/processes': new Error('HTTP 503: model down') })
    const w = await mountView()
    const counts = w.findAll('[data-testid="handbook-coverage-count"]').map((c) => c.text())
    expect(counts).toContain(`${en.llc.handbook.kindPlural.process}: ${en.llc.handbook.coverage.unread}`)
    expect(counts.join()).not.toContain(`${en.llc.handbook.kindPlural.process}: 0`)
    expect(w.get('[data-testid="handbook-coverage-partial"]').text()).toBe(en.llc.handbook.coverage.partial)
  })

  it('with every source read, each source\'s content is rendered, with counts and no partial note', async () => {
    serve()
    const w = await mountView()
    const text = w.findAll('[data-testid="handbook-page-link"]').map((l) => l.text()).join('|')
    for (const name of ['Finance lead', 'Support agent', 'Send invoice', 'Check totals', 'Reconcile ledger']) {
      expect(text).toContain(name)
    }
    expect(w.findAll('[data-testid="handbook-coverage-count"]').map((c) => c.text())).toEqual([
      'Roles: 2', 'Workflows: 1', 'Processes: 1', 'Meta skills: 1',
    ])
    expect(w.text()).not.toContain(en.llc.handbook.coverage.unread)
    expect(w.find('[data-testid="handbook-coverage-partial"]').exists()).toBe(false)
    expect(w.find('[data-testid="handbook-error"]').exists()).toBe(false)
  })

  it('a slow load for the first company that settles after a switch does not overwrite the second company', async () => {
    const hold = { company: 'c1', pending: [] as Pending[] }
    serve({ '/api/llc/company-os/workflows': [], '/api/llc/company-os/processes': [PROCESS_C] }, hold)
    const w = mount(HandbookView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(hold.pending).toHaveLength(3)
    hold.company = 'none'
    holder.params!.companyId = 'c2'
    await flushPromises()
    const first = hold.pending.splice(0)
    expect(w.findAll('[data-testid="handbook-page-link"]').some((l) => l.text().startsWith('Second company lead'))).toBe(true)
    first[0].resolve([ROLE_A])
    first[1].resolve([WORKFLOW])
    first[2].resolve([PROCESS])
    await flushPromises()
    const titles = w.findAll('[data-testid="handbook-page-link"]').map((l) => l.text())
    expect(titles.some((t) => t.startsWith('Second company lead'))).toBe(true)
    expect(titles.some((t) => t.startsWith('Finance lead') || t.startsWith('Send invoice'))).toBe(false)
  })

  it('a slow load for the first company that fails after a switch shows no error for the second', async () => {
    const hold = { company: 'c1', pending: [] as Pending[] }
    serve({ '/api/llc/company-os/processes': [PROCESS_C] }, hold)
    const w = mount(HandbookView, { global: { plugins: [i18n] } })
    await flushPromises()
    hold.company = 'none'
    holder.params!.companyId = 'c2'
    await flushPromises()
    for (const p of hold.pending.splice(0)) p.reject(new Error('HTTP 500: stale boom'))
    await flushPromises()
    expect(w.find('[data-testid="handbook-error"]').exists()).toBe(false)
    expect(w.text()).not.toContain('stale boom')
    expect(w.text()).toContain('Second company process')
    expect(w.find('[data-testid="handbook-coverage-partial"]').exists()).toBe(false)
  })

  it('workflows and processes are asked for in the route company\'s scope, after a switch too', async () => {
    serve()
    const w = await mountView()
    const scopeOf = (url: string): string[] =>
      get.mock.calls.filter((c) => c[0] === url).map((c) => (c[1] as Scope)?.headers?.['X-Organization-Id'] ?? '')
    expect(scopeOf('/api/llc/company-os/workflows')).toEqual(['c1'])
    expect(scopeOf('/api/llc/company-os/processes')).toEqual(['c1'])
    holder.params!.companyId = 'c2'
    await flushPromises()
    expect(scopeOf('/api/llc/company-os/workflows')).toEqual(['c1', 'c2'])
    expect(scopeOf('/api/llc/company-os/processes')).toEqual(['c1', 'c2'])
    expect(w.exists()).toBe(true)
  })

  it('a page\'s own Company OS reads (graph, role skills) carry the route company\'s scope', async () => {
    serve()
    const w = await mountView()
    await openPage(w, 'Send invoice')
    await openPage(w, 'Finance lead')
    const scoped = (url: string): unknown => get.mock.calls.find((c) => c[0] === url)?.[1]
    expect(scoped('/api/llc/company-os/workflows/wf-invoice/graph')).toEqual({ headers: { 'X-Organization-Id': 'c1' } })
    expect(scoped('/api/llc/company-os/roles/r1/skills')).toEqual({ headers: { 'X-Organization-Id': 'c1' } })
  })

  it('a role page reads all four parts and names only the one that failed', async () => {
    serve({ '/api/llc/roles/c1/r1/tools': new Error('HTTP 500: tools down') })
    const w = await mountView()
    get.mockClear()
    await openPage(w, 'Finance lead')
    expect(get).toHaveBeenCalledTimes(4)
    expect(w.get('[data-testid="handbook-page-failed"]').text()).toContain('tools')
    expect(w.get('[data-testid="handbook-holders"]').text()).toContain('alice')
    expect(w.get('[data-testid="handbook-role-skills"]').text()).toContain('bookkeeping')
  })

  it('a company with no roles, workflows or processes says it has none', async () => {
    serve({ '/api/llc/roles/c1': [], '/api/llc/company-os/workflows': [], '/api/llc/company-os/processes': [] })
    const w = await mountView()
    expect(w.find('[data-testid="handbook-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="handbook-error"]').exists()).toBe(false)
  })

  it('lists every part with no backend as not available, with no stand-in content', async () => {
    serve()
    const w = await mountView()
    expect(w.findAll('[data-testid="handbook-unavailable-item"]')).toHaveLength(6)
    expect(w.get('[data-testid="handbook-unavailable"]').text()).toContain(en.llc.handbook.unavailable.onboarding)
  })

  it('lists the roles and processes without a description under a label that names those kinds', async () => {
    serve()
    const w = await mountView()
    expect(w.text()).toContain('Roles and processes without a recorded description (1)')
  })

  it('search narrows the page list by title', async () => {
    serve()
    const w = await mountView()
    await w.get('[data-testid="handbook-search"] input').setValue('invoice')
    const titles = w.findAll('[data-testid="handbook-page-link"]').map((l) => l.text())
    expect(titles).toHaveLength(1)
    expect(titles[0]).toContain('Send invoice')
  })
})
