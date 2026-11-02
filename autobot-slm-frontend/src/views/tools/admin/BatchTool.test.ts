// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * BatchTool polls through the shared dashboard policy (#19482): it stops after
 * POLL_CONSECUTIVE_ERROR_LIMIT
 * consecutive failures and shows the paused banner (#1092), Retry restarts it, and
 * unmounting stops it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'

const listBatchJobs = vi.fn()
const getBatchJobHealth = vi.fn()

vi.mock('@/composables/useAutobotApi', () => ({
  useAutobotApi: () => ({
    listBatchJobs: (...a: unknown[]) => listBatchJobs(...a),
    getBatchJobHealth: (...a: unknown[]) => getBatchJobHealth(...a),
    createBatchJob: vi.fn(),
    cancelBatchJob: vi.fn(),
  }),
}))

import BatchTool from './BatchTool.vue'
import { POLL_CONSECUTIVE_ERROR_LIMIT as LIMIT } from '@/constants/api-timeouts'

const POLL_MS = 10_000
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const paused = en.tools.admin.batchTool.autoBotBackendUnreachablePolling

function mountTool() {
  return mount(BatchTool, { global: { plugins: [i18n] } })
}

async function tick(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

describe('BatchTool polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    listBatchJobs.mockReset()
    getBatchJobHealth.mockReset()
    getBatchJobHealth.mockResolvedValue({ total_jobs: 0, running_jobs: 0, completed_jobs: 0, failed_jobs: 0 })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('pauses after the shared limit of consecutive failures and shows the banner', async () => {
    listBatchJobs.mockRejectedValue(new Error('down'))
    const wrapper = mountTool()
    await flushPromises()
    expect(listBatchJobs).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain(paused)

    for (let i = 1; i < LIMIT; i++) await tick(POLL_MS)
    expect(listBatchJobs).toHaveBeenCalledTimes(LIMIT)
    expect(wrapper.text()).toContain(paused)

    await tick(POLL_MS * 3)
    expect(listBatchJobs).toHaveBeenCalledTimes(LIMIT)
    wrapper.unmount()
  })

  it('Retry restarts polling and clears the banner once the backend answers', async () => {
    listBatchJobs.mockRejectedValue(new Error('down'))
    const wrapper = mountTool()
    await flushPromises()
    for (let i = 1; i < LIMIT; i++) await tick(POLL_MS)
    expect(wrapper.text()).toContain(paused)

    listBatchJobs.mockResolvedValue({ jobs: [] })
    const retry = wrapper.findAll('button').find((b) => b.text() === en.tools.admin.batchTool.retry)
    await retry!.trigger('click')
    await flushPromises()
    expect(listBatchJobs).toHaveBeenCalledTimes(LIMIT + 1)
    expect(wrapper.text()).not.toContain(paused)

    await tick(POLL_MS)
    expect(listBatchJobs).toHaveBeenCalledTimes(LIMIT + 2)
    wrapper.unmount()
  })

  it('stops polling when unmounted', async () => {
    listBatchJobs.mockResolvedValue({ jobs: [] })
    const wrapper = mountTool()
    await flushPromises()
    wrapper.unmount()
    await tick(POLL_MS * 3)
    expect(listBatchJobs).toHaveBeenCalledTimes(1)
  })
})
