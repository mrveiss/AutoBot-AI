// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for ProviderFallbackView.vue (#11996 / umbrella #11994).
// Mocks useProviderFallbackApi so no real HTTP / WebSocket calls are made.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const mockFetch = vi.fn()
const mockSubscribe = vi.fn(() => () => {})

vi.mock('@/composables/useProviderFallbackApi', () => ({
  useProviderFallbackApi: () => ({
    fetchFallbackStatus: mockFetch,
    subscribeToFallbackEvents: mockSubscribe,
  }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import ProviderFallbackView from '../ProviderFallbackView.vue'

function mountView() {
  return mount(ProviderFallbackView, { global: { plugins: [i18n] } })
}

describe('ProviderFallbackView.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSubscribe.mockReturnValue(() => {})
  })

  it('renders the active fallback state from the read API', async () => {
    mockFetch.mockResolvedValue({
      configured_chains: [
        { primary_model: 'gpt-4o', fallback_chain: 'gpt-4o → claude-3-5-sonnet', provider: 'multi' },
      ],
      active_fallbacks: [
        {
          conversation_id: 'conv-42',
          primary_model: 'gpt-4o',
          fallback_model: 'claude-3-5-sonnet',
          primary_provider: 'openai',
          fallback_provider: 'anthropic',
          timestamp: 1700000000,
        },
      ],
    })

    const wrapper = mountView()
    await flushPromises()

    // Degraded state badge shown because an active fallback exists
    expect(wrapper.text()).toContain('Fallback active')
    // Active fallback card surfaces the conversation + hop models
    expect(wrapper.text()).toContain('conv-42')
    expect(wrapper.text()).toContain('anthropic/claude-3-5-sonnet')
    // Configured chain surfaced
    expect(wrapper.text()).toContain('gpt-4o → claude-3-5-sonnet')
  })

  it('renders the healthy state and empty message when there is no activity', async () => {
    mockFetch.mockResolvedValue({ configured_chains: [], active_fallbacks: [] })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('No active fallbacks')
    expect(wrapper.text()).toContain('No provider fallback activity')
  })

  it('subscribes to live PROVIDER_FALLBACK events on mount', async () => {
    mockFetch.mockResolvedValue({ configured_chains: [], active_fallbacks: [] })

    mountView()
    await flushPromises()

    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    expect(mockSubscribe).toHaveBeenCalledWith(expect.any(Function))
  })

  it('appends a live event to the timeline', async () => {
    mockFetch.mockResolvedValue({ configured_chains: [], active_fallbacks: [] })
    let liveCb: ((p: Record<string, unknown>) => void) | null = null
    mockSubscribe.mockImplementation((cb: (p: Record<string, unknown>) => void) => {
      liveCb = cb
      return () => {}
    })

    const wrapper = mountView()
    await flushPromises()

    liveCb!({
      conversation_id: 'conv-live',
      primary_model: 'gpt-4o',
      fallback_model: 'claude-3-5-sonnet',
      reason: 'rate_limit_429',
      exhausted: true,
      timestamp: 1700000001,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('conv-live')
    expect(wrapper.text()).toContain('Exhausted')
  })
})
