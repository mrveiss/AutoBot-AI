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
const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { status, isHttpError: true })

vi.mock('@/utils/ApiClient', () => ({ default: { get: mockGet, post: mockPost } }))
// The ui kit barrel pulls reka-ui; only the button is used here.
vi.mock('@autobot/ui', () => ({
  log: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
  BaseButton: {
    props: ['disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
  BaseCard: { template: '<section><slot /></section>' },
  BaseAlert: { props: ['message'], template: '<p>{{ message }}</p>' },
  PageHeader: { template: '<header />' },
  isHttpError: (e: unknown) => !!(e as { isHttpError?: boolean })?.isHttpError,
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
    expect(buttons).toHaveLength(2)
    expect(buttons[1].attributes('disabled')).toBeDefined()
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

  it('a refused POST shows a localised reason, not the server text, and re-enables the button', async () => {
    mockPost.mockRejectedValue(Object.assign(httpError(409), { detail: 'RAW-SERVER-ENGLISH' }))
    const wrapper = mountView()
    await flushPromises()
    const button = wrapper.findAll('button')[0]
    await button.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(en.admin.cleanup.proposeRefused)
    expect(wrapper.text()).not.toContain('RAW-SERVER-ENGLISH')
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('a forbidden POST and an unexpected failure each get their own localised message', async () => {
    mockPost.mockRejectedValueOnce(httpError(403))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(en.admin.cleanup.proposeForbidden)
    mockPost.mockRejectedValueOnce(new Error('boom'))
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(en.admin.cleanup.proposeFailed)
  })

  it('a refused plan omits the count and shows the localised refusal', async () => {
    mockGet.mockImplementation(async () => ({ count: 0, detail: 'RAW-REFUSAL', refused: 'RAW-REFUSAL' }))
    const wrapper = mountView()
    await flushPromises()
    const card = wrapper.get('[data-testid="cleanup-envCopies"]').text()
    expect(card).toContain(en.admin.cleanup.refused)
    expect(card).not.toContain('Found: 0')
    expect(card).not.toContain('RAW-REFUSAL')
  })
})
