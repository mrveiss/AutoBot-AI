// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #13138 — a blue-green deployment in the `monitoring` status showed up
 * in NO stat tile at all.
 *
 * `BlueGreenStatus` (types/slm.ts) omitted `'monitoring'`, the post-deployment
 * health-watch state the backend sets at services/blue_green.py:780 and holds
 * for up to `post_deploy_monitor_duration` seconds. `bgStats.active` tested a
 * hard-coded list that did not include it, `completed`/`failed`/`rolledBack`
 * did not match either, and `getStatusClass` fell through to the neutral gray
 * default — so a deployment being actively health-watched simply vanished from
 * the dashboard, and its badge claimed nothing was happening.
 *
 * Deriving `BlueGreenDeployment` from the generated contract restored the
 * fields the health-watch reports (`health_failures`,
 * `health_failure_threshold`, `monitoring_started_at`,
 * `post_deploy_monitor_duration`), which the hand-written type omitted
 * entirely.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { ref, computed } from 'vue'
import en from '@/locales/en.json'
import type { BlueGreenDeployment, BlueGreenStatus } from '@/types/slm'

function makeBgDeployment(status: BlueGreenStatus): BlueGreenDeployment {
  return {
    id: 1,
    bg_deployment_id: 'bg-1',
    blue_node_id: 'node-blue',
    blue_roles: ['backend'],
    green_node_id: 'node-green',
    green_original_roles: [],
    borrowed_roles: ['backend'],
    purge_on_complete: true,
    deployment_type: 'upgrade',
    health_check_url: null,
    health_check_interval: 10,
    health_check_timeout: 300,
    health_failure_threshold: 3,
    health_failures: 0,
    monitoring_started_at: '2026-07-31T12:00:00Z',
    post_deploy_monitor_duration: 1800,
    auto_rollback: true,
    status,
    progress_percent: 100,
    current_step: 'post-deploy monitoring',
    error: null,
    started_at: '2026-07-31T11:00:00Z',
    switched_at: '2026-07-31T11:59:00Z',
    completed_at: null,
    rollback_at: null,
    triggered_by: 'admin',
    created_at: '2026-07-31T11:00:00Z',
    updated_at: '2026-07-31T12:00:00Z',
  }
}

let bgDeploymentsImpl: BlueGreenDeployment[] = []

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({
    getDeployments: vi.fn().mockResolvedValue([]),
    getBlueGreenDeployments: vi.fn(async () => ({
      deployments: bgDeploymentsImpl,
      total: bgDeploymentsImpl.length,
      page: 1,
      per_page: 20,
    })),
    getRoleOwners: vi.fn().mockResolvedValue({}),
  }),
}))

vi.mock('@/composables/useSlmWebSocket', () => ({
  useSlmWebSocket: () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribeAll: vi.fn(),
    onDeploymentStatus: vi.fn(),
    onRollbackEvent: vi.fn(),
  }),
}))

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    nodeList: computed(() => []),
    roles: ref([]),
    fetchNodes: vi.fn().mockResolvedValue(undefined),
    fetchRoles: vi.fn().mockResolvedValue(undefined),
    getNode: vi.fn().mockReturnValue(undefined),
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

import DeploymentsView from './DeploymentsView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

/**
 * The blue-green "Active" tile. Two `text-blue-600` stat numbers exist —
 * standard `inProgress` first, then blue-green `active` — and `v-show` keeps
 * both in the DOM, so take the last.
 */
function activeTileCount(wrapper: VueWrapper): string {
  const tiles = wrapper.findAll('p.text-2xl.font-bold.text-blue-600')
  return tiles.length > 0 ? tiles[tiles.length - 1].text() : ''
}

async function mountWith(status: BlueGreenStatus) {
  bgDeploymentsImpl = [makeBgDeployment(status)]
  const wrapper = mount(DeploymentsView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('DeploymentsView blue-green stats (#13138)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    bgDeploymentsImpl = []
  })

  it('counts a deployment in post-deploy monitoring as active', async () => {
    const wrapper = await mountWith('monitoring')
    expect(activeTileCount(wrapper)).toBe('1')
  })

  it('gives the monitoring status the in-flight badge, not the neutral default', async () => {
    const wrapper = await mountWith('monitoring')
    expect(wrapper.html()).toContain('bg-blue-100 text-blue-800')
  })

  it('still counts the pre-existing in-flight statuses', async () => {
    for (const status of [
      'borrowing',
      'deploying',
      'verifying',
      'switching',
      'active',
    ] as BlueGreenStatus[]) {
      const wrapper = await mountWith(status)
      expect(activeTileCount(wrapper)).toBe('1')
    }
  })

  it('does not count a terminal status as active', async () => {
    const wrapper = await mountWith('completed')
    expect(activeTileCount(wrapper)).toBe('0')
  })
})
