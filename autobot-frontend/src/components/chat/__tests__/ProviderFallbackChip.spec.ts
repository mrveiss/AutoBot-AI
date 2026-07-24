// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Component tests for the opt-in provider-fallback chip (#11997 / umbrella
 * #11994).
 *
 * Scenarios:
 *  1. The `showFallbackChip` display setting defaults to OFF.
 *  2. Setting OFF (default) → chip hidden even when a fallback matched.
 *  3. Setting ON + a matching fallback → chip renders with primary/fallback
 *     tooltip context.
 *  4. Setting ON + no fallback → chip hidden.
 *
 * useDisplaySettings is mocked so the test drives the opt-in gate directly.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── Module-level mocks (hoisted) ─────────────────────────────────────────────

vi.mock('@/composables/useDisplaySettings', () => ({
  useDisplaySettings: vi.fn(),
}))

vi.mock('@/components/ui/Icon.vue', () => ({
  default: { name: 'Icon', template: '<i class="icon-stub" />', props: ['name'] },
}))

vi.mock('@autobot/ui', () => ({
  BaseBadge: {
    name: 'BaseBadge',
    props: ['variant', 'size', 'title'],
    template:
      '<span class="base-badge-stub" :data-variant="variant" :title="title">' +
      '<slot name="icon" /><slot /></span>',
  },
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import { useDisplaySettings } from '@/composables/useDisplaySettings'
import ProviderFallbackChip from '../ProviderFallbackChip.vue'
import type { ProviderFallbackPayload } from '@/constants/providerFallbackEvents'

// ── i18n (real messages so tooltip interpolation is asserted) ────────────────

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      common: { unknown: 'Unknown' },
      chat: {
        message: {
          fallback: {
            badge: 'Via fallback',
            tooltip:
              'Primary provider unavailable — answered via a fallback provider ({primary} → {fallback}).',
          },
        },
      },
    },
  },
})

const FALLBACK: ProviderFallbackPayload = {
  conversation_id: 'conv-1',
  request_id: null,
  primary_model: 'gpt-4o',
  primary_provider: 'openai',
  fallback_model: 'claude-3-5-sonnet',
  fallback_provider: 'anthropic',
  reason: 'rate_limit',
  chain_tried: ['gpt-4o', 'claude-3-5-sonnet'],
  degraded_skipped: [],
  exhausted: false,
  timestamp: 1_700_000_000,
}

let settingEnabled = false

function mountChip(fallbackInfo: ProviderFallbackPayload | null): VueWrapper {
  return mount(ProviderFallbackChip, {
    props: { fallbackInfo },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  settingEnabled = false
  vi.mocked(useDisplaySettings).mockReturnValue({
    getSetting: (key: string) => (key === 'showFallbackChip' ? settingEnabled : false),
  } as unknown as ReturnType<typeof useDisplaySettings>)
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('ProviderFallbackChip (opt-in, default OFF)', () => {
  it('defaults the showFallbackChip setting to OFF', async () => {
    // Assert against the real defaults, not the mock, to prove default-OFF.
    const actual = await vi.importActual<typeof import('@/composables/useDisplaySettings')>(
      '@/composables/useDisplaySettings',
    )
    const { getSetting } = actual.useDisplaySettings()
    expect(getSetting('showFallbackChip')).toBe(false)
  })

  it('hides the chip when the setting is OFF (default) even with a fallback', () => {
    settingEnabled = false
    const wrapper = mountChip(FALLBACK)
    expect(wrapper.find('.base-badge-stub').exists()).toBe(false)
  })

  it('renders the chip when the setting is ON and a fallback matched the message', () => {
    settingEnabled = true
    const wrapper = mountChip(FALLBACK)
    const badge = wrapper.find('.base-badge-stub')
    expect(badge.exists()).toBe(true)
    expect(badge.attributes('data-variant')).toBe('warning')
    expect(badge.text()).toContain('Via fallback')
    expect(badge.attributes('title')).toBe(
      'Primary provider unavailable — answered via a fallback provider (openai → anthropic).',
    )
  })

  it('hides the chip when the setting is ON but no fallback matched', () => {
    settingEnabled = true
    const wrapper = mountChip(null)
    expect(wrapper.find('.base-badge-stub').exists()).toBe(false)
  })
})
