// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SystemUpdatesTab runs ONE job poller while jobs are running (#19482). Before the
 * move to usePollingJob, onMounted could start a second interval after the watch
 * had already started one, orphaning it, so jobs were fetched twice per tick.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import en from '@/locales/en.json'

const JOB_POLL_MS = 10_000
const running = ref(false)
const fetchJobs = vi.fn()

vi.mock('@/composables/useSystemUpdates', () => ({
  useSystemUpdates: () => ({
    isDiscovering: ref(false),
    discoverStatus: ref(null),
    packages: ref([]),
    loading: ref(false),
    jobs: ref([]),
    error: ref(null),
    updateCount: computed(() => 0),
    securityCount: computed(() => 0),
    nodesWithUpdates: computed(() => 0),
    lastChecked: ref(null),
    hasRunningJobs: computed(() => running.value),
    fetchJobs: (...a: unknown[]) => fetchJobs(...a),
    fetchPackages: vi.fn().mockResolvedValue([]),
    fetchSummary: vi.fn().mockResolvedValue(null),
    pollDiscoverStatus: vi.fn().mockResolvedValue(null),
    discoverUpdates: vi.fn(),
    upgradeAll: vi.fn(),
    applyUpdates: vi.fn(),
    cancelJob: vi.fn(),
    clearError: vi.fn(),
  }),
}))
vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({ fetchNodes: vi.fn().mockResolvedValue([]), nodeList: [] }),
}))

import SystemUpdatesTab from './SystemUpdatesTab.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

describe('SystemUpdatesTab job polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    running.value = false
    fetchJobs.mockReset()
    // The mount's own fetchJobs reports running jobs, as a real one would.
    fetchJobs.mockImplementation(async () => {
      running.value = true
      return []
    })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('fetches jobs once per tick when both the watch and onMounted see running jobs', async () => {
    const wrapper = mount(SystemUpdatesTab, { global: { plugins: [i18n] } })
    await flushPromises()
    const afterMount = fetchJobs.mock.calls.length

    await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3)
    await flushPromises()
    expect(fetchJobs.mock.calls.length - afterMount).toBe(3)
    wrapper.unmount()
  })

  it('stops the job poller when jobs finish and when unmounted', async () => {
    const wrapper = mount(SystemUpdatesTab, { global: { plugins: [i18n] } })
    await flushPromises()
    running.value = false
    await flushPromises()
    const stoppedAt = fetchJobs.mock.calls.length
    await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3)
    expect(fetchJobs.mock.calls.length).toBe(stoppedAt)

    running.value = true
    await flushPromises()
    wrapper.unmount()
    const unmountedAt = fetchJobs.mock.calls.length
    await vi.advanceTimersByTimeAsync(JOB_POLL_MS * 3)
    expect(fetchJobs.mock.calls.length).toBe(unmountedAt)
  })
})
