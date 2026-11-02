// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #20250: nodes left offline by an update are shown on the update page. */
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import UpdateNodesOfflineAlert from './UpdateNodesOfflineAlert.vue'

const get = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ slmApiClient: { get: (...args: unknown[]) => get(...args) } }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

async function text(): Promise<string> {
  const wrapper = mount(UpdateNodesOfflineAlert, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper.text()
}

describe('UpdateNodesOfflineAlert', () => {
  it('says how many nodes stayed offline', async () => {
    get.mockResolvedValueOnce({ nodes_offline: 1, nodes_total: 2 })
    expect(await text()).toContain('1 of 2 nodes')
  })

  it('shows nothing when all came back', async () => {
    get.mockResolvedValueOnce({ nodes_offline: 0, nodes_total: 2 })
    expect(await text()).toBe('')
  })

  it('shows nothing when it cannot read the answer', async () => {
    get.mockRejectedValueOnce(new Error('down'))
    expect(await text()).toBe('')
  })
})
