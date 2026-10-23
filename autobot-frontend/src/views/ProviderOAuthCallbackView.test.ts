// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** ProviderOAuthCallbackView (#19241): exchanges ?code/&state then returns to Settings. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

// mockReset: true (vitest.config.ts, #3070) wipes implementations before every test,
// so the resolved value is applied in beforeEach, never at module scope.
const post = vi.fn()
const replace = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { post: (...a: unknown[]) => post(...a) } }))
vi.mock('@/config/ssot-config', () => ({
  getConfig: () => ({ frontendUrl: 'https://app.example.test' }),
}))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ showToast: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { code: 'abc', state: 'st' } }),
  useRouter: () => ({ replace }),
}))

import ProviderOAuthCallbackView from './ProviderOAuthCallbackView.vue'
import { PROVIDER_OAUTH_CALLBACK_PATH } from '@/utils/providerOAuth'

beforeEach(() => {
  post.mockResolvedValue({ provider_name: 'openai', stored: true, scope: 'user' })
})

describe('ProviderOAuthCallbackView', () => {
  it('posts state/code/redirect_uri and navigates to Settings API keys', async () => {
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
    mount(ProviderOAuthCallbackView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/api/llm-auth/oauth/callback', {
      state: 'st',
      code: 'abc',
      redirect_uri: `https://app.example.test${PROVIDER_OAUTH_CALLBACK_PATH}`,
    })
    expect(replace).toHaveBeenCalledWith({
      path: '/preferences',
      query: { tab: 'apikeys', oauth: 'connected' },
    })
  })
})
