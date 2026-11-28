// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #10200: a failed push to the SLM copy is shown to admins by name. */
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import PersonPushFailuresAlert from '../PersonPushFailuresAlert.vue'

const get = vi.fn()
vi.mock('@/composables/useAutobotApi', () => ({ createAutobotBackendClient: () => ({ get }) }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

async function text(): Promise<string> {
  const wrapper = mount(PersonPushFailuresAlert, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper.text()
}

describe('PersonPushFailuresAlert', () => {
  it('names each person', async () => {
    get.mockResolvedValueOnce({ failures: [{ username: 'alice' }, { username: 'bob' }] })
    expect(await text()).toContain('alice, bob')
  })

  it('shows nothing when there are no failures', async () => {
    get.mockResolvedValueOnce({ failures: [] })
    expect(await text()).toBe('')
  })

  it('shows nothing when the main app cannot be read', async () => {
    get.mockRejectedValueOnce(new Error('down'))
    expect(await text()).toBe('')
  })
})
