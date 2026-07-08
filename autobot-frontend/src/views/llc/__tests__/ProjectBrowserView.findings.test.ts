// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#11271 T8: project findings proposal queue UI — scan / promote / dismiss affordances.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountOpts = { global: { plugins: [i18n], stubs: { LlcBreadcrumb: true } } }

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1', programId: 'pr1' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@autobot/ui', () => ({
  BaseModal: {
    name: 'BaseModal',
    props: ['modelValue', 'title', 'size'],
    template: '<div v-if="modelValue" class="modal-stub"><slot /><slot name="actions" /></div>',
  },
}))

import ProjectBrowserView from '../ProjectBrowserView.vue'

const PROJECT_WITH_REPO = {
  id: 'p-with-repo',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Repo Project',
  description: null,
  status: 'active',
  lifecycle_state: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 0,
  active_sprint_name: null,
  code_source_id: 'src-1',
  code_source: {
    id: 'src-1',
    repo: 'acme/backend',
    branch: 'main',
    clone_path: '/tmp/acme',
    status: 'ready',
    error_message: null,
  },
}

const PROPOSAL = {
  id: 'prop-1',
  project_id: 'p-with-repo',
  company_id: 'c1',
  source_id: 'src-1',
  finding_key: 'src-1:src/app.py:42:bug',
  finding_type: 'bug',
  severity: 'high',
  file_path: 'src/app.py',
  line_number: 42,
  description: 'Unhandled exception in handler',
  suggestion: 'Add try/except',
  verdict_is_real: true,
  verdict_confidence: 0.92,
  verdict_rationale: 'The exception is genuinely unhandled.',
  status: 'pending',
  work_item_id: null,
  dismiss_reason: null,
}

function makeGetMock(proposals: unknown[] = [PROPOSAL]) {
  return (url?: string) => {
    if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_WITH_REPO])
    if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
    if (url?.includes('/findings/proposals')) return Promise.resolve(proposals)
    return Promise.resolve([])
  }
}

describe('ProjectBrowserView findings proposal queue (GH#11271 T8)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
    vi.restoreAllMocks()
  })

  it('renders a proposal row with severity badge, file:line, description, verdict rationale', async () => {
    get.mockImplementation(makeGetMock())

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    // Proposal list is loaded; expect the severity, file:line and rationale to be visible.
    expect(wrapper.text()).toContain('src/app.py:42')
    expect(wrapper.text()).toContain('Unhandled exception in handler')
    expect(wrapper.text()).toContain('The exception is genuinely unhandled.')
    // Severity badge should be present
    const badge = wrapper.find('.finding-severity')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('high')
  })

  it('Scan button calls POST /api/llc/projects/{id}/findings/scan and refreshes proposals', async () => {
    get.mockImplementation(makeGetMock([]))
    post.mockResolvedValue({ gathered: 3, verified_real: 2, queued: 2 })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const scanBtn = wrapper.findAll('button').find(b => b.text().includes('Scan'))
    expect(scanBtn).toBeDefined()
    await scanBtn!.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/projects/p-with-repo/findings/scan')
    // After scan, proposals list re-fetch should have been called
    const getCalls = get.mock.calls.map(c => c[0] as string)
    expect(getCalls.some(u => u?.includes('/findings/proposals'))).toBe(true)
  })

  it('Promote button calls POST /api/llc/findings/proposals/{id}/promote and refreshes', async () => {
    get.mockImplementation(makeGetMock())
    post.mockResolvedValue({ id: 'wi-1', title: 'Unhandled exception in handler' })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const promoteBtn = wrapper.findAll('button').find(b => b.text().includes('Promote'))
    expect(promoteBtn).toBeDefined()
    await promoteBtn!.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/findings/proposals/prop-1/promote')
    // Proposals list should have been refreshed
    const getCalls = get.mock.calls.map(c => c[0] as string)
    expect(getCalls.filter(u => u?.includes('/findings/proposals')).length).toBeGreaterThan(1)
  })

  it('Dismiss button prompts for reason, then calls POST /api/llc/findings/proposals/{id}/dismiss', async () => {
    get.mockImplementation(makeGetMock())
    post.mockResolvedValue({})
    vi.spyOn(window, 'prompt').mockReturnValue('Not a real bug')

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const dismissBtn = wrapper.findAll('button').find(b => b.text().includes('Dismiss'))
    expect(dismissBtn).toBeDefined()
    await dismissBtn!.trigger('click')
    await flushPromises()

    expect(window.prompt).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith(
      '/api/llc/findings/proposals/prop-1/dismiss',
      { reason: 'Not a real bug' },
    )
  })

  it('Dismiss with cancelled prompt does NOT call POST dismiss', async () => {
    get.mockImplementation(makeGetMock())
    vi.spyOn(window, 'prompt').mockReturnValue(null)

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const dismissBtn = wrapper.findAll('button').find(b => b.text().includes('Dismiss'))
    expect(dismissBtn).toBeDefined()
    await dismissBtn!.trigger('click')
    await flushPromises()

    expect(window.prompt).toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })
})
