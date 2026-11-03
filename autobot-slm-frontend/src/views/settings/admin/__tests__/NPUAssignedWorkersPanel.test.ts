// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #19706: an assigned node is offered for pairing, and only pressing Pair pairs it. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import NPUAssignedWorkersPanel from '../NPUAssignedWorkersPanel.vue'

const get = vi.fn()
const pairNPUWorker = vi.fn()

vi.mock('@/composables/useAutobotApi', () => ({
  useAutobotApi: () => ({ pairNPUWorker }),
  createAutobotBackendClient: () => ({ get }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const WORKER = { url: 'http://node:8081', hostname: 'npu-a' }

async function mounted() {
  const wrapper = mount(NPUAssignedWorkersPanel, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('NPUAssignedWorkersPanel', () => {
  beforeEach(() => {
    get.mockReset()
    pairNPUWorker.mockReset()
  })

  it('names the node and pairs nothing until asked', async () => {
    get.mockResolvedValue({ workers: [WORKER] })
    const wrapper = await mounted()
    expect(wrapper.text()).toContain('npu-a')
    expect(pairNPUWorker).not.toHaveBeenCalled()
  })

  it('pairs the node when Pair is pressed and tells the page', async () => {
    get.mockResolvedValueOnce({ workers: [WORKER] }).mockResolvedValueOnce({ workers: [] })
    pairNPUWorker.mockResolvedValue(undefined)
    const wrapper = await mounted()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(pairNPUWorker).toHaveBeenCalledWith({ url: WORKER.url, name: 'npu-a', enabled: true })
    expect(wrapper.emitted('paired')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('npu-a')
  })

  it('says so when the assignments cannot be read', async () => {
    get.mockRejectedValue(new Error('down'))
    const wrapper = await mounted()
    expect(wrapper.text()).toContain('Could not read which nodes')
  })

  it('names the node when pairing fails and keeps it listed', async () => {
    get.mockResolvedValue({ workers: [WORKER] })
    pairNPUWorker.mockRejectedValue(new Error('unreachable'))
    const wrapper = await mounted()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Could not pair the NPU worker on npu-a')
    expect(wrapper.emitted('paired')).toBeUndefined()
  })
})
