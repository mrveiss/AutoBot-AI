// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #20904: the panel lists ownerless sessions and a proposal reaches POST /api/admin/ownerless-chat-sessions/requests.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }))
const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { status, isHttpError: true })

vi.mock('@/utils/ApiClient', () => ({ default: { get: mockGet, post: mockPost } }))
vi.mock('@autobot/ui', () => ({
  BaseButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  BaseCard: { template: '<section><slot /></section>' },
  BaseAlert: { props: ['message'], template: '<p class="alert">{{ message }}</p>' },
  BaseInput: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  isHttpError: (e: unknown) => !!(e as { isHttpError?: boolean })?.isHttpError,
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => ({ selectedCompanyId: '' }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import OwnerlessSessionsPanel from '../OwnerlessSessionsPanel.vue'

async function mountPanel() {
  const wrapper = mount(OwnerlessSessionsPanel, {
    global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  return wrapper
}

describe('OwnerlessSessionsPanel.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ count: 1, session_ids: ['s1'], unreadable: [] })
  })

  it('lists the ownerless sessions from the report route', async () => {
    const wrapper = await mountPanel()
    expect(mockGet).toHaveBeenCalledWith('/api/admin/ownerless-chat-sessions')
    expect(wrapper.find('[data-testid="ownerless-s1"]').exists()).toBe(true)
  })

  it('cannot propose until an owner is named', async () => {
    const wrapper = await mountPanel()
    expect(wrapper.find('[data-testid="ownerless-s1"] button').attributes('disabled')).toBeDefined()
  })

  it('posts the proposal to the requests route and shows it as pending', async () => {
    mockPost.mockResolvedValue({ approval_id: 'a1', status: 'pending', action: 'x' })
    const wrapper = await mountPanel()
    await wrapper.find('input').setValue(' alice ')
    await wrapper.find('[data-testid="ownerless-s1"] button').trigger('click')
    await flushPromises()
    expect(mockPost).toHaveBeenCalledWith('/api/admin/ownerless-chat-sessions/requests', {
      session_id: 's1',
      owner: 'alice',
    })
    expect(wrapper.text()).toContain(en.admin.ownerless.proposed)
  })

  it('shows a localised refusal, never the server wording', async () => {
    mockPost.mockRejectedValue(httpError(422))
    const wrapper = await mountPanel()
    await wrapper.find('input').setValue('ghost')
    await wrapper.find('[data-testid="ownerless-s1"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.alert').text()).toBe(en.admin.ownerless.refusedOwner)
  })
})
