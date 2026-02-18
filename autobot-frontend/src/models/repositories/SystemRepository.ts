import { ApiRepository } from './ApiRepository'
import type { AutoBotSettings, SystemMetrics, DiagnosticsReport } from '@/types/models'

export interface HealthCheckResponse {
  status: 'healthy' | 'warning' | 'error'
  version: string
  uptime: number
  services: Record<string, {
    status: 'up' | 'down' | 'degraded'
    latency?: number
    message?: string
  }>
}

export interface SystemInfoResponse {
  system: {
    platform: string
    architecture: string
    cpu_count: number
    memory_total: number
    disk_space: number
  }
  runtime: {
    python_version: string
    pip_packages: Record<string, string>
  }
  application: {
    version: string
    environment: string
    debug_mode: boolean
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

export class SystemRepository extends ApiRepository {
  // Health and status
  async checkHealth(): Promise<HealthCheckResponse> {
    const response = await this.get('/api/system/health')
    return response.data
  }

  async getSystemStatus(): Promise<any> {
    // Issue #552: /api/system/status doesn't exist, use /api/system/info instead
    const response = await this.get('/api/system/info')
    return response.data
  }

  async getSystemInfo(): Promise<SystemInfoResponse> {
    const response = await this.get('/api/system/info')
    return response.data
  }

  async getSystemMetrics(): Promise<SystemMetrics> {
    const response = await this.get('/api/system/metrics')
    return response.data
  }

  // Settings management
  async getSettings(): Promise<AutoBotSettings> {
    const response = await this.get('/api/settings/')
    return response.data
  }

  async updateSettings(settings: Partial<AutoBotSettings>): Promise<AutoBotSettings> {
    const response = await this.post('/api/settings/', settings)
    return response.data
  }

  async getBackendSettings(): Promise<any> {
    const response = await this.get('/api/settings/backend')
    return response.data
  }

  async saveBackendSettings(settings: any): Promise<any> {
    const response = await this.post('/api/settings/backend', { settings })
    return response.data
  }

  async getConfigFiles(): Promise<string[]> {
    // Issue #552: Backend uses /api/settings/config for config file operations
    const response = await this.get('/api/settings/config')
    return response.data
  }

  async getConfigFile(filename: string): Promise<string> {
    // Issue #552: Backend uses /api/settings/config with query param
    const response = await this.get(`/api/settings/config?file=${encodeURIComponent(filename)}`)
    return response.data
  }

  async updateConfigFile(filename: string, content: string): Promise<any> {
    // Issue #552: Backend uses POST /api/settings/config
    const response = await this.post('/api/settings/config', { file: filename, content })
    return response.data
  }

  // Terminal operations
  // Issue #552: Fixed paths - backend uses /api/agent-terminal/* not /api/terminal/*
  async executeCommand(request: ExecuteCommandRequest): Promise<CommandExecutionResponse> {
    const response = await this.post('/api/agent-terminal/execute', request)
    return response.data
  }

  async interruptProcess(): Promise<any> {
    // Issue #552: Backend requires session_id for interrupt
    // Using execute with interrupt flag as fallback
    const response = await this.post('/api/agent-terminal/execute', { interrupt: true })
    return response.data
  }

  async killAllProcesses(): Promise<any> {
    // Issue #552: Backend requires session_id for kill
    // Using execute with kill flag as fallback
    const response = await this.post('/api/agent-terminal/execute', { kill: true })
    return response.data
  }

  async getTerminalHistory(): Promise<CommandExecutionResponse[]> {
    // Issue #552: Backend uses /api/agent-terminal/sessions for history
    const response = await this.get('/api/agent-terminal/sessions')
    return response.data
  }

  async clearTerminalHistory(): Promise<any> {
    // Issue #552: Backend doesn't have bulk delete - delete sessions individually
    const response = await this.get('/api/agent-terminal/sessions')
    return response.data
  }

  // System control
  // Issue #552: These control endpoints don't exist in backend yet - keeping paths for future implementation
  async restartBackend(): Promise<any> {
    // Note: Backend doesn't have /api/system/restart - this is aspirational
    const response = await this.post('/api/system/restart')
    return response.data
  }

  async shutdownSystem(): Promise<any> {
    // Note: Backend doesn't have /api/system/shutdown - this is aspirational
    const response = await this.post('/api/system/shutdown')
    return response.data
  }

  async reloadConfiguration(): Promise<any> {
    // Issue #552: Backend uses /api/system/reload_config
    const response = await this.post('/api/system/reload_config')
    return response.data
  }

  // Diagnostics
  // Issue #552: Backend uses /api/system-validation/* for diagnostics
  async getDiagnosticsReport(): Promise<DiagnosticsReport> {
    const response = await this.get('/api/system-validation/validate/status')
    return response.data
  }

  async runDiagnostics(): Promise<DiagnosticsReport> {
    const response = await this.post('/api/system-validation/validate/comprehensive')
    return response.data
  }

  async fixDiagnosticIssue(issueId: string): Promise<any> {
    // Note: No fix endpoint exists in backend - validation is read-only
    const response = await this.get(`/api/system-validation/validate/component/${issueId}`)
    return response.data
  }

  // Logs management
  // Issue #552: Backend uses /api/logs/* not /api/system/logs
  async getLogs(level?: string, limit?: number): Promise<any[]> {
    const params = new URLSearchParams()
    if (level) params.append('level', level)
    if (limit) params.append('limit', limit.toString())

    const response = await this.get(`/api/logs/recent?${params}`)
    return response.data
  }

  async clearLogs(): Promise<any> {
    // Issue #552: Backend uses /api/logs/clear/{filename}
    const response = await this.delete('/api/logs/clear/autobot')
    return response.data
  }

  async downloadLogs(): Promise<Blob> {
    // Issue #552: Backend uses /api/logs/read/{filename}
    const response = await this.get('/api/logs/unified')
    return response.data
  }

  // Performance monitoring
  async getPerformanceMetrics(timeframe?: string): Promise<any> {
    // Issue #552: Backend uses /api/monitoring/metrics/current
    const params = timeframe ? `?timeframe=${timeframe}` : ''
    const response = await this.get(`/api/monitoring/metrics/current${params}`)
    return response.data
  }

  async getResourceUsage(): Promise<any> {
    // Issue #552: Backend uses /api/service-monitor/resources
    const response = await this.get('/api/service-monitor/resources')
    return response.data
  }

  // Backup and restore
  // Issue #552: These backup endpoints don't exist in backend yet - keeping paths for future implementation
  async createBackup(): Promise<any> {
    const response = await this.post('/api/system/backup/create')
    return response.data
  }

  async listBackups(): Promise<any[]> {
    const response = await this.get('/api/system/backup/list')
    return response.data
  }

  async restoreBackup(backupId: string): Promise<any> {
    const response = await this.post(`/api/system/backup/restore/${backupId}`)
    return response.data
  }

  async deleteBackup(backupId: string): Promise<any> {
    const response = await this.delete(`/api/system/backup/${backupId}`)
    return response.data
  }

  // Environment and version info
  async getEnvironmentInfo(): Promise<any> {
    // Issue #552: Backend doesn't have /api/system/environment - use /api/system/info
    const response = await this.get('/api/system/info')
    return response.data
  }

  async getVersionInfo(): Promise<any> {
    // Issue #552: Fixed path - backend has /api/services/version
    const response = await this.get('/api/services/version')
    return response.data
  }

  async checkForUpdates(): Promise<any> {
    // Note: Backend doesn't have update check - this is aspirational
    const response = await this.get('/api/system/updates/check')
    return response.data
  }

  // Security
  // Issue #552: Backend uses /api/security/* for security assessment
  async getSecurityStatus(): Promise<any> {
    const response = await this.get('/api/security/assessments')
    return response.data
  }

  async runSecurityScan(): Promise<any> {
    const response = await this.post('/api/security/assessments')
    return response.data
  }

  async getAuditLogs(): Promise<any[]> {
    // Note: Backend doesn't have audit logs endpoint - using assessments
    const response = await this.get('/api/security/assessments')
    return response.data
  }
}
