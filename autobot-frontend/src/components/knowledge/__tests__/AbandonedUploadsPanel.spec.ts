// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #20905: the panel lists abandoned uploads and freeing one reaches DELETE /api/knowledge_base/uploads/expired/{id}.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { mockGet, mockDelete } = vi.hoisted(() => ({ mockGet: vi.fn(), mockDelete: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: { get: mockGet, delete: mockDelete } }))
vi.mock('@autobot/ui', () => ({
  BaseButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  BaseCard: { template: '<section><slot /></section>' },
  BaseAlert: { props: ['message'], template: '<p class="alert">{{ message }}</p>' },
  formatFileSize: (n: number) => `${n}B`,
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import AbandonedUploadsPanel from '../AbandonedUploadsPanel.vue'

const upload = { upload_id: 'u1', filename: 'big.pdf', total_size: 100, received: 40, state: 'open' }

async function mountPanel() {
  const wrapper = mount(AbandonedUploadsPanel, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('AbandonedUploadsPanel.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ expired: [upload] })
  })

  it('lists abandoned uploads from the expired route', async () => {
    const wrapper = await mountPanel()
    expect(mockGet).toHaveBeenCalledWith('/api/knowledge_base/uploads/expired')
    expect(wrapper.find('[data-testid="abandoned-u1"]').text()).toContain('big.pdf')
  })

  it('frees one upload through the DELETE route and drops it from the list', async () => {
    mockDelete.mockResolvedValue({ upload_id: 'u1', removed: true })
    const wrapper = await mountPanel()
    await wrapper.find('[data-testid="abandoned-u1"] button').trigger('click')
    await flushPromises()
    expect(mockDelete).toHaveBeenCalledWith('/api/knowledge_base/uploads/expired/u1')
    expect(wrapper.find('[data-testid="abandoned-u1"]').exists()).toBe(false)
  })

  it('keeps the row and says so when the server refuses', async () => {
    mockDelete.mockRejectedValue(new Error('HTTP 503'))
    const wrapper = await mountPanel()
    await wrapper.find('[data-testid="abandoned-u1"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="abandoned-u1"]').exists()).toBe(true)
    expect(wrapper.find('.alert').text()).toBe(en.knowledge.abandonedUploads.freeFailed)
  })
})
