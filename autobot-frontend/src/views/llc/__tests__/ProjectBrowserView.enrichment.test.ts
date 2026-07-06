// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#10232: ProjectBrowserView renders the enriched card fields (open-item
// count, active sprint) and a velocity sparkline fed by the velocity endpoint.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()

// vue-i18n 11 requires the plugin be installed via app.use(); load the real
// en.json messages so the card text assertions ("7 open", "No active sprint")
// resolve against the actual translations.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountOpts = { global: { plugins: [i18n], stubs: { LlcBreadcrumb: true } } }

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1', programId: 'pr1' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))

import ProjectBrowserView from '../ProjectBrowserView.vue'

const PROJECT = {
  id: 'p1',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Apollo',
  description: null,
  status: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 7,
  active_sprint_name: 'Sprint 3',
}

describe('ProjectBrowserView enrichment (GH#10232)', () => {
  beforeEach(() => get.mockReset())

  it('shows open-item count, active sprint, and a velocity sparkline', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([PROJECT])
      if (url?.includes('/velocity')) {
        return Promise.resolve({ sprints: [{ velocity: 8 }, { velocity: 5 }, { velocity: 11 }] })
      }
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    expect(wrapper.text()).toContain('7 open')
    expect(wrapper.text()).toContain('Sprint 3')
    expect(wrapper.find('.card-velocity svg').exists()).toBe(true)
  })

  it('falls back to "No active sprint" and hides the sparkline when velocity is sparse', async () => {
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) {
        return Promise.resolve([{ ...PROJECT, active_sprint_name: null, open_work_item_count: 0 }])
      }
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [{ velocity: 8 }] })
      return Promise.resolve([])
    })

    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    expect(wrapper.text()).toContain('No active sprint')
    expect(wrapper.find('.card-velocity').exists()).toBe(false)
  })
})
