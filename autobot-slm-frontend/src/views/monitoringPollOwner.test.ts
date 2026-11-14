// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * One poll owner per monitoring route (#19851).
 *
 * MonitoringView owns the fleet poll under /monitoring/system and PerformanceView
 * owns the performance poll under /monitoring/performance/overview; the child
 * route reads the provided state instead of polling a second time, and an outage
 * shows one PollingPausedAlert per poller. Counted against the real composables,
 * the real router tree and the global `fetch`.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import { POLL_CONSECUTIVE_ERROR_LIMIT } from '@/constants/api-timeouts'
import en from '@/locales/en.json'
import MonitoringView from './MonitoringView.vue'
import { monitoringChildren } from '@/router/monitoringRoutes'
import SystemMonitor from './monitoring/SystemMonitor.vue'

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ isAdmin: false }) }))
vi.mock('@/stores/fleet', () => ({ useFleetStore: () => ({ nodeList: [] }) }))

const INTERVAL_MS = 30000
vi.mock('@/components/monitoring/GrafanaDashboard.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/monitoring/NodeGpuSummary.vue', () => ({ default: { render: () => null } }))
vi.mock('./monitoring/MetricsDetailsView.vue', () => ({ default: { render: () => null } }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function routerFor(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/monitoring', component: MonitoringView, children: monitoringChildren },
      { path: '/standalone', component: SystemMonitor },
    ],
  })
}

const App = defineComponent({ components: { RouterView }, template: '<RouterView />' })

describe('monitoring routes poll once and show one paused notice (#19851)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let down: string | null
  let wrapper: VueWrapper | null

  const calls = (needle: string) =>
    fetchMock.mock.calls.filter(([url]) => String(url).includes(needle)).length

  async function open(path: string): Promise<Router> {
    const router = routerFor()
    await router.push(path)
    await router.isReady()
    wrapper = mount(App, { global: { plugins: [i18n, router] } })
    await flushPromises()
    return router
  }

  async function tick(): Promise<void> {
    await vi.advanceTimersByTimeAsync(INTERVAL_MS)
    await flushPromises()
  }

  beforeEach(() => {
    vi.useFakeTimers()
    down = null
    wrapper = null
    fetchMock = vi.fn(async (url: unknown) => {
      if (down && String(url).includes(down)) throw new TypeError('network down')
      return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    wrapper?.unmount()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('/monitoring/system fetches the fleet dashboard once per interval', async () => {
    await open('/monitoring/system')
    expect(calls('/monitoring/dashboard')).toBe(1)
    await tick()
    expect(calls('/monitoring/dashboard')).toBe(2)
    await tick()
    expect(calls('/monitoring/dashboard')).toBe(3)
  })

  it('/monitoring/performance/overview fetches the performance overview once per interval', async () => {
    await open('/monitoring/performance/overview')
    expect(calls('/performance/overview')).toBe(1)
    await tick()
    expect(calls('/performance/overview')).toBe(2)
    await tick()
    expect(calls('/performance/overview')).toBe(3)
  })

  it('an outage on /monitoring/system shows one paused notice', async () => {
    await open('/monitoring/system')
    down = '/monitoring/'
    for (let i = 0; i < POLL_CONSECUTIVE_ERROR_LIMIT; i++) await tick()
    expect(wrapper!.findAll('[data-polling-paused]')).toHaveLength(1)
  })

  it('an outage on the performance overview shows one paused notice for the performance poll', async () => {
    await open('/monitoring/performance/overview')
    down = '/performance/'
    for (let i = 0; i < POLL_CONSECUTIVE_ERROR_LIMIT; i++) await tick()
    expect(wrapper!.findAll('[data-polling-paused]')).toHaveLength(1)
  })

  async function pauseAll(): Promise<void> {
    await open('/monitoring/performance/overview')
    down = '/'
    for (let i = 0; i < POLL_CONSECUTIVE_ERROR_LIMIT; i++) await tick()
  }

  it('a full outage on the performance overview shows one paused notice', async () => {
    await pauseAll()
    expect(wrapper!.findAll('[data-polling-paused]')).toHaveLength(1)
  })

  it('only the fleet poller failing on the performance overview shows one paused notice', async () => {
    await open('/monitoring/performance/overview')
    down = '/monitoring/'
    for (let i = 0; i < POLL_CONSECUTIVE_ERROR_LIMIT; i++) await tick()
    expect(wrapper!.findAll('[data-polling-paused]')).toHaveLength(1)
  })

  it('retry after a full outage restarts both pollers', async () => {
    await pauseAll()
    down = null
    const fleet = calls('/monitoring/dashboard')
    const perf = calls('/performance/overview')
    await wrapper!.find('[data-polling-paused] button').trigger('click')
    await flushPromises()
    expect(calls('/monitoring/dashboard')).toBe(fleet + 1)
    expect(calls('/performance/overview')).toBe(perf + 1)
    expect(wrapper!.findAll('[data-polling-paused]')).toHaveLength(0)
    await tick()
    expect(calls('/monitoring/dashboard')).toBe(fleet + 2)
    expect(calls('/performance/overview')).toBe(perf + 2)
  })

  it('a child rendered without its layout polls for itself, once', async () => {
    await open('/standalone')
    expect(calls('/monitoring/dashboard')).toBe(1)
    await tick()
    expect(calls('/monitoring/dashboard')).toBe(2)
  })

  it('the monitoring-performance route name lands on the overview', async () => {
    const router = await open('/monitoring/system')
    await router.push({ name: 'monitoring-performance' })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/monitoring/performance/overview')
  })

  it('/monitoring/performance redirects and fetches the overview once', async () => {
    const router = await open('/monitoring/performance')
    expect(router.currentRoute.value.path).toBe('/monitoring/performance/overview')
    expect(calls('/performance/overview')).toBe(1)
  })

  it('switching traces to overview starts no extra poll', async () => {
    const router = await open('/monitoring/performance/traces')
    expect(calls('/performance/overview')).toBe(1)
    await router.push('/monitoring/performance/overview')
    await flushPromises()
    expect(calls('/performance/overview')).toBe(1)
    await tick()
    expect(calls('/performance/overview')).toBe(2)
  })

  it('the fetch count stays flat after unmount', async () => {
    await open('/monitoring/performance/overview')
    wrapper!.unmount()
    wrapper = null
    const before = fetchMock.mock.calls.length
    await tick()
    await tick()
    expect(fetchMock.mock.calls.length).toBe(before)
  })

  it('a performance page renders exactly one h1', async () => {
    await open('/monitoring/performance/overview')
    expect(wrapper!.findAll('h1')).toHaveLength(1)
  })
})
