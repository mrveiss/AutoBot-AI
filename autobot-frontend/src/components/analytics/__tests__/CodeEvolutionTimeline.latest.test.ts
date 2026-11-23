// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * CodeEvolutionTimeline: only the newest fetch may write data or clear `loading` (#20513).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

type Timeline = { timeline: { timestamp: string }[] }
let pending: Array<(value: Timeline | null) => void> = []
let rejectors: Array<(reason: Error) => void> = []
const sourceId = ref<string | undefined>('src-a')

vi.mock('@/composables/analytics/useCodeEvolutionData', () => ({
  useCodeEvolutionData: () => ({
    sourceId,
    fetchTimeline: () =>
      new Promise<Timeline | null>((resolve, reject) => {
        pending.push(resolve)
        rejectors.push(reject)
      }),
    fetchTrends: async () => ({ trends: {} }),
    fetchPatterns: async () => ({ patterns: {} }),
    fetchExport: async () => null,
  }),
}))
vi.mock('@autobot/ui', async importOriginal => ({
  ...(await importOriginal<typeof import('@autobot/ui')>()),
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
    rejectors = []
    sourceId.value = 'src-a'
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

  it('a superseded call that rejects does not show its error and the newer data stands', async () => {
    const wrapper = await twoOverlappingFetches()
    rejectors[0](new Error('old failed'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('old failed')
    pending[1](point('new'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('old failed')
    expect(shown(wrapper).map(p => p.timestamp)).toEqual(['new'])
  })

  it('switching the route source refetches and drops the previous source\'s late reply', async () => {
    const wrapper = mount(CodeEvolutionTimeline, { global: { plugins: [i18n] } })
    await flushPromises()
    sourceId.value = 'src-b'
    await flushPromises()
    expect(pending).toHaveLength(2)
    pending[1](point('b'))
    await flushPromises()
    pending[0](point('a'))
    await flushPromises()
    expect(shown(wrapper).map(p => p.timestamp)).toEqual(['b'])
  })

  it('the latest call failing shows the translated load-failed message, not English literals', async () => {
    const wrapper = mount(CodeEvolutionTimeline, { global: { plugins: [i18n] } })
    await flushPromises()
    pending[0](null)
    await flushPromises()
    expect(wrapper.find('.error-state').text()).toContain(en.analytics.codeEvolution.loadFailed)
  })
})
