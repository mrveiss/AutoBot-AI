// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * MemoryPrivacyPanel forget-everywhere outcomes — Issue #13739.
 *
 * A 409 means the id exists in more than one store and the backend refused to
 * guess which one the user meant. That is a different situation from "the
 * delete failed", and the row already offers a per-store delete — so the two
 * must not collapse into the same toast, or the user is left at a dead end.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import MemoryPrivacyPanel from './MemoryPrivacyPanel.vue'
import en from '@/i18n/locales/en.json'

const showToast = vi.fn()
const confirm = vi.fn().mockResolvedValue(true)

vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ showToast }),
}))

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm }),
}))

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), delete: vi.fn(), put: vi.fn(), post: vi.fn() },
}))

import apiClient from '@/utils/ApiClient'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: en as Record<string, unknown> },
})

const ITEM = {
  memory_id: '6',
  store: 'graph',
  content: 'an entity',
  provenance: {},
  timestamp: '2026-08-09T00:00:00Z',
}

function mountPanel() {
  return mount(MemoryPrivacyPanel, {
    global: {
      plugins: [i18n],
      stubs: { Icon: { template: '<i />', props: ['name'] } },
    },
  })
}

/** Load one item into the panel, then invoke forget-everywhere on it. */
async function forgetEverywhere(deleteImpl: () => Promise<unknown>) {
  vi.mocked(apiClient.get).mockResolvedValue({ memories: [ITEM] })
  vi.mocked(apiClient.delete).mockImplementation(deleteImpl as never)
  const wrapper = mountPanel()
  await flushPromises()

  const button = wrapper.findAll('button').find((b) => b.text().includes('Forget everywhere'))
  expect(button, 'the forget-everywhere control must be reachable').toBeTruthy()
  await button!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('MemoryPrivacyPanel forget-everywhere (#13739)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    confirm.mockResolvedValue(true)
  })

  it('tells the user to delete per store when the id is ambiguous', async () => {
    await forgetEverywhere(() => Promise.reject(new Error('HTTP 409: conflict')))

    expect(showToast).toHaveBeenCalledWith(
      en.settings.memoryPrivacy.forgetEverywhereAmbiguous,
      'error',
    )
  })

  it('still reports an ordinary failure as a failure', async () => {
    await forgetEverywhere(() => Promise.reject(new Error('HTTP 500: boom')))

    expect(showToast).toHaveBeenCalledWith(en.settings.memoryPrivacy.forgetEverywhereFailed, 'error')
  })

  it('reports which stores it was deleted from on success', async () => {
    await forgetEverywhere(() => Promise.resolve({ deleted_from: ['graph'] }))

    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('graph'), 'success')
  })
})
