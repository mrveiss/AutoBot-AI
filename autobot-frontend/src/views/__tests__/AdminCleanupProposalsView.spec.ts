// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for AdminCleanupProposalsView.vue (#20567): status with counts, propose -> review queue.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: { get: mockGet, post: mockPost } }))
// The ui kit barrel pulls reka-ui; only the button is used here.
vi.mock('@autobot/ui', () => ({
  log: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
  BaseButton: {
    props: ['disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => ({ selectedCompanyId: '' }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import AdminCleanupProposalsView from '../AdminCleanupProposalsView.vue'

function mountView() {
  return mount(AdminCleanupProposalsView, {
    global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('AdminCleanupProposalsView.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockImplementation(async (url: string) =>
      url.endsWith('org-tier-column')
        ? { present: false }
        : { count: 2, detail: 'two things', refused: null },
    )
  })

  it('shows a count per cleanup and disables Propose when there is nothing to do', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('Found: 2.')
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(3)
    expect(buttons[2].attributes('disabled')).toBeDefined()
  })

  it('proposing reports the review queue and calls the requests route', async () => {
    mockPost.mockResolvedValue({ approval_id: 'a1', status: 'pending', action: 'x' })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledWith('/api/admin/env-copies-cleanup/requests')
    expect(wrapper.text()).toContain('review queue')
  })
})
