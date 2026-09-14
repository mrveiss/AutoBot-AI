// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16245 — AdminMonitoringView colours what /system/health/detailed actually
 * sends. The overall status is the backend's probe vocabulary (ok / degraded /
 * down, #6909) and each service is healthy or unhealthy. The view used to
 * expect healthy / degraded / critical and running / stopped, so a healthy
 * backend rendered grey and every service badge yellow.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AdminMonitoringView from './AdminMonitoringView.vue'
import en from '@/locales/en.json'

const api = vi.hoisted(() => ({
  getSystemHealth: vi.fn(),
  getErrorStatistics: vi.fn(),
  getRecentErrors: vi.fn(),
  getMetricsSummary: vi.fn(),
}))

vi.mock('@/composables/useAutobotApi', () => ({ useAutobotApi: () => api }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

let wrapper: VueWrapper | null = null

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(AdminMonitoringView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

function statusBar() {
  return wrapper!.find('.border-l-4')
}

function badge(label: string) {
  const found = wrapper!.findAll('span.rounded-full').find((s) => s.text().trim() === label)
  if (!found) throw new Error(`no badge reading ${label}`)
  return found
}

describe('AdminMonitoringView health vocabulary (#16245)', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getSystemHealth.mockResolvedValue({ status: 'ok', services: [] })
    api.getErrorStatistics.mockResolvedValue({ total_errors: 0, last_24h: 0, by_level: [], resolved_count: 0 })
    api.getRecentErrors.mockResolvedValue({ errors: [] })
    api.getMetricsSummary.mockResolvedValue({ metrics: [] })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('colours an ok backend green', async () => {
    await mountView()

    expect(statusBar().classes()).toContain('bg-green-100')
  })

  it('colours a degraded backend yellow', async () => {
    api.getSystemHealth.mockResolvedValue({ status: 'degraded', services: [] })
    await mountView()

    expect(statusBar().classes()).toContain('bg-yellow-100')
  })

  it('colours a down backend red', async () => {
    api.getSystemHealth.mockResolvedValue({ status: 'down', services: [] })
    await mountView()

    expect(statusBar().classes()).toContain('bg-red-100')
  })

  it('colours each service by the healthy or unhealthy the backend sends', async () => {
    api.getSystemHealth.mockResolvedValue({
      status: 'degraded',
      services: [
        { name: 'redis', status: 'healthy' },
        { name: 'llm', status: 'unhealthy' },
      ],
    })
    await mountView()

    expect(badge('healthy').classes()).toContain('bg-green-100')
    expect(badge('unhealthy').classes()).toContain('bg-red-100')
  })

  it('drops the last report instead of showing it as current when a refresh fails', async () => {
    await mountView()
    expect(statusBar().exists()).toBe(true)

    api.getSystemHealth.mockRejectedValue(new Error('500'))
    const refresh = wrapper!.findAll('button').find((b) => b.text().includes(en.monitoring.admin.adminMonitoringView.refresh))
    await refresh!.trigger('click')
    await flushPromises()

    expect(statusBar().exists()).toBe(false)
  })
})
