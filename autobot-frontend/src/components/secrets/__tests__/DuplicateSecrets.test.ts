// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #17850: duplicated stored credentials on the Secrets page -- counts and vaults only, propose through the
 * approval queue, and Propose stays available while groups remain after a capped request.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { status, isHttpError: true })

vi.mock('@/utils/ApiClient', () => ({ default: { get: mockGet, post: mockPost } }))
vi.mock('@autobot/ui', () => ({
  log: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
  BaseButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  BaseCard: { template: '<section><slot /></section>' },
  BaseAlert: { props: ['message'], template: '<p>{{ message }}</p>' },
  isHttpError: (e: unknown) => !!(e as { isHttpError?: boolean })?.isHttpError,
}))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => ({ selectedCompanyId: '' }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import DuplicateSecrets from '../DuplicateSecrets.vue'

const status = (groups: number, copies: number) => ({
  group_count: groups,
  copy_count: copies,
  groups: groups ? [{ owner_vault: 'system', copy_count: copies, approval_id: null }] : [],
})
const proposal = { approval_id: 'ap-1', reason: 'one_verified', copies: 2, skipped: false }

function mountSection() {
  return mount(DuplicateSecrets, {
    global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('DuplicateSecrets.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue(status(2, 5))
  })

  it('shows group and copy counts and the vault, and nothing that identifies a secret', async () => {
    const wrapper = mountSection()
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith('/api/admin/secret-duplicates')
    expect(wrapper.text()).toContain('Found: 2.')
    expect(wrapper.text()).toContain('5 copies in total.')
    expect(wrapper.text()).toContain('system')
  })

  it('disables Propose when there are no duplicates', async () => {
    mockGet.mockResolvedValue(status(0, 0))
    const wrapper = mountSection()
    await flushPromises()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('proposes through the review queue and says nothing changes until approved', async () => {
    mockPost.mockResolvedValue({ proposals: [proposal], remaining: 0 })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledWith('/api/admin/secret-duplicates/requests')
    expect(wrapper.text()).toContain('Proposal sent to the review queue')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('keeps Propose available while duplicated groups remain after a proposal', async () => {
    mockGet.mockResolvedValue(status(6, 12))
    mockPost.mockResolvedValue({ proposals: [proposal], remaining: 1 })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Proposal sent to the review queue')
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
  })

  it('maps a refused proposal to localised text, never the server wording', async () => {
    mockPost.mockRejectedValue(httpError(409))
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No proposal was created')
  })
})
