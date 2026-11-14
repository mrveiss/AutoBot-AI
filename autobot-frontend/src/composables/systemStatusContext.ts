// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * systemStatusContext.ts - the shell's ONE shared system-status instance (#18240).
 *
 * Each `useSystemStatus()` call owns its own state, so a second call would poll
 * and display a different snapshot. App.vue calls it once and provides the
 * result under SYSTEM_STATUS_KEY; the header dot and the status panel inject it
 * here, and read one verdict (`statusTone`) so they cannot disagree.
 */

import { computed, inject, type ComputedRef, type InjectionKey } from 'vue'
import type { SystemStatus, UseSystemStatusReturn } from '@/composables/useSystemStatus'

/** Which token family a status paints with: success / warning / error. */
export type StatusTone = 'success' | 'warning' | 'error'

/** Issues -> error, not healthy -> warning, otherwise success. */
export function statusToneOf(status: SystemStatus): StatusTone {
  if (status.hasIssues) return 'error'
  return status.isHealthy ? 'success' : 'warning'
}

export const SYSTEM_STATUS_KEY: InjectionKey<UseSystemStatusReturn> = Symbol('systemStatus')

export type InjectedSystemStatus = UseSystemStatusReturn & { statusTone: ComputedRef<StatusTone> }

export function useInjectedSystemStatus(): InjectedSystemStatus {
  const status = inject(SYSTEM_STATUS_KEY)
  if (!status) throw new Error('useInjectedSystemStatus: no provider (App.vue provides SYSTEM_STATUS_KEY)')
  return { ...status, statusTone: computed(() => statusToneOf(status.systemStatus.value)) }
}
