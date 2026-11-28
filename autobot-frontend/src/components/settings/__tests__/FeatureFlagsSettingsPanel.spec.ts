// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * FeatureFlagsSettingsPanel talks to the backend through the typed `apiClient.call` (#12363 slice 4):
 * the status and metrics load, a mode change and an endpoint override each hit the contract path with
 * the documented path params, query and body. These replace the retired FeatureFlagsApiClient spec.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const call = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...args: unknown[]) => call(...args) } }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))

const STATUS = {
  success: true,
  data: { current_mode: 'log_only', history: [], endpoint_overrides: {}, total_endpoints_configured: 0 },
}
const METRICS = { success: true, data: { total_violations: 0, period_days: 7, by_endpoint: {}, by_user: {}, by_day: {}, current_mode: 'log_only' } }

async function mountPanel() {
  const { default: Panel } = await import('../FeatureFlagsSettingsPanel.vue')
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const wrapper = mount(Panel, {
    global: {
      plugins: [i18n],
      stubs: { EnforcementModeSelector: true, EndpointEnforcement: true, FlagChangeHistory: true, AccessMetrics: true, BaseAlert: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe('FeatureFlagsSettingsPanel typed calls', () => {
  beforeEach(() => {
    call.mockReset().mockImplementation(async (method: string, path: string) => {
      if (path === '/api/admin/feature-flags/status') return STATUS
      if (path === '/api/admin/access-control/metrics') return METRICS
      return { success: true, message: 'ok' }
    })
  })

  it('loads the status and 7-day metrics on mount', async () => {
    await mountPanel()
    expect(call).toHaveBeenCalledWith('get', '/api/admin/feature-flags/status')
    expect(call).toHaveBeenCalledWith('get', '/api/admin/access-control/metrics', {
      query: { days: 7, include_details: true },
    })
  })

  it('PUTs the new mode, then reloads', async () => {
    const wrapper = await mountPanel()
    wrapper.findComponent({ name: 'EnforcementModeSelector' }).vm.$emit('update:mode', 'enforced')
    await flushPromises()
    expect(call).toHaveBeenCalledWith('put', '/api/admin/feature-flags/enforcement-mode', { body: { mode: 'enforced' } })
    expect(call.mock.calls.filter(([, p]) => p === '/api/admin/feature-flags/status')).toHaveLength(2)
  })

  it('sets and removes an endpoint override with the endpoint as a path parameter', async () => {
    const wrapper = await mountPanel()
    const overrides = wrapper.findComponent({ name: 'EndpointEnforcement' })
    overrides.vm.$emit('add', '/api/chat', 'enforced')
    await flushPromises()
    overrides.vm.$emit('remove', '/api/chat')
    await flushPromises()
    expect(call).toHaveBeenCalledWith('put', '/api/admin/feature-flags/endpoint/{endpoint}', {
      path: { endpoint: '/api/chat' },
      body: { mode: 'enforced' },
    })
    expect(call).toHaveBeenCalledWith('delete', '/api/admin/feature-flags/endpoint/{endpoint}', { path: { endpoint: '/api/chat' } })
  })

  it('keeps the status when only the metrics call rejects', async () => {
    // a fresh object: the mode-change test above mutates the shared STATUS in place
    const status = { ...STATUS, data: { ...STATUS.data, current_mode: 'log_only' } }
    call.mockImplementation(async (method: string, path: string) => {
      if (path === '/api/admin/feature-flags/status') return status
      if (path === '/api/admin/access-control/metrics') throw new Error('HTTP 500')
      return { success: true, message: 'ok' }
    })
    const wrapper = await mountPanel()
    expect(wrapper.find('.error-state').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'EnforcementModeSelector' }).props('currentMode')).toBe('log_only')
  })

  it('stays fatal when the status call rejects', async () => {
    call.mockImplementation(async (method: string, path: string) => {
      if (path === '/api/admin/feature-flags/status') throw new Error('HTTP 500')
      return METRICS
    })
    const wrapper = await mountPanel()
    expect(wrapper.find('.error-state').exists()).toBe(true)
  })
})
