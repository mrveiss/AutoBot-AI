// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useBackendHealthNotice — one system notification while the backend is degraded or
 * critical, carrying its status details; removed when it recovers (#16253).
 *
 * The details panel in SystemStatusNotification (status, last check, consecutive failures)
 * had no producer: nothing ever raised a notification with `statusDetails`, so it rendered
 * only in Storybook. The health monitor already measures those fields, so its health changes
 * now drive the notice.
 */

import type { HealthData } from '@/utils/HealthMonitor'
import type { SystemSeverity, SystemStatusDetails } from '@/types/system'

type BackendState = HealthData['status']['backend']

interface NoticeStore {
  addSystemNotification(n: {
    severity: SystemSeverity
    title: string
    message: string
    statusDetails?: SystemStatusDetails
  }): string
  removeSystemNotification(id: string): void
  systemNotifications: Array<{ id: string; statusDetails?: SystemStatusDetails }>
}

const NOTICE_SEVERITY: Partial<Record<BackendState, SystemSeverity>> = { degraded: 'warning', critical: 'error' }

/** What the monitor knows about the backend's recent checks. */
export interface BackendCheckState {
  consecutiveFailures: number
  error?: string | null
}

export function useBackendHealthNotice(
  store: NoticeStore,
  t: (key: string) => string,
  backendChecks: () => BackendCheckState,
) {
  let notice: { id: string; state: BackendState } | null = null

  function details(health: HealthData): SystemStatusDetails {
    const checks = backendChecks()
    return {
      status: health.status.backend,
      lastCheck: health.monitoring.lastCheck,
      consecutiveFailures: checks.consecutiveFailures,
      ...(checks.error ? { error: checks.error } : {}),
      timestamp: Date.now(),
    }
  }

  function clear(): void {
    if (notice) store.removeSystemNotification(notice.id)
    notice = null
  }

  /** Apply one health change: raise, refresh, replace or clear the backend notice. */
  function onHealthChange(health: HealthData): void {
    const state = health.status.backend
    const severity = NOTICE_SEVERITY[state]
    if (!severity) {
      if (state === 'healthy') clear() // 'unknown' says nothing new: keep what is shown
      return
    }
    const shown = notice ? store.systemNotifications.find((n) => n.id === notice?.id) : undefined
    if (notice?.state === state && shown) {
      shown.statusDetails = details(health)
      return
    }
    // A notice that is gone (cleared at startup, removed) while the state holds is raised
    // again: a backend that stays down must keep saying so. A dismissed one stays in the
    // store, hidden, until the state changes.
    clear()
    const id = store.addSystemNotification({
      severity,
      title: t(`nav.backendHealth.${state}Title`),
      message: t(`nav.backendHealth.${state}Message`),
      statusDetails: details(health),
    })
    notice = { id, state }
  }

  return { onHealthChange, clear }
}
