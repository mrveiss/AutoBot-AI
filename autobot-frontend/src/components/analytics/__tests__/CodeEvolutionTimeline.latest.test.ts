// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * CodeEvolutionTimeline: only the newest fetch may write data or clear `loading` (#20513).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

type Timeline = { timeline: { timestamp: string }[] }
let pending: Array<(value: Timeline | null) => void> = []

vi.mock('@/composables/analytics/useCodeEvolutionData', () => ({
  useCodeEvolutionData: () => ({
    fetchTimeline: () => new Promise<Timeline | null>(resolve => pending.push(resolve)),
    fetchTrends: async () => ({ trends: {} }),
    fetchPatterns: async () => ({ patterns: {} }),
    fetchExport: async () => null,
  }),
}))
vi.mock('@autobot/ui', () => ({
  BaseButton: { template: '<button><slot /></button>' },
  saveBlob: vi.fn(),
}))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))

import CodeEvolutionTimeline from '../CodeEvolutionTimeline.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const point = (timestamp: string): Timeline => ({ timeline: [{ timestamp }] })

async function twoOverlappingFetches() {
  const wrapper = mount(CodeEvolutionTimeline, { global: { plugins: [i18n] } })
  await flushPromises() // fetch #1 (mount) is in flight
  await wrapper.findAll('select')[1].setValue('90') // fetch #2 supersedes it
  await flushPromises()
  expect(pending).toHaveLength(2)
  return wrapper
}
const shown = (wrapper: ReturnType<typeof mount>) => (wrapper.vm as unknown as { timelineData: { timestamp: string }[] }).timelineData

describe('CodeEvolutionTimeline fetchTimeline races (#20513)', () => {
  beforeEach(() => {
    pending = []
  })

  it('an older reply that lands first neither writes data nor clears loading while the newer request is pending', async () => {
    const wrapper = await twoOverlappingFetches()
    pending[0](point('old'))
    await flushPromises()
    expect(wrapper.find('.loading-state').exists()).toBe(true)
    expect(shown(wrapper)).toEqual([])
    pending[1](point('new'))
    await flushPromises()
    expect(wrapper.find('.loading-state').exists()).toBe(false)
    expect(shown(wrapper).map(p => p.timestamp)).toEqual(['new'])
  })

  it('a slower superseded reply landing after the newer one does not overwrite it', async () => {
    const wrapper = await twoOverlappingFetches()
    pending[1](point('new'))
    await flushPromises()
    pending[0](point('old'))
    await flushPromises()
    expect(wrapper.find('.loading-state').exists()).toBe(false)
    expect(shown(wrapper).map(p => p.timestamp)).toEqual(['new'])
  })
})
