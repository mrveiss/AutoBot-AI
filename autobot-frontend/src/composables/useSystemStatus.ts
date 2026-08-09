// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * System Status Management Composable
 * Extracted from App.vue for better maintainability
 * Enhanced with API endpoint mapping and graceful fallbacks
 *
 * TypeScript migration of useSystemStatus.js
 */

import { ref, watch, type Ref } from 'vue'
import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'
import { createLogger } from '@/utils/debugUtils'
import { usePollingJob } from '@/composables/usePollingJob'
import { getApiBase } from '@/config/ssot-config'

// #10347: poll cadence while the System Status panel is open, so a transient
// backend restart self-recovers without a manual Refresh.
const STATUS_POLL_INTERVAL_MS = 15000

// GH#12866: budget for the /api/health confirmation probe. Deliberately short —
// it only has to distinguish "not answering" from "answering slowly", and a
// long budget here would just re-add the delay the status probes already hit.
const BACKEND_HEALTH_TIMEOUT_MS = 3000

// GH#12866: budget for the two service-monitor probes. Was 5000, which sat
// *inside* the backend's measured latency distribution rather than above it:
// 40 samples on an idle single-box host gave p50=0.85s but p90=12s, so 11/40
// polls (27.5%) blew the budget while the backend was healthy and merely
// GIL-starved. A budget below p90 does not measure reachability, it measures
// whether a stall happened to be in progress.
//
// 12s clears the measured p90 and still lands inside the 15s poll cadence, so a
// slow poll cannot overlap the next one. It is not a fix for the stalls — that
// is the backend half of #12866 — only for reading them as an outage.
const STATUS_PROBE_TIMEOUT_MS = 12000

// ---------------------------------------------------------------------------
// Types & Interfaces
// ---------------------------------------------------------------------------

export type ServiceHealthStatus = 'healthy' | 'warning' | 'error'

export interface SystemService {
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

/**
 * Response-like object returned by apiEndpointMapper.fetchWithFallback().
 * Extends the standard Response shape with an optional `fallback` flag
 * that indicates the data was served from cache or default values.
 */
export interface FallbackResponse extends Response {
  fallback?: boolean
}

/** Shape of a single VM entry from /api/service-monitor/vms/status */
interface VmEntry {
  name: string
  status: string
  message?: string
}

/** Shape of a single service entry from /api/service-monitor/services */
interface BackendServiceEntry {
  status: string
  health?: string
}

/** Shape of the JSON body from /api/service-monitor/vms/status */
interface VmStatusResponse {
  vms?: VmEntry[]
}

/** Shape of the JSON body from /api/service-monitor/services */
interface ServicesResponse {
  services?: Record<string, BackendServiceEntry>
}

export interface UseSystemStatusReturn {
  // State
  systemStatus: Ref<SystemStatus>
  systemServices: Ref<SystemService[]>
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

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maps backend service keys to user-facing display names. */
const SERVICE_DISPLAY_NAMES: Record<string, string> = {
  backend: 'Backend API',
  redis: 'Redis',
  ollama: 'Ollama',
  frontend: 'Frontend',
  npu_worker: 'NPU Worker',
  browser: 'Browser Service',
  // #10285: /service-monitor/services reports this under key `chromadb` while
  // /service-monitor/vms/status reports the same health as 'AI Stack (ChromaDB)'.
  // Map both to one display name so deduplicateServices() collapses the pair.
  chromadb: 'AI Stack (ChromaDB)',
}

const DEFAULT_SERVICES: SystemService[] = [
  { name: 'Backend API', status: 'healthy', statusText: 'Running' },
  { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
  { name: 'WebSocket', status: 'healthy', statusText: 'Connected' },
  { name: 'Redis', status: 'healthy', statusText: 'Connected' },
  { name: 'Ollama', status: 'healthy', statusText: 'Connected' },
  { name: 'NPU Worker', status: 'healthy', statusText: 'Running' },
  { name: 'Browser Service', status: 'healthy', statusText: 'Running' },
]

// ---------------------------------------------------------------------------
// Module-level logger
// ---------------------------------------------------------------------------

const logger = createLogger('useSystemStatus')

// ---------------------------------------------------------------------------
// Helper: map a raw status string to ServiceHealthStatus
// ---------------------------------------------------------------------------

/**
 * Map any raw backend/VM status string to a frontend display status.
 *
 * Backend health endpoint sends: 'healthy', 'unhealthy', 'degraded'.
 * VM status endpoint may send: 'online', 'offline', 'warning'.
 * Frontend displays: 'healthy' | 'warning' | 'error'.
 *
 * Issue #2076: Added 'healthy', 'degraded', 'unhealthy' mappings.
 */
function toHealthStatus(raw: string): ServiceHealthStatus {
  const normalized = raw.toLowerCase()
  switch (normalized) {
    case 'healthy':
    case 'online':
    case 'up':
    case 'running':
    case 'available':
    case 'connected':
      return 'healthy'
    case 'degraded':
    case 'warning':
    case 'pending':
      return 'warning'
    case 'unhealthy':
    case 'error':
    case 'offline':
    case 'down':
    case 'unavailable':
    case 'not_configured':
    case 'not_initialized':
    case 'import_error':
      return 'error'
    default:
      return 'error'
  }
}

// ---------------------------------------------------------------------------
// Helper: fetchVmStatus
// ---------------------------------------------------------------------------

/**
 * Fetch VM status from backend aggregation endpoint.
 *
 * Helper for refreshSystemStatus.
 *
 * @returns Tuple of [services, hadApiError]
 */
/**
 * Is the backend actually reachable, independent of the status endpoints?
 *
 * GH#12866: the two service-monitor probes carry a 5s budget, but the backend
 * stalls in bursts — a CPU-bound scan holds the GIL and blocks the event loop
 * for 12s+, so 27.5% of polls exceeded the budget while /api/health kept
 * returning 200 and the process never restarted. Treating any probe timeout as
 * "unreachable" therefore reported a healthy backend as down roughly a quarter
 * of the time.
 *
 * /api/health is cheap, so a short budget here distinguishes "not answering at
 * all" from "answering slowly". Returns false only when the backend genuinely
 * does not respond.
 */
async function isBackendReachable(): Promise<boolean> {
  try {
    const res = (await apiEndpointMapper.fetchWithFallback(
      `${getApiBase()}/health`,
      { timeout: BACKEND_HEALTH_TIMEOUT_MS },
    )) as FallbackResponse
    return Boolean(res?.ok) && !res?.fallback
  } catch {
    return false
  }
}

async function fetchVmStatus(): Promise<[SystemService[], boolean]> {
  const services: SystemService[] = []
  let hadError = false

  try {
    const vmResponse =
      await apiEndpointMapper.fetchWithFallback(
        `${getApiBase()}/service-monitor/vms/status`,
        { timeout: STATUS_PROBE_TIMEOUT_MS },
      ) as FallbackResponse
    const vmData: VmStatusResponse = await vmResponse.json()

    if (vmResponse.fallback) {
      hadError = true
    }

    if (vmData.vms) {
      for (const vm of vmData.vms) {
        services.push({
          name: vm.name,
          status: toHealthStatus(vm.status),
          statusText: vm.message || vm.status,
        })
      }
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    logger.warn('Infrastructure endpoint failed:', message)
    hadError = true
    services.push(
      { name: 'Backend API', status: 'warning', statusText: 'Status Unknown' },
      { name: 'NPU Worker', status: 'warning', statusText: 'Status Unknown' },
      { name: 'Redis', status: 'warning', statusText: 'Status Unknown' },
    )
  }

  return [services, hadError]
}

// ---------------------------------------------------------------------------
// Helper: fetchServiceStatus
// ---------------------------------------------------------------------------

/**
 * Fetch individual service statuses from backend.
 *
 * Helper for refreshSystemStatus.
 *
 * @returns Tuple of [services, hadApiError]
 */
async function fetchServiceStatus(): Promise<[SystemService[], boolean]> {
  const services: SystemService[] = []
  let hadError = false

  try {
    const resp =
      await apiEndpointMapper.fetchWithFallback(
        `${getApiBase()}/service-monitor/services`,
        { timeout: STATUS_PROBE_TIMEOUT_MS },
      ) as FallbackResponse
    const data: ServicesResponse = await resp.json()

    if (resp.fallback) {
      hadError = true
    }

    if (data.services) {
      for (const [key, svc] of Object.entries(data.services)) {
        const displayName = SERVICE_DISPLAY_NAMES[key] || key
        services.push({
          name: displayName,
          status: toHealthStatus(svc.status),
          statusText: svc.health || svc.status,
        })
      }
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    logger.warn('Services endpoint failed:', message)
    hadError = true
    services.push(
      { name: 'Ollama', status: 'warning', statusText: 'Status Unknown' },
      { name: 'Browser Service', status: 'warning', statusText: 'Status Unknown' },
    )
  }

  return [services, hadError]
}

// ---------------------------------------------------------------------------
// Helper: stale-state presentation (GH#12866)
// ---------------------------------------------------------------------------

/** `HH:MM` in the viewer's locale, for the "as of" stamp. */
function asOf(at: Date): string {
  return at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Wording for the Backend API row when a status probe failed.
 *
 * GH#12866: the original text asserted unreachability for every probe failure.
 * On a single-box deployment there is no network to be unreachable across, so
 * that reading was not merely imprecise, it was wrong — the honest states are
 * "slow" and "stale", and only a failed /api/health means "down".
 */
function describeProbeFailure(reachable: boolean, at: Date | null): string {
  const stamp = at ? ` — status as of ${asOf(at)}` : ''
  return reachable
    ? `Degraded — status checks timed out, backend responding${stamp}`
    : `Unreachable — service status unknown${stamp}`
}

/**
 * The last observed rows, re-labelled as stale rather than re-asserted as current.
 *
 * Status is downgraded to `warning` because a green row from four minutes ago
 * must not read as a live green row; the text carries the reason.
 */
function staleCopyOf(previous: SystemService[] | null): SystemService[] {
  if (!previous) return []
  return previous
    .filter((s) => s.name !== 'Backend API' && s.name !== 'Frontend' && s.name !== 'WebSocket')
    .map((s) => ({
      name: s.name,
      status: 'warning' as const,
      statusText: `${s.statusText} (last known)`,
    }))
}

// ---------------------------------------------------------------------------
// Helper: deduplicateServices
// ---------------------------------------------------------------------------

/**
 * Remove duplicate services, preferring the healthy entry when there is a
 * conflict between two entries sharing the same name.
 *
 * Helper for refreshSystemStatus.
 */
function deduplicateServices(services: SystemService[]): SystemService[] {
  return services.reduce<SystemService[]>((acc, service) => {
    const existing = acc.find((s) => s.name === service.name)
    if (!existing) {
      acc.push(service)
    } else if (
      service.status === 'healthy' &&
      existing.status !== 'healthy'
    ) {
      Object.assign(existing, service)
    }
    return acc
  }, [])
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useSystemStatus(): UseSystemStatusReturn {
  // ---- Reactive state ----

  const systemStatus = ref<SystemStatus>({
    isHealthy: true,
    hasIssues: false,
    lastChecked: new Date(),
  })

  const systemServices = ref<SystemService[]>([...DEFAULT_SERVICES])

  const showSystemStatus = ref(false)

  // GH#12866: the last per-service snapshot that came from a successful poll,
  // and when it was taken. A stalled probe means the current state is UNKNOWN,
  // not that seven services went down — so the panel keeps showing what it last
  // actually observed, stamped, instead of replacing eight rows with three
  // placeholders that read as "everything else disappeared".
  const lastGoodServices = ref<SystemService[] | null>(null)
  const lastGoodAt = ref<Date | null>(null)

  // ---- Computed-like getters ----

  const getSystemStatusTooltip = (): string => {
    if (systemStatus.value.hasIssues) {
      return 'Click to view system issues'
    } else if (!systemStatus.value.isHealthy) {
      return 'Click to view system warnings'
    }
    return 'Click to view system status - all services operational'
  }

  const getSystemStatusAriaLabel = (): string => {
    if (systemStatus.value.hasIssues) {
      return 'System status: issues detected'
    } else if (!systemStatus.value.isHealthy) {
      return 'System status: warnings present'
    }
    return 'System status: all services operational'
  }

  const getSystemStatusText = (): string => {
    if (systemStatus.value.hasIssues) {
      return 'System Issues Detected'
    } else if (!systemStatus.value.isHealthy) {
      return 'System Warnings'
    }
    return 'All Systems Operational'
  }

  const getSystemStatusDescription = (): string => {
    const errorCount = systemServices.value.filter(
      (s) => s.status === 'error',
    ).length
    const warningCount = systemServices.value.filter(
      (s) => s.status === 'warning',
    ).length

    if (errorCount > 0) {
      const eSuffix = errorCount > 1 ? 's' : ''
      const wSuffix = warningCount !== 1 ? 's' : ''
      return `${errorCount} service${eSuffix} down, ${warningCount} warning${wSuffix}`
    } else if (warningCount > 0) {
      const suffix = warningCount > 1 ? 's' : ''
      return `${warningCount} service${suffix} with warnings`
    }
    return 'All services running normally'
  }

  // ---- Methods ----

  const toggleSystemStatus = (): void => {
    showSystemStatus.value = !showSystemStatus.value
  }

  /**
   * Orchestrates a full system-status refresh by fetching VM and service
   * data, deduplicating, and updating reactive state.
   */
  const refreshSystemStatus = async (): Promise<void> => {
    try {
      const [vmServices, vmError] = await fetchVmStatus()
      const [svcServices, svcError] = await fetchServiceStatus()
      const hasApiErrors = vmError || svcError

      // GH#12866: a failed status probe does not mean the backend is down.
      // Confirm with a cheap /api/health call before declaring it unreachable,
      // so a burst of event-loop stalls reads as "degraded" rather than "down".
      const reachable = hasApiErrors ? await isBackendReachable() : true

      // #10347: NPU/Redis/Ollama/Browser are read THROUGH the backend's
      // /api/service-monitor/*. If the backend API itself is unreachable
      // (e.g. a ~20-30s restart), we don't know their state — show ONE
      // amber "backend unreachable" row, not five false red "down"s.
      if (hasApiErrors) {
        systemServices.value = [
          {
            name: 'Backend API',
            status: 'warning',
            statusText: describeProbeFailure(reachable, lastGoodAt.value),
          },
          // GH#12866: keep the last observed rows rather than dropping to a
          // three-row placeholder. The probe failing says nothing about Redis,
          // Ollama or the NPU worker — their state is simply as of the stamp
          // above. Dropping them made a slow poll look like a fleet outage.
          ...staleCopyOf(lastGoodServices.value),
          { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
          { name: 'WebSocket', status: 'healthy', statusText: 'Connected' },
        ]
        systemStatus.value = {
          isHealthy: false,
          hasIssues: false,
          lastChecked: new Date(),
          apiErrors: true,
          // GH#12866: only true when /api/health also failed. Consumers gate
          // reconnect banners on this, so a slow poll must not trigger them.
          backendUnreachable: !reachable,
        }
        return
      }

      const combined: SystemService[] = [
        ...vmServices,
        ...svcServices,
        { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
        { name: 'WebSocket', status: 'healthy', statusText: 'Connected' },
      ]

      systemServices.value = deduplicateServices(combined)

      // GH#12866: this poll actually observed the fleet — remember it, so the
      // next stalled poll can show it stamped instead of showing nothing.
      lastGoodServices.value = systemServices.value.map((s) => ({ ...s }))
      lastGoodAt.value = new Date()

      const hasErrors = systemServices.value.some(
        (s) => s.status === 'error',
      )
      const hasWarnings = systemServices.value.some(
        (s) => s.status === 'warning',
      )

      systemStatus.value = {
        isHealthy: !hasErrors && !hasWarnings,
        hasIssues: hasErrors,
        lastChecked: new Date(),
        apiErrors: hasApiErrors,
      }
    } catch (error: unknown) {
      logger.error('Critical error during status refresh:', error)
      setCriticalFallbackState()
    }
  }

  // #10347: auto-refresh while the panel is open so a transient backend
  // restart self-recovers without a manual Refresh. Polls only while shown
  // (no cost when closed); cleaned up on scope teardown.
  // Backed by the canonical usePollingJob (#12701): fires immediately on start
  // then re-polls every STATUS_POLL_INTERVAL_MS, with auto scope-dispose cleanup.
  // maxAttempts is effectively unlimited — lifecycle is driven by the panel
  // open/close watch below, not an attempt cap. refreshSystemStatus never throws
  // (internal try/catch → fallback state), so no error-backoff path applies.
  const statusJob = usePollingJob<void>(
    async () => { await refreshSystemStatus() },
    { intervalMs: STATUS_POLL_INTERVAL_MS, maxAttempts: Number.MAX_SAFE_INTEGER },
  )
  watch(showSystemStatus, (open) => {
    statusJob.stop()
    if (open) {
      statusJob.start('')
    }
  })

  /**
   * Manually recalculate system status from the current services list
   * without performing any network requests.
   */
  const updateSystemStatus = (): void => {
    const errorCount = systemServices.value.filter(
      (s) => s.status === 'error',
    ).length
    const warningCount = systemServices.value.filter(
      (s) => s.status === 'warning',
    ).length

    systemStatus.value = {
      isHealthy: errorCount === 0 && warningCount === 0,
      hasIssues: errorCount > 0,
      lastChecked: new Date(),
    }
  }

  /**
   * Set a minimal working state when a critical (unexpected) error occurs
   * so the application does not break entirely.
   *
   * Helper for refreshSystemStatus.
   */
  function setCriticalFallbackState(): void {
    systemServices.value = [
      { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
      { name: 'Backend API', status: 'error', statusText: 'Connection Failed' },
      { name: 'Other Services', status: 'warning', statusText: 'Status Unknown' },
    ]

    systemStatus.value = {
      isHealthy: false,
      hasIssues: true,
      lastChecked: new Date(),
      criticalError: true,
    }
  }

  // ---- Public API ----

  return {
    // State
    systemStatus,
    systemServices,
    showSystemStatus,

    // API utilities
    clearStatusCache: (): void => apiEndpointMapper.clearCache(),

    // Computed-like getters
    getSystemStatusTooltip,
    getSystemStatusAriaLabel,
    getSystemStatusText,
    getSystemStatusDescription,

    // Methods
    toggleSystemStatus,
    refreshSystemStatus,
    updateSystemStatus,
  }
}
