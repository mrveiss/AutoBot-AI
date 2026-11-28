// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * CodeQualityDashboard shows "live" only for its current socket (#21548).
 *
 * useWebSocket is replaced by a double that keeps the options the dashboard passed. The spec calls
 * `onOpen` (which sets wsConnected) and then `onClose` with `{ current: false }` / `{ current: true }`,
 * and reads the `.realtime-status` element that `wsConnected` drives. Every data composable resolves
 * to nothing and noDataState reports no data, so only the header and the empty-state are rendered;
 * child components are stubbed by shallowMount.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, type VueWrapper } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

const stubT = (key: string, _params?: object) => key

vi.mock('vue-i18n', () => ({
  useI18n: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/composables/analytics/useCodeQualityData', () => ({
  useCodeQualityData: vi.fn(),
}))

vi.mock('@/composables/analytics/useUnwiredTrackers', () => ({
  useUnwiredTrackers: vi.fn(),
}))

import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useWebSocket, type UseWebSocketOptions } from '@/composables/useWebSocket'
import { useCodeQualityData } from '@/composables/analytics/useCodeQualityData'
import { useUnwiredTrackers } from '@/composables/analytics/useUnwiredTrackers'
import CodeQualityDashboard from '../CodeQualityDashboard.vue'

let socketOptions: UseWebSocketOptions
let wrapper: VueWrapper | null

const flushAsync = () => new Promise((resolve) => setTimeout(resolve, 0))
const closeEvent = () => new CloseEvent('close', { code: 1006 })
const status = () => wrapper!.find('.realtime-status')

async function mountDashboard(): Promise<VueWrapper> {
  const view = shallowMount(CodeQualityDashboard, { global: { mocks: { $t: stubT } } })
  await flushAsync()
  await nextTick()
  return view
}

describe('CodeQualityDashboard when its socket closes (#21548)', () => {
  beforeEach(() => {
    wrapper = null
    vi.mocked(useI18n).mockReturnValue({ t: stubT, te: () => false } as unknown as ReturnType<typeof useI18n>)
    vi.mocked(useRoute).mockReturnValue({ params: {} } as unknown as ReturnType<typeof useRoute>)
    vi.mocked(useCodeQualityData).mockReturnValue({
      fetchHealthScore: vi.fn().mockResolvedValue(null),
      fetchMetrics: vi.fn().mockResolvedValue([]),
      fetchPatterns: vi.fn().mockResolvedValue([]),
      fetchComplexity: vi.fn().mockResolvedValue(null),
      fetchTrends: vi.fn().mockResolvedValue([]),
      fetchSnapshot: vi.fn().mockResolvedValue(null),
      fetchDrillDown: vi.fn().mockResolvedValue(null),
      fetchExport: vi.fn().mockResolvedValue(null),
      noDataState: ref({ noData: true, message: 'no scan data' }),
    } as unknown as ReturnType<typeof useCodeQualityData>)
    vi.mocked(useUnwiredTrackers).mockReturnValue({
      count: ref(0),
      sparkline: ref([]),
      loading: ref(false),
      fetchUnwiredTrackers: vi.fn().mockResolvedValue(undefined),
    } as unknown as ReturnType<typeof useUnwiredTrackers>)
    vi.mocked(useWebSocket).mockImplementation(((_url: unknown, options: UseWebSocketOptions) => {
      socketOptions = options
      return { connect: vi.fn() }
    }) as unknown as typeof useWebSocket)
  })

  it('stays live when a replaced socket closes', async () => {
    wrapper = await mountDashboard()
    expect(status().classes()).not.toContain('connected')
    socketOptions.onOpen!(new Event('open'))
    await nextTick()
    expect(status().classes()).toContain('connected')
    expect(status().text()).toBe('analytics.codeQuality.live')

    socketOptions.onClose!(closeEvent(), { current: false })
    await nextTick()

    expect(status().classes()).toContain('connected')
    expect(status().text()).toBe('analytics.codeQuality.live')
  })

  it('goes offline when the current socket closes', async () => {
    wrapper = await mountDashboard()
    socketOptions.onOpen!(new Event('open'))
    await nextTick()
    expect(status().classes()).toContain('connected')

    socketOptions.onClose!(closeEvent(), { current: true })
    await nextTick()

    expect(status().classes()).not.toContain('connected')
    expect(status().text()).toBe('analytics.codeQuality.offline')
  })
})
