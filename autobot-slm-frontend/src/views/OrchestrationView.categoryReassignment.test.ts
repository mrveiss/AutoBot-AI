// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15224 review — the consolidation of ServicesView.vue into the
 * Orchestration per-node tab dropped the per-service category
 * (autobot/system) reassignment dropdown entirely. The static badge that
 * replaced it had no click handler and no menu, and
 * `useOrchestrationManagement.updateServiceCategory` was left exported with
 * no caller outside a composable-level test — which is exactly why that
 * test did not catch the regression: it never proved the VIEW calls it.
 *
 * This test mounts the real OrchestrationView, opens the per-node category
 * menu and picks a category, and asserts the PATCH actually goes out and
 * the fleet list is refreshed — so dropping the dropdown again fails here,
 * not just in a composable unit test.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// RedisServicePanel (also ported from ServicesView.vue) talks to the main
// AutoBot backend through a private axios instance, not the `fetch` seam
// stubbed below — irrelevant to the capability under test, so it is
// stubbed out to keep this test deterministic.
vi.mock('@/composables/useAutobotApi', () => ({
  useAutobotApi: () => ({
    getRedisServiceStatus: vi.fn().mockResolvedValue({
      status: 'running',
      uptime_seconds: 0,
      memory_used_bytes: 0,
      memory_peak_bytes: 0,
    }),
    performRedisServiceAction: vi.fn(),
  }),
  autobotApiErrorMessage: () => 'error',
}))

import OrchestrationView from './OrchestrationView.vue'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const NODE = {
  node_id: 'node-a',
  hostname: 'node-a-host',
  ip_address: '10.0.0.5',
  status: 'online',
  roles: [],
  detected_roles: [],
}

const FLEET_SERVICE = {
  service_name: 'autobot-backend',
  category: 'autobot',
  nodes: [{ node_id: 'node-a', hostname: 'node-a-host', status: 'running', ip_address: null, port: null }],
  running_count: 1,
  stopped_count: 0,
  failed_count: 0,
  total_nodes: 1,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function routeBody(url: string): unknown {
  if (url.includes('/fleet/services')) return { services: [FLEET_SERVICE], total_services: 1 }
  if (url.includes('/nodes')) return { nodes: [NODE] }
  if (url.includes('/roles/owners')) return { owners: {} }
  if (url.includes('/roles/fleet-health')) return {}
  if (url.includes('/roles')) return []
  if (url.includes('/orchestration/services')) return []
  if (url.includes('/orchestration/status')) return {}
  return {}
}

async function mountOrchestration() {
  const wrapper = mount(OrchestrationView, { global: { plugins: [i18n] } })
  await flushPromises()
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('OrchestrationView per-node tab — service category reassignment (#15224 review)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH' && String(url).includes('/category')) {
        return jsonResponse({ service_name: 'autobot-backend', category: 'system', nodes_updated: 1 })
      }
      return jsonResponse(routeBody(String(url)))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders the category as an interactive control, not a static badge', async () => {
    const wrapper = await mountOrchestration()

    const toggle = wrapper.find('.category-menu-container button')
    expect(toggle.exists(), 'no interactive category control rendered in the per-node tab').toBe(true)
  })

  it('opens the menu, PATCHes the new category, and refreshes the fleet list', async () => {
    const wrapper = await mountOrchestration()
    fetchMock.mockClear()

    await wrapper.find('.category-menu-container button').trigger('click')
    await flushPromises()

    const options = wrapper.findAll('.category-menu-container .absolute button')
    expect(options.length, 'category menu did not open').toBe(2)

    const systemOption = options.find((b) => b.text() === en.orchestrationView.system)
    expect(systemOption, 'no System option in the opened menu').toBeDefined()

    await systemOption!.trigger('click')
    await flushPromises()

    const patchCall = fetchMock.mock.calls.find(
      (c) => (c[1] as RequestInit)?.method === 'PATCH' && String(c[0]).includes('/fleet/services/autobot-backend/category')
    )
    expect(patchCall, 'no PATCH request was issued for the category change').toBeDefined()
    expect(JSON.parse((patchCall![1] as RequestInit).body as string)).toEqual({ category: 'system' })

    // ServicesView.vue's original handler refetched services after a
    // successful category change; the ported handler must too.
    const refetch = fetchMock.mock.calls.filter(
      (c) => String(c[0]).includes('/fleet/services') && !String(c[0]).includes('/category'),
    )
    expect(refetch.length, 'fleet services were not re-fetched after the category change').toBeGreaterThan(0)
  })

  it('closes the menu on an outside click without changing the category', async () => {
    const wrapper = await mountOrchestration()

    await wrapper.find('.category-menu-container button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.category-menu-container .absolute button').length).toBe(2)

    document.body.click()
    await flushPromises()

    expect(wrapper.findAll('.category-menu-container .absolute button').length).toBe(0)
  })
})
