// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * System Status Management Composable
 *
 * Reactive state for the header status indicator and the System status panel.
 * The probes and the keyed rows they produce live in systemStatusServices.ts
 * (#18353); this file renders those rows through i18n, so every label and
 * status text follows the active locale and re-renders when it changes.
 */

import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'
import i18n from '@/i18n'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import {
  CLIENT_ROWS,
  DEFAULT_ROWS,
  deduplicateServices,
  fetchServiceStatus,
  fetchVmStatus,
  isBackendReachable,
  probeFailureRow,
  row,
  staleCopyOf,
  type LocalText,
  type ServiceHealthStatus,
  type ServiceRow,
} from '@/composables/systemStatusServices'

export type { FallbackResponse, ServiceHealthStatus } from '@/composables/systemStatusServices'

// #10347: poll cadence while the System Status panel is open, so a transient
// backend restart self-recovers without a manual Refresh.
const STATUS_POLL_INTERVAL_MS = 15000

/** A row as the panel shows it, in the active locale. */
export interface SystemService {
  /** Stable identity for list keys; never shown. */
  id: string
  name: string
  status: ServiceHealthStatus
  statusText: string
}

export interface SystemStatus {
  isHealthy: boolean
  hasIssues: boolean
  lastChecked: Date
  apiErrors?: boolean
  criticalError?: boolean
  // #10347: the backend API itself was unreachable, so downstream service
  // health (read THROUGH the backend) is unknown — not "down".
  backendUnreachable?: boolean
}

export interface UseSystemStatusReturn {
  // State
  systemStatus: Ref<SystemStatus>
  systemServices: ComputedRef<SystemService[]>
  showSystemStatus: Ref<boolean>

  // API utilities
  clearStatusCache: () => void

  // Computed-like getters
  getSystemStatusTooltip: () => string
  getSystemStatusAriaLabel: () => string
  getSystemStatusText: () => string
  getSystemStatusDescription: () => string

  // Methods
  toggleSystemStatus: () => void
  refreshSystemStatus: () => Promise<void>
  updateSystemStatus: () => void
}

const logger = createLogger('useSystemStatus')

const t = (key: string, params: Record<string, string | number> = {}): string => i18n.global.t(key, params)

function textOf(text: LocalText): string {
  return 'raw' in text ? text.raw : t(text.key, text.params)
}

function render(r: ServiceRow): SystemService {
  const base = textOf(r.text)
  return {
    id: r.id,
    name: textOf(r.label),
    status: r.status,
    statusText: r.lastKnown ? t('systemStatus.lastKnown', { text: base }) : base,
  }
}

/** issues | warnings | ok -- the three states every top-line string reads from. */
function level(status: SystemStatus): 'issues' | 'warnings' | 'ok' {
  if (status.hasIssues) return 'issues'
  return status.isHealthy ? 'ok' : 'warnings'
}

function countBy(rows: ServiceRow[], status: ServiceHealthStatus): number {
  return rows.filter((s) => s.status === status).length
}

function describe(rows: ServiceRow[]): string {
  const down = countBy(rows, 'error')
  const warnings = countBy(rows, 'warning')
  if (down > 0) {
    return t('systemStatus.description.downAndWarnings', {
      down: i18n.global.t('systemStatus.description.servicesDown', { n: down }, down),
      warnings: i18n.global.t('systemStatus.description.warnings', { n: warnings }, warnings),
    })
  }
  if (warnings > 0) return i18n.global.t('systemStatus.description.withWarnings', { n: warnings }, warnings)
  return t('systemStatus.description.ok')
}

export function useSystemStatus(): UseSystemStatusReturn {
  const systemStatus = ref<SystemStatus>({ isHealthy: true, hasIssues: false, lastChecked: new Date() })
  const rows = ref<ServiceRow[]>([...DEFAULT_ROWS])
  const systemServices = computed(() => rows.value.map(render))
  const showSystemStatus = ref(false)

  // GH#12866: the last per-service snapshot from a successful poll, and when.
  // A stalled probe means the current state is UNKNOWN, so the panel keeps
  // showing what it last observed, stamped, instead of three placeholders.
  const lastGoodRows = ref<ServiceRow[] | null>(null)
  const lastGoodAt = ref<Date | null>(null)

  const getSystemStatusTooltip = (): string => t(`systemStatus.tooltip.${level(systemStatus.value)}`)
  const getSystemStatusAriaLabel = (): string => t(`systemStatus.aria.${level(systemStatus.value)}`)
  const getSystemStatusText = (): string => t(`systemStatus.summary.${level(systemStatus.value)}`)
  const getSystemStatusDescription = (): string => describe(rows.value)

  const toggleSystemStatus = (): void => {
    showSystemStatus.value = !showSystemStatus.value
  }

  // #10347 / GH#12866: a failed probe does not mean the backend is down. One
  // amber backend row says degraded or unreachable; the last observed rows stay,
  // marked last known, rather than a three-row placeholder.
  function setProbeFailure(reachable: boolean): void {
    rows.value = [probeFailureRow(reachable, lastGoodAt.value), ...staleCopyOf(lastGoodRows.value), ...CLIENT_ROWS]
    systemStatus.value = {
      isHealthy: false,
      hasIssues: false,
      lastChecked: new Date(),
      apiErrors: true,
      // GH#12866: only true when /api/health also failed; reconnect banners gate on it.
      backendUnreachable: !reachable,
    }
  }

  function setObserved(observed: ServiceRow[]): void {
    rows.value = deduplicateServices([...observed, ...CLIENT_ROWS])
    lastGoodRows.value = rows.value.map((s) => ({ ...s }))
    lastGoodAt.value = new Date()
    updateSystemStatus()
  }

  const refreshSystemStatus = async (): Promise<void> => {
    try {
      const [vmRows, vmError] = await fetchVmStatus()
      const [svcRows, svcError] = await fetchServiceStatus()
      if (vmError || svcError) {
        setProbeFailure(await isBackendReachable())
        return
      }
      setObserved([...vmRows, ...svcRows])
    } catch (error: unknown) {
      logger.error('Critical error during status refresh:', error)
      setCriticalFallbackState()
    }
  }

  // #10347: auto-refresh while the panel is open (canonical usePollingJob,
  // #12701); lifecycle follows the open/close watch, not an attempt cap.
  const statusJob = usePollingJob<void>(
    async () => {
      await refreshSystemStatus()
    },
    { intervalMs: STATUS_POLL_INTERVAL_MS, maxAttempts: Number.MAX_SAFE_INTEGER },
  )

  watch(showSystemStatus, (open) => {
    statusJob.stop()
    if (open) statusJob.start('')
  })

  /** Recalculate the overall status from the current rows, without a request. */
  function updateSystemStatus(): void {
    const errors = countBy(rows.value, 'error')
    const warnings = countBy(rows.value, 'warning')
    systemStatus.value = { isHealthy: errors === 0 && warnings === 0, hasIssues: errors > 0, lastChecked: new Date() }
  }

  /** A minimal working state when an unexpected error escapes the refresh. */
  function setCriticalFallbackState(): void {
    rows.value = [row('frontend', 'healthy', 'connected'), row('backend', 'error', 'connectionFailed'), row('other', 'warning', 'statusUnknown')]
    systemStatus.value = { isHealthy: false, hasIssues: true, lastChecked: new Date(), criticalError: true }
  }

  return {
    systemStatus,
    systemServices,
    showSystemStatus,
    clearStatusCache: (): void => apiEndpointMapper.clearCache(),
    getSystemStatusTooltip,
    getSystemStatusAriaLabel,
    getSystemStatusText,
    getSystemStatusDescription,
    toggleSystemStatus,
    refreshSystemStatus,
    updateSystemStatus,
  }
}
