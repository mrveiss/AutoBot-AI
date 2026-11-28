// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ChromaDBExplorer's subtitle is a translated string with no port number (#19321).
 *
 * It read "... at port 8100": a hardcoded UI string and a second copy of
 * PortConfig.chromadb, which the UI does not dial (it goes through the backend).
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: vi.fn().mockResolvedValue({ collections: [] }), post: vi.fn() }),
}))

import ChromaDBExplorer from '../ChromaDBExplorer.vue'

describe('ChromaDBExplorer subtitle (#19321)', () => {
  it('renders the en.json subtitle and no port number', async () => {
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
    const wrapper = mount(ChromaDBExplorer, { global: { plugins: [i18n] } })
    await flushPromises()
    const subtitle = wrapper.get('.header-subtitle').text()
    expect(subtitle).toBe(en.knowledge.chromaExplorer.subtitle)
    expect(subtitle).not.toMatch(/\d{4}/)
  })
})
