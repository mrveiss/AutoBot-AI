// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16253 — a degraded or critical backend raises one system notification carrying its status
 * details; it is refreshed while the state holds, replaced when the state changes, and removed
 * on recovery. Before, nothing raised a notification with details, so the panel never showed.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppStore } from '@/stores/useAppStore'
import { useBackendHealthNotice } from '../useBackendHealthNotice'
import type { HealthData } from '@/utils/HealthMonitor'

let failures = 0
let lastError: string | null = null
const t = (key: string) => key

function health(backend: HealthData['status']['backend'], lastCheck = 1000): HealthData {
  return {
    status: { overall: backend, backend, frontend: 'healthy', websocket: 'healthy', router: 'healthy' },
    metrics: { checksPerformed: 1, totalCheckTime: 1, averageCheckTime: 1, lastSlowCheck: null },
    timestamp: lastCheck,
    monitoring: { isActive: true, performanceBudget: { maxOverheadPerMinute: 1, currentOverhead: 0 } as never, lastCheck },
  } as HealthData
}

function setup() {
  const store = useAppStore()
  store.notificationSettings.enabled = false // no auto-hide timers in these tests
  const notice = useBackendHealthNotice(store, t, () => ({ consecutiveFailures: failures, error: lastError }))
  return { store, notice }
}

beforeEach(() => {
  setActivePinia(createPinia())
  failures = 0
  lastError = null
})

describe('useBackendHealthNotice (#16253)', () => {
  it('a degraded backend raises one warning carrying its status details', () => {
    const { store, notice } = setup()
    failures = 2
    notice.onHealthChange(health('degraded', 5000))
    expect(store.systemNotifications).toHaveLength(1)
    const [n] = store.systemNotifications
    expect(n.severity).toBe('warning')
    expect(n.title).toBe('nav.backendHealth.degradedTitle')
    expect(n.statusDetails).toMatchObject({ status: 'degraded', lastCheck: 5000, consecutiveFailures: 2 })
  })

  it('while the state holds, the same notice is refreshed, not duplicated', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('critical', 1000))
    failures = 4
    notice.onHealthChange(health('critical', 2000))
    expect(store.systemNotifications).toHaveLength(1)
    expect(store.systemNotifications[0].severity).toBe('error')
    expect(store.systemNotifications[0].statusDetails).toMatchObject({ lastCheck: 2000, consecutiveFailures: 4 })
  })

  it('a change of state replaces the notice', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('degraded'))
    notice.onHealthChange(health('critical'))
    expect(store.systemNotifications.map((n) => n.severity)).toEqual(['error'])
  })

  it('recovery removes the notice; unknown keeps what is shown', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('degraded'))
    notice.onHealthChange(health('unknown'))
    expect(store.systemNotifications).toHaveLength(1)
    notice.onHealthChange(health('healthy'))
    expect(store.systemNotifications).toHaveLength(0)
  })

  it('a healthy backend raises nothing', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('healthy'))
    expect(store.systemNotifications).toHaveLength(0)
  })

  it('carries the last failed check\'s error, so the panel can show it', () => {
    const { store, notice } = setup()
    lastError = 'Backend responded with status: 502'
    notice.onHealthChange(health('critical'))
    expect(store.systemNotifications[0].statusDetails?.error).toBe('Backend responded with status: 502')
  })

  it('a notice that was cleared while the state holds is raised again (#19305 review)', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('critical'))
    store.clearAllNotifications() // what App.vue's startup clear does
    notice.onHealthChange(health('critical'))
    expect(store.systemNotifications).toHaveLength(1)
    expect(store.systemNotifications[0].visible).toBe(true)
  })

  it('a dismissed notice stays dismissed until the state changes', () => {
    const { store, notice } = setup()
    notice.onHealthChange(health('degraded'))
    store.hideSystemNotification(store.systemNotifications[0].id)
    notice.onHealthChange(health('degraded'))
    expect(store.systemNotifications.filter((n) => n.visible)).toHaveLength(0)
    notice.onHealthChange(health('critical'))
    expect(store.systemNotifications.filter((n) => n.visible).map((n) => n.severity)).toEqual(['error'])
  })
})
