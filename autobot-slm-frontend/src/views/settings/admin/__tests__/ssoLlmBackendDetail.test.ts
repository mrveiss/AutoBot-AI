// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SSO and LLM settings show the backend `detail` carried by the kit HttpError
 * (#19816): they read `err.response?.data?.detail`, which never exists on it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/locales/en.json'
import SSOSettings from '../SSOSettings.vue'
import LLMSettings from '../LLMSettings.vue'

const sso = { listProviders: vi.fn(), getProvidersHealth: vi.fn() }
const llm = { getConfig: vi.fn() }
vi.mock('@/composables/useSsoApi', () => ({ useSsoApi: () => sso }))
vi.mock('@/composables/useLlmConfigApi', () => ({ useLlmConfigApi: () => llm }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const detail = 'backend says no'

describe('backend detail on an HttpError', () => {
  beforeEach(() => {
    sso.listProviders.mockReset()
    sso.getProvidersHealth.mockReset().mockResolvedValue([])
    llm.getConfig.mockReset()
  })

  it('SSOSettings shows it when loading providers fails', async () => {
    sso.listProviders.mockRejectedValue(new HttpError(400, 'Bad Request', { detail }))
    const wrapper = mount(SSOSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain(detail)
  })

  it('LLMSettings shows it when loading the config fails', async () => {
    llm.getConfig.mockRejectedValue(new HttpError(400, 'Bad Request', { detail }))
    const wrapper = mount(LLMSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain(detail)
  })
})
