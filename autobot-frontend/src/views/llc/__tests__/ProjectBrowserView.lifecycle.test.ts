// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#11129 P2: archive / delete (dispose) / restore lifecycle affordances on
// ProjectBrowserView — lifecycle badge, Archive, Delete, Restore actions.

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

const ACTIVE_PROJECT = {
  id: 'p-active',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Active Project',
  description: null,
  status: 'active',
  lifecycle_state: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 2,
  active_sprint_name: null,
  code_source_id: null,
  code_source: null,
}

const ARCHIVED_PROJECT = {
  id: 'p-archived',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Archived Project',
  description: null,
  status: 'active',
  lifecycle_state: 'archived',
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

const PENDING_DISPOSAL_PROJECT = {
  ...ARCHIVED_PROJECT,
  id: 'p-pending',
  name: 'Pending Disposal Project',
  lifecycle_state: 'pending_disposal',
}

describe('ProjectBrowserView lifecycle affordances (GH#11129 P2)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
    vi.restoreAllMocks()
  })

  it('shows the lifecycle badge for an active project', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ACTIVE_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    // The lifecycle badge should display "Active" (from i18n key llcBrowser.lifecycle.active)
    expect(wrapper.text()).toContain('Active')
    const badge = wrapper.find('.lifecycle-badge')
    expect(badge.exists()).toBe(true)
  })

  it('shows the lifecycle badge for an archived project', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ARCHIVED_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const badge = wrapper.find('.lifecycle-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('Archived')
  })

  it('shows Archive button for an active project', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ACTIVE_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const archiveBtn = wrapper.findAll('button').find(b => b.text().includes('Archive'))
    expect(archiveBtn).toBeDefined()
    expect(archiveBtn!.exists()).toBe(true)
  })

  it('clicking Archive calls POST /api/llc/projects/{id}/archive and refreshes', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ACTIVE_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    post.mockResolvedValue({ ...ACTIVE_PROJECT, lifecycle_state: 'archived' })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const archiveBtn = wrapper.findAll('button').find(b => b.text().includes('Archive'))
    expect(archiveBtn).toBeDefined()
    await archiveBtn!.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/projects/p-active/archive')
  })

  it('shows Delete and Restore buttons for an archived project', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ARCHIVED_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const deleteBtn = buttons.find(b => b.text().includes('Delete'))
    const restoreBtn = buttons.find(b => b.text().includes('Restore'))

    expect(deleteBtn).toBeDefined()
    expect(deleteBtn!.exists()).toBe(true)
    expect(restoreBtn).toBeDefined()
    expect(restoreBtn!.exists()).toBe(true)
  })

  it('clicking Restore calls POST /api/llc/projects/{id}/restore and refreshes', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ARCHIVED_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    post.mockResolvedValue({ ...ARCHIVED_PROJECT, lifecycle_state: 'active' })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const restoreBtn = wrapper.findAll('button').find(b => b.text().includes('Restore'))
    expect(restoreBtn).toBeDefined()
    await restoreBtn!.trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledWith('/api/llc/projects/p-archived/restore')
  })

  it('clicking confirmed Delete calls POST /api/llc/projects/{id}/dispose and refreshes', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ARCHIVED_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    post.mockResolvedValue({ result: 'disposed' })

    // Confirm dialog should return true
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const deleteBtn = wrapper.findAll('button').find(b => b.text().includes('Delete'))
    expect(deleteBtn).toBeDefined()
    await deleteBtn!.trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(post).toHaveBeenCalledWith('/api/llc/projects/p-archived/dispose')
  })

  it('cancelled Delete does NOT call POST dispose', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([ARCHIVED_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    vi.spyOn(window, 'confirm').mockReturnValue(false)

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const deleteBtn = wrapper.findAll('button').find(b => b.text().includes('Delete'))
    expect(deleteBtn).toBeDefined()
    await deleteBtn!.trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('shows Delete and Restore for pending_disposal project', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PENDING_DISPOSAL_PROJECT])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const deleteBtn = buttons.find(b => b.text().includes('Delete'))
    const restoreBtn = buttons.find(b => b.text().includes('Restore'))
    expect(deleteBtn?.exists()).toBe(true)
    expect(restoreBtn?.exists()).toBe(true)
  })
})
