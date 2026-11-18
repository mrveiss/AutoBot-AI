// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * InstallMetrics (#19484): the main app's monitoring figures, read from its /monitoring routes and
 * polled. Each state is said apart -- reading, data, read-but-empty, one section failed, and the
 * main app down (every read failed). A figure the backend did not report reads "Not reported",
 * never 0, and a failed poll never leaves the last reading on screen as if it were current.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import InstallMetrics from './InstallMetrics.vue'
import en from '@/locales/en.json'

const client = { get: vi.fn(), post: vi.fn() }
vi.mock('@/composables/useAutobotApi', () => ({ createAutobotBackendClient: () => client }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const L = en.monitoring.installMetrics

const ROUTES = {
  dashboard: '/monitoring/dashboard/overview',
  services: '/monitoring/services/health',
  alerts: '/monitoring/alerts/check',
  recommendations: '/monitoring/optimization/recommendations',
  gpu: '/monitoring/hardware/gpu',
  npu: '/monitoring/hardware/npu',
}

// The shape get_performance_dashboard() + the route's `analysis` block return (monitor.py, monitoring.py).
const dashboard = {
  timestamp: 1730000000,
  monitoring_active: true,
  hardware_acceleration: { gpu_available: false, npu_available: false },
  recent_alerts: [],
  system: { cpu_usage_percent: 12.5, memory_usage_percent: 48.25, cpu_load_1m: 0.4 },
  trends: {},
  analysis: { overall_health: 'healthy', performance_score: 88, bottlenecks: [], resource_utilization: {} },
}
// What the route returns when the monitor holds nothing: `analysis` is still attached, as a default.
const unmeasuredDashboard = {
  timestamp: 1730000000,
  monitoring_active: false,
  recent_alerts: [],
  analysis: { overall_health: 'healthy', performance_score: 0, bottlenecks: [], resource_utilization: {} },
}
const services = {
  total_services: 2, healthy_services: 1, degraded_services: 1, critical_services: 0, overall_status: 'degraded', health_percentage: 50,
  services: [
    { name: 'redis', host: 'h1', port: 6379, status: 'healthy', response_time_ms: 3, health_score: 99, uptime_hours: 12.5 },
    { name: 'chroma', host: 'h2', port: 8000, status: 'degraded', response_time_ms: 410, health_score: 60, uptime_hours: 1 },
  ],
}
const alerts = {
  total_count: 1, critical_count: 0, warning_count: 1,
  alerts: [{ category: 'memory', severity: 'warning', message: 'Memory is high', recommendation: 'x', timestamp: 1 }],
}
const recommendations = [
  { category: 'cache', priority: 'high', recommendation: 'Raise the cache size', action: 'Edit settings', expected_improvement: 'faster' },
]
const gpu = { available: true, name: 'GPU-X', utilization_percent: 40, memory_utilization_percent: 55.5, temperature_celsius: 61, power_watts: 120 }
const npu = { available: false, utilization_percent: 0, acceleration_ratio: 0, inference_count: 0 }

let wrapper: VueWrapper | undefined

function serve(overrides: Record<string, unknown> = {}): void {
  const body: Record<string, unknown> = { dashboard, services, alerts, recommendations, gpu, npu, ...overrides }
  client.get.mockImplementation(async (url: string) => {
    const section = Object.entries(ROUTES).find(([, path]) => path === url)?.[0]
    if (!section) throw new Error(`unrouted ${url}`)
    const value = body[section]
    if (value instanceof Error) throw value
    return value
  })
}

const down = () => new HttpError(502, 'Bad Gateway', { detail: 'upstream down' })
const allDown = () => Object.fromEntries(Object.keys(ROUTES).map((k) => [k, down()]))

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(InstallMetrics, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

const byId = (w: VueWrapper, id: string) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  vi.useFakeTimers()
  client.get.mockReset()
  serve()
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
})

describe('InstallMetrics', () => {
  it('reads the six main-backend routes and shows host, GPU, services, alerts and recommendations', async () => {
    const w = await mountView()
    for (const path of Object.values(ROUTES)) expect(client.get).toHaveBeenCalledWith(path, { maxRetries: 1 })
    expect(client.get).toHaveBeenCalledTimes(6)
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')
    expect(byId(w, 'slm-install-stat-memory').text()).toContain('48.3%')
    expect(byId(w, 'slm-install-stat-disk').exists()).toBe(false)
    expect(byId(w, 'slm-install-stat-processes').exists()).toBe(false)
    expect(byId(w, 'slm-install-stat-gpuName').text()).toContain('GPU-X')
    expect(byId(w, 'slm-install-stat-gpuTemperature').text()).toContain('61 °C')
    expect(byId(w, 'slm-install-services-summary').text()).toContain('1 of 2 services healthy')
    expect(byId(w, 'slm-install-services-table').text()).toContain('chroma')
    expect(byId(w, 'slm-install-alert').text()).toContain('Memory is high')
    expect(byId(w, 'slm-install-recommendation').text()).toContain('Raise the cache size')
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
  })

  it('shows a reading state until the first answer', async () => {
    client.get.mockImplementation(() => new Promise(() => {}))
    wrapper = mount(InstallMetrics, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(byId(wrapper, 'slm-install-loading').text()).toContain(L.loading)
    expect(byId(wrapper, 'slm-install-system').exists()).toBe(false)
  })

  it('says a field the backend left out is not reported, never 0, and a device that is absent is said absent', async () => {
    serve({ dashboard: { system: { cpu_usage_percent: 5 } } })
    const w = await mountView()
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('5.0%')
    expect(byId(w, 'slm-install-stat-memory').text()).toContain(L.notReported)
    expect(byId(w, 'slm-install-stat-performanceScore').text()).toContain(L.notReported)
    expect(byId(w, 'slm-install-stat-memory').text()).not.toContain('0.0%')
    expect(byId(w, 'slm-install-npu-absent').text()).toBe(L.npu.absent)
  })

  it('says the read is empty when every route answers with nothing, not that it failed', async () => {
    serve({
      dashboard: unmeasuredDashboard, services: { ...services, total_services: 0, healthy_services: 0, services: [] },
      alerts: { ...alerts, total_count: 0, alerts: [] }, recommendations: [], gpu: { ...gpu, available: false }, npu,
    })
    const w = await mountView()
    expect(byId(w, 'slm-install-empty').text()).toContain(L.emptyTitle)
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
    expect(byId(w, 'slm-install-section-failed').exists()).toBe(false)
    expect(byId(w, 'slm-install-system').exists()).toBe(false)
  })

  it('is not empty when only the host was measured, and not empty when only the analysis was computed', async () => {
    const quiet = { services: { ...services, total_services: 0, healthy_services: 0, services: [] }, alerts: { ...alerts, total_count: 0, alerts: [] }, recommendations: [], gpu: { ...gpu, available: false }, npu }
    serve({ ...quiet, dashboard: { ...unmeasuredDashboard, system: { cpu_usage_percent: 3, memory_usage_percent: 4 } } })
    let w = await mountView()
    expect(byId(w, 'slm-install-empty').exists()).toBe(false)
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('3.0%')
    w.unmount()
    serve({ ...quiet, dashboard: { ...unmeasuredDashboard, analysis: { overall_health: 'warning', performance_score: 0, bottlenecks: ['High CPU load'] } } })
    w = await mountView()
    expect(byId(w, 'slm-install-empty').exists()).toBe(false)
    expect(byId(w, 'slm-install-stat-overallHealth').text()).toContain('warning')
  })

  it('does not show the default analysis as a measured figure', async () => {
    serve({ dashboard: unmeasuredDashboard })
    const w = await mountView()
    expect(byId(w, 'slm-install-stat-overallHealth').text()).toContain(L.notReported)
    expect(byId(w, 'slm-install-stat-performanceScore').text()).toContain(L.notReported)
  })

  it('says not authorised, apart from unavailable, when all six reads are refused with 401 or 403', async () => {
    for (const status of [401, 403]) {
      const refused = () => new HttpError(status, 'Refused', { detail: 'no' })
      serve(Object.fromEntries(Object.keys(ROUTES).map((k) => [k, refused()])))
      const w = await mountView()
      expect(byId(w, 'slm-install-unauthorised').text()).toContain(L.unauthorisedTitle)
      expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
      w.unmount()
    }
  })

  it('keeps the unavailable state for 502/503/504 and mixed refusals', async () => {
    for (const status of [502, 503, 504]) {
      serve(Object.fromEntries(Object.keys(ROUTES).map((k) => [k, new HttpError(status, 'x', { detail: 'd' })])))
      const w = await mountView()
      expect(byId(w, 'slm-install-unavailable').exists()).toBe(true)
      expect(byId(w, 'slm-install-unauthorised').exists()).toBe(false)
      w.unmount()
    }
    const mixed = Object.fromEntries(Object.keys(ROUTES).map((k, i) => [k, i === 0 ? down() : new HttpError(403, 'x', { detail: 'd' })]))
    serve(mixed)
    const w = await mountView()
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(true)
    expect(byId(w, 'slm-install-unauthorised').exists()).toBe(false)
  })

  it('names the one section that failed, shows the rest, and draws the failed one as not reported', async () => {
    serve({ services: down() })
    const w = await mountView()
    const failed = w.findAll('[data-testid="slm-install-section-failed"]')
    expect(failed).toHaveLength(1)
    expect(failed[0].text()).toContain('Service health could not be read')
    expect(failed[0].text()).toContain('upstream down')
    expect(byId(w, 'slm-install-services-unread').text()).toBe(L.notReported)
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
  })

  it('says the main app is not available, with no figures, when every read fails', async () => {
    serve(allDown())
    const w = await mountView()
    const alert = byId(w, 'slm-install-unavailable')
    expect(alert.text()).toContain(L.unavailableTitle)
    expect(alert.text()).toContain('upstream down')
    expect(byId(w, 'slm-install-system').exists()).toBe(false)
    expect(byId(w, 'slm-install-services').exists()).toBe(false)
    expect(w.text()).not.toContain('0.0%')
  })

  it('treats a network failure (no HTTP status) as the main app being unavailable', async () => {
    serve(Object.fromEntries(Object.keys(ROUTES).map((k) => [k, new TypeError('Failed to fetch')])))
    const w = await mountView()
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(true)
    expect(byId(w, 'slm-install-stat-cpu').exists()).toBe(false)
  })

  it('drops the last reading when a later poll finds the main app down, and recovers on the next good poll', async () => {
    const w = await mountView()
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')

    serve(allDown())
    await vi.advanceTimersByTimeAsync(15000)
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(true)
    expect(byId(w, 'slm-install-stat-cpu').exists()).toBe(false)

    serve()
    await vi.advanceTimersByTimeAsync(15000)
    expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
    expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')
  })

  it('polls again every 15 seconds and on Refresh', async () => {
    const w = await mountView()
    expect(client.get).toHaveBeenCalledTimes(6)
    await vi.advanceTimersByTimeAsync(15000)
    expect(client.get).toHaveBeenCalledTimes(12)
    await byId(w, 'slm-install-refresh').trigger('click')
    await flushPromises()
    expect(client.get).toHaveBeenCalledTimes(18)
  })

  describe('circuit breaker: polling pauses on repeated failure and Retry resumes it', () => {
    const LIMIT = 5

    async function pauseWithMainAppDown(): Promise<VueWrapper> {
      serve(allDown())
      const w = await mountView()
      for (let i = 1; i < LIMIT; i++) await vi.advanceTimersByTimeAsync(15000)
      return w
    }

    it('stops reading the main app after five consecutive all-failed polls', async () => {
      const w = await pauseWithMainAppDown()
      expect(client.get).toHaveBeenCalledTimes(LIMIT * 6)
      await vi.advanceTimersByTimeAsync(60000)
      expect(client.get).toHaveBeenCalledTimes(LIMIT * 6)
      expect(w.find('[data-polling-paused]').exists()).toBe(true)
    })

    it('shows the paused notice with Retry while the screen says the main app is not available', async () => {
      const w = await pauseWithMainAppDown()
      expect(byId(w, 'slm-install-unavailable').exists()).toBe(true)
      const paused = w.find('[data-polling-paused]')
      expect(paused.exists()).toBe(true)
      expect(paused.text()).toContain(en.common.polling.retry)
    })

    it('recovers: all down, paused, main app returns, Retry shows the figures and polling resumes', async () => {
      const w = await pauseWithMainAppDown()
      serve()
      await w.find('[data-polling-paused] button').trigger('click')
      await flushPromises()
      expect(byId(w, 'slm-install-unavailable').exists()).toBe(false)
      expect(w.find('[data-polling-paused]').exists()).toBe(false)
      expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')
      const after = client.get.mock.calls.length
      await vi.advanceTimersByTimeAsync(15000)
      expect(client.get.mock.calls.length).toBe(after + 6)
    })

    it('one good poll resets the count, so failures that are not consecutive never pause', async () => {
      const w = await mountView()
      for (let round = 0; round < 3; round++) {
        serve(allDown())
        for (let i = 0; i < LIMIT - 1; i++) await vi.advanceTimersByTimeAsync(15000)
        serve()
        await vi.advanceTimersByTimeAsync(15000)
      }
      expect(w.find('[data-polling-paused]').exists()).toBe(false)
      expect(byId(w, 'slm-install-stat-cpu').text()).toContain('12.5%')
    })
  })
})
