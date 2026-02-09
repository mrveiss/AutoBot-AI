// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * System Status Management Composable
 * Extracted from App.vue for better maintainability
 * Enhanced with API endpoint mapping and graceful fallbacks
 *
 * TypeScript migration of useSystemStatus.js
 */

import { ref, type Ref } from 'vue'
import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'
import { createLogger } from '@/utils/debugUtils'

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

function toHealthStatus(raw: string): ServiceHealthStatus {
  if (raw === 'online') return 'healthy'
  if (raw === 'warning') return 'warning'
  return 'error'
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
async function fetchVmStatus(): Promise<[SystemService[], boolean]> {
  const services: SystemService[] = []
  let hadError = false

  try {
    const vmResponse: FallbackResponse =
      await apiEndpointMapper.fetchWithFallback(
        '/api/service-monitor/vms/status',
        { timeout: 5000 },
      )
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
    const resp: FallbackResponse =
      await apiEndpointMapper.fetchWithFallback(
        '/api/service-monitor/services',
        { timeout: 5000 },
      )
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

  // ---- Computed-like getters ----

  const getSystemStatusTooltip = (): string => {
    if (systemStatus.value.hasIssues) {
      return 'Click to view system issues'
    } else if (!systemStatus.value.isHealthy) {
      return 'Click to view system warnings'
    }
    return 'Click to view system status - all services operational'
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

      const combined: SystemService[] = [
        ...vmServices,
        ...svcServices,
        { name: 'Frontend', status: 'healthy', statusText: 'Connected' },
        { name: 'WebSocket', status: 'healthy', statusText: 'Connected' },
      ]

      systemServices.value = deduplicateServices(combined)

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
    getSystemStatusText,
    getSystemStatusDescription,

    // Methods
    toggleSystemStatus,
    refreshSystemStatus,
    updateSystemStatus,
  }
}
