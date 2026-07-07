// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#11129: ProjectBrowserView surfaces linked repo (code_source) and
// provides Attach / Sync / Detach actions.

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
// Render BaseModal slots inline (no Teleport) so inputs and buttons are
// accessible in the wrapper DOM — same pattern used by the debug-modal test.
vi.mock('@autobot/ui', () => ({
  BaseModal: {
    name: 'BaseModal',
    props: ['modelValue', 'title', 'size'],
    template: '<div v-if="modelValue" class="modal-stub"><slot /><slot name="actions" /></div>',
  },
}))

import ProjectBrowserView from '../ProjectBrowserView.vue'

const CODE_SOURCE = {
  id: 'cs1',
  repo: 'acme-org/backend',
  branch: 'main',
  clone_path: '/opt/autobot/repos/backend',
  status: 'ready',
  error_message: null,
}

const PROJECT_WITH_REPO = {
  id: 'p2',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Backend Service',
  description: null,
  status: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 3,
  active_sprint_name: null,
  code_source_id: 'cs1',
  code_source: CODE_SOURCE,
}

const PROJECT_NO_REPO = {
  id: 'p3',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Frontend App',
  description: null,
  status: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 0,
  active_sprint_name: null,
  code_source_id: null,
  code_source: null,
}

describe('ProjectBrowserView repo linkage (GH#11129)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
  })

  it('shows linked repo as a GitHub link and clone_path for a project with code_source', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_WITH_REPO])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    // The repo should appear as a hyperlink to GitHub
    const link = wrapper.find('a[href="https://github.com/acme-org/backend"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('acme-org/backend')

    // clone_path should be visible
    expect(wrapper.text()).toContain('/opt/autobot/repos/backend')

    // status badge should appear
    expect(wrapper.text()).toContain('ready')
  })

  it('shows "Attach repo" button for a project without code_source', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_NO_REPO])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    expect(wrapper.text()).toContain('Attach repo')
  })

  it('calls POST /api/llc/projects/{id}/repo when Attach repo is submitted', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_NO_REPO])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    post.mockResolvedValue({
      ...PROJECT_NO_REPO,
      code_source_id: 'cs2',
      code_source: { ...CODE_SOURCE, id: 'cs2', repo: 'acme-org/new' },
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    // Open the attach modal by clicking "Attach repo" on the project card
    const attachBtn = wrapper.findAll('button').find(b => b.text().includes('Attach repo'))
    expect(attachBtn).toBeDefined()
    await attachBtn!.trigger('click')
    await flushPromises()

    // Modal is now rendered inline by the stub (v-if="modelValue" + slot render).
    // First input in the modal form is the owner/repo field.
    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThan(0)
    await inputs[0].setValue('acme-org/new')

    // Click the submit "Attach" button (the one inside the modal actions slot,
    // which has text "Attach" rather than "Attach repo")
    const attachBtns = wrapper.findAll('button').filter(b => b.text() === 'Attach')
    const submitBtn = attachBtns[attachBtns.length - 1]
    expect(submitBtn).toBeDefined()
    await submitBtn.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith(
      '/api/llc/projects/p3/repo',
      expect.objectContaining({ repo: 'acme-org/new' }),
    )
  })

  it('shows Detach button for a project with code_source and calls DELETE on click', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_WITH_REPO])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    del.mockResolvedValue({})

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const detachBtn = wrapper.findAll('button').find(b => b.text().includes('Detach'))
    expect(detachBtn).toBeDefined()
    await detachBtn!.trigger('click')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/projects/p2/repo')
  })

  it('GH#11129: renders a copy button with aria-label next to clone_path', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT_WITH_REPO])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const copyBtn = wrapper.find('button[aria-label]')
    expect(copyBtn.exists()).toBe(true)
    // The aria-label contains the i18n key text for copy clone path
    const ariaLabel = copyBtn.attributes('aria-label') ?? ''
    expect(ariaLabel.length).toBeGreaterThan(0)
  })
})
