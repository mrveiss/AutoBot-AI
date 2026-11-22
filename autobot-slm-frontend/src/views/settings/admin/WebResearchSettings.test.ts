// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19217 — the SLM web research editor: loads every setting, saves only what changed,
 * switches through enable/disable, says "saved, takes effect after a restart" for a
 * saved_not_applied answer, treats a 503 status as an unavailable researcher (not a
 * broken page), and marks exactly the settings the backend does not enforce yet.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { HttpError } from '@autobot/ui'
import { createI18n } from 'vue-i18n'
import WebResearchSettings from './WebResearchSettings.vue'
import en from '@/locales/en.json'

const api = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  enable: vi.fn(),
  disable: vi.fn(),
  getStatus: vi.fn(),
  clearCache: vi.fn(),
  resetCircuitBreakers: vi.fn(),
}))

vi.mock('@/composables/useWebResearchAdminApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useWebResearchAdminApi')>()),
  useWebResearchAdminApi: () => api,
}))
vi.mock('@/composables/useAutobotApi', () => ({
  autobotApiErrorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}))

const copy = en.settings.admin.webResearchSettings
const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const SETTINGS = {
  enabled: false,
  require_user_confirmation: true,
  preferred_method: 'basic',
  max_results: 5,
  timeout_seconds: 30,
  auto_research_threshold: 0.3,
  rate_limit_requests: 5,
  rate_limit_window: 60,
  daily_limit: 100,
  quality_threshold: 0.5,
  store_results_in_kb: true,
  filter_adult_content: true,
  anonymize_requests: true,
}
const STATUS = {
  status: 'success',
  enabled: false,
  preferred_method: 'basic',
  cache_stats: { cache_size: 7, rate_limiter: { current_requests: 1, max_requests: 5 } },
  circuit_breakers: {},
  timestamp: 't',
}
const NOT_ENFORCED = [
  'anonymize_requests', 'filter_adult_content', 'store_results_in_kb', 'auto_research_threshold',
  'daily_limit', 'quality_threshold', 'require_user_confirmation',
]

async function mountView() {
  const wrapper = mount(WebResearchSettings, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('WebResearchSettings (SLM, #19217)', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getStatus.mockResolvedValue({ ...STATUS })
    api.updateSettings.mockResolvedValue({ status: 'success', message: 'ok', settings: { ...SETTINGS, max_results: 9 }, timestamp: 't' })
    api.enable.mockResolvedValue({ status: 'success', message: 'ok', enabled: true, timestamp: 't' })
    api.disable.mockResolvedValue({ status: 'success', message: 'ok', enabled: false, timestamp: 't' })
    api.clearCache.mockResolvedValue({ status: 'success', message: 'ok', timestamp: 't' })
    api.resetCircuitBreakers.mockResolvedValue({ status: 'success', message: 'ok', timestamp: 't' })
  })

  it('loads the settings into the form and the status into the cards', async () => {
    const wrapper = await mountView()
    expect((wrapper.find('#wr-max_results').element as HTMLInputElement).value).toBe('5')
    expect((wrapper.find('#wr-daily_limit').element as HTMLInputElement).value).toBe('100')
    expect((wrapper.find('#wr-preferred_method').element as HTMLSelectElement).value).toBe('basic')
    expect(wrapper.find('[data-test="card-cache"]').text()).toBe('7')
    expect(wrapper.find('[data-test="card-rate"]').text()).toBe('1 / 5')
    expect(wrapper.find('[data-test="card-researcher"]').text()).toBe(copy.researcher_ok)
  })

  it('ties every numeric input to a label and states its range', async () => {
    const wrapper = await mountView()
    const label = wrapper.find('label[for="wr-max_results"]')
    expect(label.text()).toBe(copy.field_max_results)
    expect(wrapper.find('#wr-max_results').attributes('max')).toBe('50')
    expect(wrapper.find('#wr-daily_limit').attributes('max')).toBeUndefined()
  })

  it('saves only the changed fields', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
    await wrapper.find('#wr-max_results').setValue('9')
    await wrapper.find('[data-test="settings-form"]').trigger('submit')
    await flushPromises()
    expect(api.updateSettings).toHaveBeenCalledTimes(1)
    expect(api.updateSettings).toHaveBeenCalledWith({ max_results: 9 })
    expect(wrapper.text()).toContain(copy.saved)
  })

  it('blocks a save while a value is out of range', async () => {
    const wrapper = await mountView()
    await wrapper.find('#wr-max_results').setValue('99')
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="settings-form"]').trigger('submit')
    expect(api.updateSettings).not.toHaveBeenCalled()
  })

  it('the enable switch calls enable, then disable', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="enable-switch"]').trigger('click')
    await flushPromises()
    expect(api.enable).toHaveBeenCalledTimes(1)
    expect(api.disable).not.toHaveBeenCalled()
    await wrapper.find('[data-test="enable-switch"]').trigger('click')
    await flushPromises()
    expect(api.disable).toHaveBeenCalledTimes(1)
  })

  it('shows a warning, not plain success, for saved_not_applied', async () => {
    api.updateSettings.mockResolvedValue({ status: 'saved_not_applied', message: 'x', settings: { ...SETTINGS, max_results: 9 }, timestamp: 't' })
    const wrapper = await mountView()
    await wrapper.find('#wr-max_results').setValue('9')
    await wrapper.find('[data-test="settings-form"]').trigger('submit')
    await flushPromises()
    const warning = wrapper.find('[data-test="saved-not-applied"]')
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain(copy.savedNotApplied)
    expect(wrapper.text()).not.toContain(copy.saved + '\n')
  })

  it('shows the same warning when enable answers saved_not_applied', async () => {
    api.enable.mockResolvedValue({ status: 'saved_not_applied', message: 'x', enabled: true, timestamp: 't' })
    const wrapper = await mountView()
    await wrapper.find('[data-test="enable-switch"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="saved-not-applied"]').exists()).toBe(true)
  })

  it('a 503 status is an unavailable researcher, and the page still renders', async () => {
    api.getStatus.mockRejectedValue(new HttpError(503, 'Service Unavailable'))
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="researcher-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="card-researcher"]').text()).toBe(copy.researcher_unavailable)
    expect(wrapper.find('[data-test="settings-form"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain(copy.statusFailed)
  })

  it('marks exactly the settings the backend does not enforce yet', async () => {
    const wrapper = await mountView()
    const notes = wrapper.findAll('[data-test="not-enforced"]')
    expect(notes).toHaveLength(NOT_ENFORCED.length)
    notes.forEach((n) => expect(n.text()).toBe(copy.notEnforced))
    for (const key of ['auto_research_threshold', 'daily_limit', 'quality_threshold']) {
      expect(wrapper.find(`#wr-${key}`).element.parentElement!.querySelector('[data-test="not-enforced"]')).not.toBeNull()
    }
    for (const key of ['max_results', 'timeout_seconds', 'rate_limit_requests', 'rate_limit_window']) {
      expect(wrapper.find(`#wr-${key}`).element.parentElement!.querySelector('[data-test="not-enforced"]')).toBeNull()
    }
  })

  it('clears the cache, and shows reset only when there are breakers', async () => {
    let wrapper = await mountView()
    expect(wrapper.find('[data-test="reset-breakers"]').exists()).toBe(false)
    await wrapper.find('[data-test="clear-cache"]').trigger('click')
    await flushPromises()
    expect(api.clearCache).toHaveBeenCalledTimes(1)

    api.getStatus.mockResolvedValue({ ...STATUS, circuit_breakers: { duckduckgo: { state: 'open' } } })
    wrapper = await mountView()
    await wrapper.find('[data-test="reset-breakers"]').trigger('click')
    await flushPromises()
    expect(api.resetCircuitBreakers).toHaveBeenCalledTimes(1)
  })
})
