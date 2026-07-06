// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for SystemHealthView.vue (#10932).
// Mocks useProbeBackedHealth so no real HTTP calls are made.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

// getHealth mock function — replaced per test in beforeEach
const mockGetHealth = vi.fn()

vi.mock('@/composables/useProbeBackedHealth', () => ({
  useProbeBackedHealth: () => mockGetHealth,
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// vue-i18n installed as a real plugin so $t() resolves in templates.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

import SystemHealthView from '../SystemHealthView.vue'

function mountView() {
  return mount(SystemHealthView, {
    global: { plugins: [i18n] },
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SystemHealthView.vue', () => {
  beforeEach(() => {
    mockGetHealth.mockReset()
  })

  it('renders source names and marks live vs dead backends', async () => {
    mockGetHealth.mockResolvedValue({
      status: 'degraded',
      detail: 'one backend down',
      sources: { web: ['ddgs', 'jina'], youtube: ['ytdlp'] },
      live: { web: ['ddgs'], youtube: ['ytdlp'] },
    })

    const wrapper = mountView()
    await flushPromises()

    // Status badge is present
    expect(wrapper.text()).toContain('Degraded')

    // Source names appear
    expect(wrapper.text()).toContain('web')
    expect(wrapper.text()).toContain('youtube')

    // 'ddgs' is live — find its span and check for live class
    const backendSpans = wrapper.findAll('span.inline-flex.items-center')
    const ddgsSpan = backendSpans.find((s) => s.text().includes('ddgs'))
    expect(ddgsSpan).toBeTruthy()
    expect(ddgsSpan?.classes()).toContain('bg-green-100')

    // 'jina' is dead — present in sources but not in live
    const jinaSpan = backendSpans.find((s) => s.text().includes('jina'))
    expect(jinaSpan).toBeTruthy()
    expect(jinaSpan?.classes()).toContain('bg-red-100')
  })

  it('renders unavailable / empty state when no sources are returned', async () => {
    mockGetHealth.mockResolvedValue({
      status: 'unavailable',
      detail: 'probe unavailable',
      sources: {},
      live: {},
    })

    const wrapper = mountView()
    await flushPromises()

    // Status badge shows 'Unavailable'
    expect(wrapper.text()).toContain('Unavailable')

    // No source rows are rendered
    const backendSpans = wrapper.findAll('span.inline-flex.items-center')
    expect(backendSpans).toHaveLength(0)

    // noSources message is visible
    expect(wrapper.text()).toContain('No content sources configured')
  })
})
