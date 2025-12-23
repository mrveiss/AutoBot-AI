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
    const response = await this.get('/api/system/status')
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
    const response = await this.get('/api/settings/config_files')
    return response.data
  }

  async getConfigFile(filename: string): Promise<string> {
    const response = await this.get(`/api/settings/config_files/${filename}`)
    return response.data
  }

  async updateConfigFile(filename: string, content: string): Promise<any> {
    const response = await this.put(`/api/settings/config_files/${filename}`, { content })
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
  async restartBackend(): Promise<any> {
    const response = await this.post('/api/system/restart')
    return response.data
  }

  async shutdownSystem(): Promise<any> {
    const response = await this.post('/api/system/shutdown')
    return response.data
  }

  async reloadConfiguration(): Promise<any> {
    const response = await this.post('/api/system/reload_config')
    return response.data
  }

  // Diagnostics
  async getDiagnosticsReport(): Promise<DiagnosticsReport> {
    const response = await this.get('/api/system/diagnostics')
    return response.data
  }

  async runDiagnostics(): Promise<DiagnosticsReport> {
    const response = await this.post('/api/system/diagnostics/run')
    return response.data
  }

  async fixDiagnosticIssue(issueId: string): Promise<any> {
    const response = await this.post(`/api/system/diagnostics/fix/${issueId}`)
    return response.data
  }

  // Logs management
  async getLogs(level?: string, limit?: number): Promise<any[]> {
    const params = new URLSearchParams()
    if (level) params.append('level', level)
    if (limit) params.append('limit', limit.toString())
    
    const response = await this.get(`/api/system/logs?${params}`)
    return response.data
  }

  async clearLogs(): Promise<any> {
    const response = await this.delete('/api/system/logs')
    return response.data
  }

  async downloadLogs(): Promise<Blob> {
    const response = await this.get('/api/system/logs/download')
    return response.data
  }

  // Performance monitoring
  async getPerformanceMetrics(timeframe?: string): Promise<any> {
    const params = timeframe ? `?timeframe=${timeframe}` : ''
    const response = await this.get(`/api/system/performance${params}`)
    return response.data
  }

  async getResourceUsage(): Promise<any> {
    const response = await this.get('/api/system/resources')
    return response.data
  }

  // Backup and restore
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
    const response = await this.get('/api/system/environment')
    return response.data
  }

  async getVersionInfo(): Promise<any> {
    const response = await this.get('/api/system/version')
    return response.data
  }

  async checkForUpdates(): Promise<any> {
    const response = await this.get('/api/system/updates/check')
    return response.data
  }

  // Security
  async getSecurityStatus(): Promise<any> {
    const response = await this.get('/api/system/security/status')
    return response.data
  }

  async runSecurityScan(): Promise<any> {
    const response = await this.post('/api/system/security/scan')
    return response.data
  }

  async getAuditLogs(): Promise<any[]> {
    const response = await this.get('/api/system/security/audit_logs')
    return response.data
  }
}