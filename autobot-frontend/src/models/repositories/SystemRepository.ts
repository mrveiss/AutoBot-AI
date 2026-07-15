// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { ApiRepository } from './ApiRepository'
import type { AutoBotSettings, DiagnosticsReport } from '@/types/models'
// `/api/settings/backend` returns the open-ended provider/memory/agents config
// object typed in settings.ts (distinct from the settings-section BackendSettings
// in models.ts). Aliased to make the endpoint semantics explicit at call sites.
import type { BackendSettings as BackendConfig } from '@/types/settings'
import { getApiBase } from '@/config/ssot-config'

/**
 * Backend `/api/system/health` response shape (#5212, updated #6909).
 *
 * Issue #6909: status and component values use probe vocabulary
 * ("ok" | "degraded" | "down") — the legacy "healthy"/"unhealthy" mapping
 * was retired on the backend. Frontend callers that previously checked
 * `status === 'healthy'` must now check `status === 'ok'`.
 */
export type HealthStatus = 'ok' | 'degraded' | 'down'

export interface HealthCheckResponse {
  status: HealthStatus
  timestamp?: string
  initialization?: {
    status: string
    message?: string
  }
  components?: Record<string, HealthStatus>
}

/**
 * Backend `/api/system/info` response shape (#5212).
 *
 * Previously declared a fabricated nested `{system, runtime, application}` envelope.
 * Rewritten to match the actual flat payload returned by FastAPI.
 */
export interface SystemInfoResponse {
  name: string
  version: string
  python_version: string
  timestamp?: string
  features?: Record<string, boolean>
}

/**
 * Backend `/api/system/metrics` response shape (#5212).
 *
 * Replaces the flat `SystemMetrics` from `types/models.ts`, which described
 * `cpu_usage/memory_usage/disk_usage/active_connections` fields the backend
 * never produced. The real payload is nested under `system`/`python`/`cache`.
 */
export interface SystemMetricsResponse {
  timestamp: string
  system: {
    cpu_percent: number
    memory: {
      total: number
      available: number
      percent: number
      used: number
      free: number
    }
    disk: {
      total: number
      used: number
      free: number
      percent: number
    }
  }
  python?: {
    version: string
    executable: string
  }
  cache?: {
    status: string
    total_keys: number
    memory_usage: string
    default_ttl: number
  }
}

export interface ExecuteCommandRequest {
  command: string
  timeout?: number
  working_directory?: string
  environment?: Record<string, string>
}

export interface CommandExecutionResponse {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
  execution_time: number
  command: string
}

/**
 * A single log record from `/api/logs/recent` (#5207 audit). The backend
 * wraps these in `{entries, count, limit, source}`; `getLogs` unwraps to a
 * flat `LogEntry[]`. Extra provider-specific keys are permitted.
 */
export interface LogEntry {
  timestamp?: string
  level?: string
  message?: string
  service?: string
  source_type?: string
  raw?: string
  [key: string]: unknown
}

/**
 * A single record from `/api/security/assessments`. The backend payload is
 * open-ended; only the identifying fields are typed, with a pass-through
 * index signature for the rest.
 */
export interface SecurityAssessment {
  id?: string
  status?: string
  timestamp?: string
  [key: string]: unknown
}

/**
 * Metadata for a stored backup from `/api/system/backup/*` (aspirational —
 * these endpoints are not yet implemented on the backend, see #552).
 */
export interface BackupInfo {
  id?: string
  name?: string
  created_at?: string
  size?: number
  [key: string]: unknown
}

export class SystemRepository extends ApiRepository {
  // Health and status
  // Issue #5212: Backend returns {status, timestamp, initialization, components}.
  // Previously mis-typed as {version, uptime, services} — fields that never existed.
  async checkHealth(): Promise<HealthCheckResponse> {
    const response = await this.get<HealthCheckResponse>(`${getApiBase()}/system/health`)
    const data = response.data
    return {
      status: data?.status ?? 'unknown',
      timestamp: data?.timestamp,
      initialization: data?.initialization,
      components: data?.components ?? {}
    }
  }

  async getSystemStatus(): Promise<SystemInfoResponse> {
    // Issue #552: /api/system/status doesn't exist, use /api/system/info instead
    return this.getSystemInfo()
  }

  // Issue #5212: Backend returns flat {name, version, python_version, timestamp, features}.
  // Previously mis-typed as nested {system, runtime, application} — entirely fabricated.
  async getSystemInfo(): Promise<SystemInfoResponse> {
    const response = await this.get<SystemInfoResponse>(`${getApiBase()}/system/info`)
    const data = response.data
    return {
      name: data?.name ?? 'unknown',
      version: data?.version ?? 'unknown',
      python_version: data?.python_version ?? 'unknown',
      timestamp: data?.timestamp,
      features: data?.features ?? {}
    }
  }

  // Issue #5212: Backend returns nested {timestamp, system: {cpu_percent, memory, disk}, python, cache}.
  // Previously mis-typed as flat {cpu_usage, memory_usage, disk_usage, active_connections} — never returned.
  async getSystemMetrics(): Promise<SystemMetricsResponse> {
    const response = await this.get<SystemMetricsResponse>(`${getApiBase()}/system/metrics`)
    const data = response.data
    return {
      timestamp: data?.timestamp ?? '',
      system: {
        cpu_percent: data?.system?.cpu_percent ?? 0,
        memory: {
          total: data?.system?.memory?.total ?? 0,
          available: data?.system?.memory?.available ?? 0,
          percent: data?.system?.memory?.percent ?? 0,
          used: data?.system?.memory?.used ?? 0,
          free: data?.system?.memory?.free ?? 0
        },
        disk: {
          total: data?.system?.disk?.total ?? 0,
          used: data?.system?.disk?.used ?? 0,
          free: data?.system?.disk?.free ?? 0,
          percent: data?.system?.disk?.percent ?? 0
        }
      },
      python: data?.python,
      cache: data?.cache
    }
  }

  // Settings management
  // Backend returns the section-keyed settings dict directly (no envelope) —
  // see #5214 for the audit history and the rewritten AutoBotSettings shape.
  async getSettings(): Promise<AutoBotSettings> {
    const response = await this.get<AutoBotSettings>(`${getApiBase()}/settings/`)
    return (response.data ?? {}) as AutoBotSettings
  }

  async updateSettings(settings: Partial<AutoBotSettings>): Promise<AutoBotSettings> {
    const response = await this.post<AutoBotSettings>(`${getApiBase()}/settings/`, settings)
    return (response.data ?? {}) as AutoBotSettings
  }

  async getBackendSettings(): Promise<BackendConfig> {
    const response = await this.get<BackendConfig>(`${getApiBase()}/settings/backend`)
    return (response.data ?? {}) as BackendConfig
  }

  async saveBackendSettings(settings: BackendConfig): Promise<BackendConfig> {
    const response = await this.post<BackendConfig>(`${getApiBase()}/settings/backend`, { settings })
    return (response.data ?? {}) as BackendConfig
  }

  // Config-file methods removed for #5214: backend /api/settings/config returns
  // the same section-keyed settings dict as /api/settings/ (query params ignored),
  // not a filename list or file-content string. The file-based abstraction these
  // methods declared no longer exists in the backend; audit found zero call sites.

  // Terminal operations
  // Issue #552: Fixed paths - backend uses /api/agent-terminal/* not /api/terminal/*
  async executeCommand(request: ExecuteCommandRequest): Promise<CommandExecutionResponse> {
    const response = await this.post<CommandExecutionResponse>(`${getApiBase()}/agent-terminal/execute`, request)
    return response.data as CommandExecutionResponse
  }

  async interruptProcess(): Promise<unknown> {
    // Issue #552: Backend requires session_id for interrupt
    // Using execute with interrupt flag as fallback
    const response = await this.post(`${getApiBase()}/agent-terminal/execute`, { interrupt: true })
    return response.data
  }

  async killAllProcesses(): Promise<unknown> {
    // Issue #552: Backend requires session_id for kill
    // Using execute with kill flag as fallback
    const response = await this.post(`${getApiBase()}/agent-terminal/execute`, { kill: true })
    return response.data
  }

  async getTerminalHistory(): Promise<CommandExecutionResponse[]> {
    // Issue #552: Backend uses /api/agent-terminal/sessions for history.
    // Backend returns `{status, total, sessions}`; we extract `.sessions` so
    // callers get a flat array matching the declared return type. (#5207 audit)
    const response = await this.get<{
      status?: string
      total?: number
      sessions?: CommandExecutionResponse[]
    }>(`${getApiBase()}/agent-terminal/sessions`)
    return response.data?.sessions ?? []
  }

  async clearTerminalHistory(): Promise<unknown> {
    // Issue #552: Backend doesn't have bulk delete - delete sessions individually
    const response = await this.get(`${getApiBase()}/agent-terminal/sessions`)
    return response.data
  }

  // System control
  // Issue #552: These control endpoints don't exist in backend yet - keeping paths for future implementation
  async restartBackend(): Promise<unknown> {
    // Note: Backend doesn't have /api/system/restart - this is aspirational
    const response = await this.post(`${getApiBase()}/system/restart`)
    return response.data
  }

  async shutdownSystem(): Promise<unknown> {
    // Note: Backend doesn't have /api/system/shutdown - this is aspirational
    const response = await this.post(`${getApiBase()}/system/shutdown`)
    return response.data
  }

  async reloadConfiguration(): Promise<unknown> {
    // Issue #552: Backend uses /api/system/reload_config
    const response = await this.post(`${getApiBase()}/system/reload_config`)
    return response.data
  }

  // Diagnostics
  // Issue #552: Backend uses /api/system-validation/* for diagnostics
  async getDiagnosticsReport(): Promise<DiagnosticsReport> {
    const response = await this.get<DiagnosticsReport>(`${getApiBase()}/system-validation/validate/status`)
    return response.data as DiagnosticsReport
  }

  async runDiagnostics(): Promise<DiagnosticsReport> {
    const response = await this.post<DiagnosticsReport>(`${getApiBase()}/system-validation/validate/comprehensive`)
    return response.data as DiagnosticsReport
  }

  async fixDiagnosticIssue(issueId: string): Promise<unknown> {
    // Note: No fix endpoint exists in backend - validation is read-only
    const response = await this.get(`${getApiBase()}/system-validation/validate/component/${issueId}`)
    return response.data
  }

  // Logs management
  // Issue #552: Backend uses /api/logs/* not /api/system/logs
  async getLogs(level?: string, limit?: number): Promise<LogEntry[]> {
    const params = new URLSearchParams()
    if (level) params.append('level', level)
    if (limit) params.append('limit', limit.toString())

    // Backend returns `{entries, count, limit, source}`; we extract `.entries`
    // so callers get a flat array matching the declared return type.
    // Previously cast the whole envelope to `any[]`, so `.map()`/`.filter()`
    // at call sites failed silently. (#5207 audit)
    const response = await this.get<{
      entries?: LogEntry[]
      count?: number
      limit?: number
      source?: string
    }>(`${getApiBase()}/logs/recent?${params}`)
    return response.data?.entries ?? []
  }

  async clearLogs(): Promise<unknown> {
    // Issue #552: Backend uses /api/logs/clear/{filename}
    const response = await this.delete(`${getApiBase()}/logs/clear/autobot`)
    return response.data
  }

  async downloadLogs(): Promise<Blob> {
    // Issue #552: Backend uses /api/logs/combined (docker + file logs merged)
    const response = await this.get<Blob>(`${getApiBase()}/logs/combined`)
    return response.data as Blob
  }

  // Performance monitoring
  async getPerformanceMetrics(timeframe?: string): Promise<unknown> {
    // Issue #552: Backend uses /api/monitoring/metrics/current
    const params = timeframe ? `?timeframe=${timeframe}` : ''
    const response = await this.get(`${getApiBase()}/monitoring/metrics/current${params}`)
    return response.data
  }

  async getResourceUsage(): Promise<unknown> {
    // Issue #552: Backend uses /api/service-monitor/resources
    const response = await this.get(`${getApiBase()}/service-monitor/resources`)
    return response.data
  }

  // Backup and restore
  // Issue #552: These backup endpoints don't exist in backend yet - keeping paths for future implementation
  async createBackup(): Promise<unknown> {
    const response = await this.post(`${getApiBase()}/system/backup/create`)
    return response.data
  }

  async listBackups(): Promise<BackupInfo[]> {
    const response = await this.get<BackupInfo[]>(`${getApiBase()}/system/backup/list`)
    return (response.data ?? []) as BackupInfo[]
  }

  async restoreBackup(backupId: string): Promise<unknown> {
    const response = await this.post(`${getApiBase()}/system/backup/restore/${backupId}`)
    return response.data
  }

  async deleteBackup(backupId: string): Promise<unknown> {
    const response = await this.delete(`${getApiBase()}/system/backup/${backupId}`)
    return response.data
  }

  // Environment and version info
  async getEnvironmentInfo(): Promise<SystemInfoResponse> {
    // Issue #552: Backend doesn't have /api/system/environment - use /api/system/info
    const response = await this.get<SystemInfoResponse>(`${getApiBase()}/system/info`)
    return response.data
  }

  async getVersionInfo(): Promise<unknown> {
    // Issue #552: Fixed path - backend has /api/services/version
    const response = await this.get(`${getApiBase()}/services/version`)
    return response.data
  }

  async checkForUpdates(): Promise<unknown> {
    // Note: Backend doesn't have update check - this is aspirational
    const response = await this.get(`${getApiBase()}/system/updates/check`)
    return response.data
  }

  // Security
  // Issue #552: Backend uses /api/security/* for security assessment
  async getSecurityStatus(): Promise<unknown> {
    const response = await this.get(`${getApiBase()}/security/assessments`)
    return response.data
  }

  async runSecurityScan(): Promise<unknown> {
    const response = await this.post(`${getApiBase()}/security/assessments`)
    return response.data
  }

  async getAuditLogs(): Promise<SecurityAssessment[]> {
    // Note: Backend doesn't have audit logs endpoint - using assessments
    const response = await this.get<SecurityAssessment[]>(`${getApiBase()}/security/assessments`)
    return (response.data ?? []) as SecurityAssessment[]
  }
}
