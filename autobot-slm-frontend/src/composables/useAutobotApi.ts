// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AutoBot Backend API Composable
 *
 * Provides REST API integration for the main AutoBot backend (172.16.168.20:8001).
 * Used for settings, tools, and monitoring functionality that requires the main backend.
 * Issue #729 - Migrating admin functionality to SLM.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'

// AutoBot backend is proxied via nginx at /autobot-api/
const API_BASE = '/autobot-api'

// Type definitions for AutoBot API responses

export interface SettingsResponse {
  settings: Record<string, unknown>
  last_modified: string
}

export interface UserResponse {
  id: string
  username: string
  email?: string
  roles: string[]
  created_at: string
  last_login?: string
}

export interface CacheConfig {
  enabled: boolean
  ttl_seconds: number
  max_size_mb: number
  eviction_policy: string
}

export interface CacheStats {
  hits: number
  misses: number
  size_mb: number
  entries: number
}

export interface LogForwardingDestination {
  id: string
  name: string
  type: 'syslog' | 'http' | 'file' | 'elasticsearch'
  enabled: boolean
  config: Record<string, unknown>
}

export interface NPUWorker {
  id: string
  hostname: string
  ip_address: string
  status: 'online' | 'offline' | 'busy' | 'error'
  capabilities: string[]
  current_load: number
  last_heartbeat: string
}

export interface PermissionRule {
  id: string
  pattern: string
  action: 'allow' | 'deny' | 'ask'
  scope: string
  enabled: boolean
}

export interface PromptTemplate {
  id: string
  name: string
  content: string
  category: string
  is_default: boolean
  modified_at: string
}

export interface FileItem {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number
  modified?: string
  permissions?: string
}

export interface MCPServer {
  id: string
  name: string
  type: string
  status: 'running' | 'stopped' | 'error'
  config: Record<string, unknown>
}

export interface Agent {
  id: string
  name: string
  type: string
  status: 'active' | 'inactive'
  config: Record<string, unknown>
}

export interface RUMMetrics {
  page_views: number
  unique_users: number
  avg_load_time_ms: number
  error_count: number
  timestamp: string
}

export function useAutobotApi() {
  const authStore = useAuthStore()

  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 30000,
  })

  // Add auth token to all requests
  client.interceptors.request.use((config) => {
    // Try SLM token first, fallback to AutoBot token
    const token = authStore.token || localStorage.getItem('autobot_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Response interceptor for error handling
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        // Token expired or invalid
        localStorage.removeItem('autobot_access_token')
      }
      return Promise.reject(error)
    }
  )

  // =============================================================================
  // Settings API
  // =============================================================================

  async function getSettings(): Promise<SettingsResponse> {
    const response = await client.get<SettingsResponse>('/settings')
    return response.data
  }

  async function updateSettings(settings: Record<string, unknown>): Promise<SettingsResponse> {
    const response = await client.put<SettingsResponse>('/settings', settings)
    return response.data
  }

  async function getSettingsSection(section: string): Promise<Record<string, unknown>> {
    const response = await client.get(`/settings/${section}`)
    return response.data
  }

  async function updateSettingsSection(
    section: string,
    data: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const response = await client.put(`/settings/${section}`, data)
    return response.data
  }

  // =============================================================================
  // User Management API
  // =============================================================================

  async function getUsers(): Promise<UserResponse[]> {
    const response = await client.get<{ users: UserResponse[] }>('/users')
    return response.data.users
  }

  async function createUser(userData: {
    username: string
    password: string
    email?: string
    roles?: string[]
  }): Promise<UserResponse> {
    const response = await client.post<UserResponse>('/users', userData)
    return response.data
  }

  async function updateUser(
    userId: string,
    data: Partial<UserResponse & { password?: string }>
  ): Promise<UserResponse> {
    const response = await client.patch<UserResponse>(`/users/${userId}`, data)
    return response.data
  }

  async function deleteUser(userId: string): Promise<void> {
    await client.delete(`/users/${userId}`)
  }

  // =============================================================================
  // Cache API
  // =============================================================================

  async function getCacheConfig(): Promise<CacheConfig> {
    const response = await client.get<CacheConfig>('/cache/config')
    return response.data
  }

  async function updateCacheConfig(config: Partial<CacheConfig>): Promise<CacheConfig> {
    const response = await client.put<CacheConfig>('/cache/config', config)
    return response.data
  }

  async function getCacheStats(): Promise<CacheStats> {
    const response = await client.get<CacheStats>('/cache/stats')
    return response.data
  }

  async function clearCache(cacheType?: string): Promise<{ cleared: number }> {
    const params = cacheType ? `?type=${cacheType}` : ''
    const response = await client.post<{ cleared: number }>(`/cache/clear${params}`)
    return response.data
  }

  async function warmupCache(): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>('/cache/warmup')
    return response.data
  }

  // =============================================================================
  // Log Forwarding API
  // =============================================================================

  async function getLogForwardingDestinations(): Promise<LogForwardingDestination[]> {
    const response = await client.get<{ destinations: LogForwardingDestination[] }>(
      '/log-forwarding/destinations'
    )
    return response.data.destinations
  }

  async function createLogForwardingDestination(
    destination: Omit<LogForwardingDestination, 'id'>
  ): Promise<LogForwardingDestination> {
    const response = await client.post<LogForwardingDestination>(
      '/log-forwarding/destinations',
      destination
    )
    return response.data
  }

  async function updateLogForwardingDestination(
    id: string,
    data: Partial<LogForwardingDestination>
  ): Promise<LogForwardingDestination> {
    const response = await client.patch<LogForwardingDestination>(
      `/log-forwarding/destinations/${id}`,
      data
    )
    return response.data
  }

  async function deleteLogForwardingDestination(id: string): Promise<void> {
    await client.delete(`/log-forwarding/destinations/${id}`)
  }

  async function testLogForwardingDestination(
    id: string
  ): Promise<{ success: boolean; message: string }> {
    const response = await client.post<{ success: boolean; message: string }>(
      `/log-forwarding/destinations/${id}/test`
    )
    return response.data
  }

  // =============================================================================
  // NPU Workers API
  // =============================================================================

  async function getNPUWorkers(): Promise<NPUWorker[]> {
    const response = await client.get<{ workers: NPUWorker[] }>('/npu-workers')
    return response.data.workers
  }

  async function getNPUWorker(workerId: string): Promise<NPUWorker> {
    const response = await client.get<NPUWorker>(`/npu-workers/${workerId}`)
    return response.data
  }

  async function updateNPUWorker(
    workerId: string,
    data: Partial<NPUWorker>
  ): Promise<NPUWorker> {
    const response = await client.patch<NPUWorker>(`/npu-workers/${workerId}`, data)
    return response.data
  }

  async function restartNPUWorker(workerId: string): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>(`/npu-workers/${workerId}/restart`)
    return response.data
  }

  // Missing NPU Worker methods (Issue #729)
  async function getNPULoadBalancingConfig(): Promise<Record<string, unknown>> {
    const response = await client.get('/npu-workers/load-balancing/config')
    return response.data
  }

  async function updateNPULoadBalancingConfig(config: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await client.put('/npu-workers/load-balancing/config', config)
    return response.data
  }

  async function pairNPUWorker(workerId: string, data: { hostname: string; ip_address: string }): Promise<NPUWorker> {
    const response = await client.post<NPUWorker>(`/npu-workers/${workerId}/pair`, data)
    return response.data
  }

  async function testNPUWorker(workerId: string): Promise<{ success: boolean; latency_ms: number; message: string }> {
    const response = await client.post<{ success: boolean; latency_ms: number; message: string }>(`/npu-workers/${workerId}/test`)
    return response.data
  }

  async function removeNPUWorker(workerId: string): Promise<void> {
    await client.delete(`/npu-workers/${workerId}`)
  }

  // =============================================================================
  // Permission API
  // =============================================================================

  async function getPermissionRules(): Promise<PermissionRule[]> {
    const response = await client.get<{ rules: PermissionRule[] }>('/permissions/rules')
    return response.data.rules
  }

  async function createPermissionRule(
    rule: Omit<PermissionRule, 'id'>
  ): Promise<PermissionRule> {
    const response = await client.post<PermissionRule>('/permissions/rules', rule)
    return response.data
  }

  async function updatePermissionRule(
    id: string,
    data: Partial<PermissionRule>
  ): Promise<PermissionRule> {
    const response = await client.patch<PermissionRule>(`/permissions/rules/${id}`, data)
    return response.data
  }

  async function deletePermissionRule(id: string): Promise<void> {
    await client.delete(`/permissions/rules/${id}`)
  }

  // =============================================================================
  // Prompts API
  // =============================================================================

  async function getPromptTemplates(): Promise<PromptTemplate[]> {
    const response = await client.get<{ templates: PromptTemplate[] }>('/prompts')
    return response.data.templates
  }

  async function getPromptTemplate(id: string): Promise<PromptTemplate> {
    const response = await client.get<PromptTemplate>(`/prompts/${id}`)
    return response.data
  }

  async function createPromptTemplate(
    template: Omit<PromptTemplate, 'id' | 'modified_at'>
  ): Promise<PromptTemplate> {
    const response = await client.post<PromptTemplate>('/prompts', template)
    return response.data
  }

  async function updatePromptTemplate(
    id: string,
    data: Partial<PromptTemplate>
  ): Promise<PromptTemplate> {
    const response = await client.patch<PromptTemplate>(`/prompts/${id}`, data)
    return response.data
  }

  async function deletePromptTemplate(id: string): Promise<void> {
    await client.delete(`/prompts/${id}`)
  }

  async function revertPromptToDefault(id: string): Promise<PromptTemplate> {
    const response = await client.post<PromptTemplate>(`/prompts/${id}/revert`)
    return response.data
  }

  // =============================================================================
  // Files API
  // =============================================================================

  async function listFiles(path: string, host?: string): Promise<FileItem[]> {
    const params = new URLSearchParams({ path })
    if (host) params.append('host', host)
    const response = await client.get<{ files: FileItem[] }>(`/files?${params}`)
    return response.data.files
  }

  async function readFile(path: string, host?: string): Promise<string> {
    const params = new URLSearchParams({ path })
    if (host) params.append('host', host)
    const response = await client.get<{ content: string }>(`/files/read?${params}`)
    return response.data.content
  }

  async function writeFile(path: string, content: string, host?: string): Promise<void> {
    await client.post('/files/write', { path, content, host })
  }

  async function deleteFile(path: string, host?: string): Promise<void> {
    const params = new URLSearchParams({ path })
    if (host) params.append('host', host)
    await client.delete(`/files?${params}`)
  }

  async function uploadFile(
    path: string,
    file: File,
    host?: string,
    onProgress?: (progress: number) => void
  ): Promise<void> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('path', path)
    if (host) formData.append('host', host)

    const config: AxiosRequestConfig = {
      headers: { 'Content-Type': 'multipart/form-data' },
    }
    if (onProgress) {
      config.onUploadProgress = (progressEvent) => {
        const progress = progressEvent.total
          ? Math.round((progressEvent.loaded * 100) / progressEvent.total)
          : 0
        onProgress(progress)
      }
    }

    await client.post('/files/upload', formData, config)
  }

  // =============================================================================
  // MCP Registry API
  // =============================================================================

  async function getMCPServers(): Promise<MCPServer[]> {
    const response = await client.get<{ servers: MCPServer[] }>('/mcp/servers')
    return response.data.servers
  }

  async function getMCPServer(id: string): Promise<MCPServer> {
    const response = await client.get<MCPServer>(`/mcp/servers/${id}`)
    return response.data
  }

  async function startMCPServer(id: string): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>(`/mcp/servers/${id}/start`)
    return response.data
  }

  async function stopMCPServer(id: string): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>(`/mcp/servers/${id}/stop`)
    return response.data
  }

  async function restartMCPServer(id: string): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>(`/mcp/servers/${id}/restart`)
    return response.data
  }

  async function getMCPBridges(): Promise<Record<string, unknown>[]> {
    const response = await client.get<{ bridges: Record<string, unknown>[] }>('/mcp/bridges')
    return response.data.bridges
  }

  async function getMCPTools(): Promise<Record<string, unknown>[]> {
    const response = await client.get<{ tools: Record<string, unknown>[] }>('/mcp/tools')
    return response.data.tools
  }

  async function getMCPHealth(): Promise<Record<string, unknown>> {
    const response = await client.get('/mcp/health')
    return response.data
  }

  async function getMCPStats(): Promise<Record<string, unknown>> {
    const response = await client.get('/mcp/stats')
    return response.data
  }

  // =============================================================================
  // Agents API
  // =============================================================================

  async function getAgents(): Promise<Agent[]> {
    const response = await client.get<{ agents: Agent[] }>('/agents')
    return response.data.agents
  }

  async function getAgent(id: string): Promise<Agent> {
    const response = await client.get<Agent>(`/agents/${id}`)
    return response.data
  }

  async function updateAgent(id: string, data: Partial<Agent>): Promise<Agent> {
    const response = await client.patch<Agent>(`/agents/${id}`, data)
    return response.data
  }

  async function getAvailableAgents(): Promise<Record<string, unknown>[]> {
    const response = await client.get('/agent/agents/available')
    return response.data
  }

  async function getAgentsStatus(): Promise<Record<string, unknown>> {
    const response = await client.get('/agent/agents/status')
    return response.data
  }

  async function pauseAgent(): Promise<Record<string, unknown>> {
    const response = await client.post('/agent/pause')
    return response.data
  }

  async function resumeAgent(): Promise<Record<string, unknown>> {
    const response = await client.post('/agent/resume')
    return response.data
  }

  async function executeAgentGoal(goal: string): Promise<Record<string, unknown>> {
    const response = await client.post('/agent/goal', { goal })
    return response.data
  }

  // =============================================================================
  // RUM (Real User Monitoring) API
  // =============================================================================

  async function getRUMMetrics(options?: {
    start?: string
    end?: string
    interval?: string
  }): Promise<RUMMetrics[]> {
    const params = new URLSearchParams()
    if (options?.start) params.append('start', options.start)
    if (options?.end) params.append('end', options.end)
    if (options?.interval) params.append('interval', options.interval)
    const response = await client.get<{ metrics: RUMMetrics[] }>(`/rum/metrics?${params}`)
    return response.data.metrics
  }

  // =============================================================================
  // Voice API
  // =============================================================================

  async function getVoiceConfig(): Promise<Record<string, unknown>> {
    const response = await client.get('/voice/config')
    return response.data
  }

  async function updateVoiceConfig(config: Record<string, unknown>): Promise<void> {
    await client.put('/voice/config', config)
  }

  async function voiceListen(userRole: string = 'admin'): Promise<Record<string, unknown>> {
    const formData = new FormData()
    formData.append('user_role', userRole)
    const response = await client.post('/voice/listen', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  async function voiceSpeak(text: string, userRole: string = 'admin'): Promise<Record<string, unknown>> {
    const formData = new FormData()
    formData.append('text', text)
    formData.append('user_role', userRole)
    const response = await client.post('/voice/speak', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  // =============================================================================
  // LLM/Inference API
  // =============================================================================

  async function getLLMConfig(): Promise<Record<string, unknown>> {
    const response = await client.get('/llm/config')
    return response.data
  }

  async function updateLLMConfig(config: Record<string, unknown>): Promise<void> {
    await client.put('/llm/config', config)
  }

  async function getLLMModels(): Promise<Array<{ id: string; name: string; provider: string }>> {
    const response = await client.get<{ models: Array<{ id: string; name: string; provider: string }> }>(
      '/llm/models'
    )
    return response.data.models
  }

  // =============================================================================
  // Logs API (for viewing, not forwarding)
  // =============================================================================

  async function getLogs(options?: {
    source?: string
    level?: string
    search?: string
    limit?: number
    offset?: number
  }): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
    const params = new URLSearchParams()
    if (options?.source) params.append('source', options.source)
    if (options?.level) params.append('level', options.level)
    if (options?.search) params.append('search', options.search)
    if (options?.limit) params.append('limit', options.limit.toString())
    if (options?.offset) params.append('offset', options.offset.toString())
    const response = await client.get<{
      logs: Array<{ timestamp: string; level: string; message: string; source: string }>
    }>(`/logs?${params}`)
    return response.data.logs
  }

  // =============================================================================
  // System Monitoring API
  // =============================================================================

  async function getSystemMetrics(): Promise<Record<string, unknown>> {
    const response = await client.get('/monitoring/system')
    return response.data
  }

  async function getHardwareInfo(): Promise<Record<string, unknown>> {
    const response = await client.get('/monitoring/hardware')
    return response.data
  }

  async function getSystemHealth(): Promise<{
    status: 'healthy' | 'degraded' | 'critical'
    cpu_percent?: number
    memory_percent?: number
    disk_percent?: number
    uptime_seconds?: number
    services?: { name: string; status: string }[]
  }> {
    const response = await client.get('/health/detailed')
    const data = response.data
    // Issue #997: Backend returns metrics nested in components as "12.5%" strings.
    // Transform to flat numeric fields expected by AdminMonitoringView.
    const components: Record<string, string> = data.components || {}
    const parsePct = (s: string | undefined): number | undefined => {
      if (!s) return undefined
      const n = parseFloat(s)
      return isNaN(n) ? undefined : n
    }
    return {
      status: data.status,
      cpu_percent: parsePct(components.cpu_usage),
      memory_percent: parsePct(components.memory_usage),
      disk_percent: parsePct(components.disk_usage),
      uptime_seconds: data.uptime_seconds,
      services: data.services,
    }
  }

  async function getErrorStatistics(): Promise<{
    total_errors: number
    last_24h: number
    by_level: { level: string; count: number }[]
    resolved_count: number
  }> {
    const response = await client.get('/errors/statistics')
    return response.data
  }

  async function getRecentErrors(limit: number = 10): Promise<{
    errors: Array<{
      id: string
      level: string
      message: string
      timestamp: string
      resolved: boolean
    }>
  }> {
    const response = await client.get(`/errors/recent?limit=${limit}`)
    return response.data
  }

  async function getMetricsSummary(): Promise<{
    metrics: Array<{
      name: string
      value: string | number
      status: 'good' | 'warning' | 'critical'
      trend?: 'up' | 'down' | 'stable'
    }>
  }> {
    const response = await client.get('/metrics/summary')
    return response.data
  }

  // =============================================================================
  // Browser MCP API (Issue #835 - browser automation via MCP protocol)
  // =============================================================================

  async function getBrowserStatus(): Promise<Record<string, unknown>> {
    const response = await client.get('/browser/mcp/status')
    return response.data
  }

  async function browserNavigate(url: string): Promise<Record<string, unknown>> {
    const response = await client.post('/browser/mcp/navigate', { url })
    return response.data
  }

  async function browserScreenshot(): Promise<Record<string, unknown>> {
    const response = await client.post('/browser/mcp/screenshot', {})
    return response.data
  }

  async function browserClick(selector: string): Promise<Record<string, unknown>> {
    const response = await client.post('/browser/mcp/click', { selector })
    return response.data
  }

  async function browserFill(selector: string, value: string): Promise<Record<string, unknown>> {
    const response = await client.post('/browser/mcp/fill', { selector, value })
    return response.data
  }

  async function browserEvaluate(script: string): Promise<Record<string, unknown>> {
    const response = await client.post('/browser/mcp/evaluate', { script })
    return response.data
  }

  async function browserGoBack(sessionId: string): Promise<Record<string, unknown>> {
    const response = await client.post(`/browser/mcp/navigate`, { url: 'javascript:history.back()' })
    void sessionId
    return response.data
  }

  async function browserGoForward(sessionId: string): Promise<Record<string, unknown>> {
    const response = await client.post(`/browser/mcp/navigate`, { url: 'javascript:history.forward()' })
    void sessionId
    return response.data
  }

  async function browserRefresh(sessionId: string): Promise<Record<string, unknown>> {
    const response = await client.post(`/browser/mcp/navigate`, { url: 'javascript:location.reload()' })
    void sessionId
    return response.data
  }

  // =============================================================================
  // Vision API (Issue #835)
  // =============================================================================

  async function getVisionStatus(): Promise<Record<string, unknown>> {
    const response = await client.get('/vision/status')
    return response.data
  }

  async function getVisionHealth(): Promise<Record<string, unknown>> {
    const response = await client.get('/vision/health')
    return response.data
  }

  async function analyzeScreen(
    data: { image_base64?: string; url?: string }
  ): Promise<Record<string, unknown>> {
    const response = await client.post('/vision/analyze', data)
    return response.data
  }

  async function detectElements(
    data: { image_base64?: string; url?: string }
  ): Promise<Record<string, unknown>> {
    const response = await client.post('/vision/elements', data)
    return response.data
  }

  async function extractTextOCR(
    data: { image_base64?: string; url?: string }
  ): Promise<Record<string, unknown>> {
    const response = await client.post('/vision/ocr', data)
    return response.data
  }

  // =============================================================================
  // Batch Jobs API (Issue #835 - at /batch-jobs prefix)
  // =============================================================================

  async function listBatchJobs(): Promise<Record<string, unknown>> {
    const response = await client.get('/batch-jobs')
    return response.data
  }

  async function createBatchJob(
    data: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const response = await client.post('/batch-jobs', data)
    return response.data
  }

  async function getBatchJob(jobId: string): Promise<Record<string, unknown>> {
    const response = await client.get(`/batch-jobs/${jobId}`)
    return response.data
  }

  async function cancelBatchJob(jobId: string): Promise<Record<string, unknown>> {
    const response = await client.delete(`/batch-jobs/${jobId}`)
    return response.data
  }

  async function getBatchJobHealth(): Promise<Record<string, unknown>> {
    const response = await client.get('/batch-jobs/health')
    return response.data
  }

  async function getBatchStatus(): Promise<Record<string, unknown>> {
    const response = await client.get('/batch/status')
    return response.data
  }

  // =============================================================================
  // Terminal API (Issue #729 - for TerminalTool)
  // =============================================================================

  async function executeTerminalCommand(
    command: string,
    host: string
  ): Promise<{ stdout: string; stderr: string; exit_code: number }> {
    const response = await client.post<{ stdout: string; stderr: string; exit_code: number }>(
      '/terminal/execute',
      { command, host }
    )
    return response.data
  }

  // =============================================================================
  // Log Forwarding Status/Control (Issue #729)
  // =============================================================================

  async function getLogForwardingStatus(): Promise<{
    running: boolean
    total_destinations: number
    enabled_destinations: number
    healthy_destinations: number
    total_sent: number
    total_failed: number
    auto_start: boolean
  }> {
    const response = await client.get('/log-forwarding/status')
    return response.data
  }

  async function startLogForwarding(): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>('/log-forwarding/start')
    return response.data
  }

  async function stopLogForwarding(): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>('/log-forwarding/stop')
    return response.data
  }

  async function setLogForwardingAutoStart(enabled: boolean): Promise<{ status: string }> {
    const response = await client.post<{ status: string }>('/log-forwarding/auto-start', { enabled })
    return response.data
  }

  async function testAllLogForwardingDestinations(): Promise<{ results: Array<{ id: string; success: boolean; message: string }> }> {
    const response = await client.post<{ results: Array<{ id: string; success: boolean; message: string }> }>('/log-forwarding/test-all')
    return response.data
  }

  return {
    // Settings
    getSettings,
    updateSettings,
    getSettingsSection,
    updateSettingsSection,
    // Users
    getUsers,
    createUser,
    updateUser,
    deleteUser,
    // Cache
    getCacheConfig,
    updateCacheConfig,
    getCacheStats,
    clearCache,
    warmupCache,
    // Log Forwarding
    getLogForwardingDestinations,
    createLogForwardingDestination,
    updateLogForwardingDestination,
    deleteLogForwardingDestination,
    testLogForwardingDestination,
    // NPU Workers
    getNPUWorkers,
    getNPUWorker,
    updateNPUWorker,
    restartNPUWorker,
    getNPULoadBalancingConfig,
    updateNPULoadBalancingConfig,
    pairNPUWorker,
    testNPUWorker,
    removeNPUWorker,
    // Permissions
    getPermissionRules,
    createPermissionRule,
    updatePermissionRule,
    deletePermissionRule,
    // Prompts
    getPromptTemplates,
    getPromptTemplate,
    createPromptTemplate,
    updatePromptTemplate,
    deletePromptTemplate,
    revertPromptToDefault,
    // Files
    listFiles,
    readFile,
    writeFile,
    deleteFile,
    uploadFile,
    // MCP Registry (Issue #835)
    getMCPServers,
    getMCPServer,
    startMCPServer,
    stopMCPServer,
    restartMCPServer,
    getMCPBridges,
    getMCPTools,
    getMCPHealth,
    getMCPStats,
    // Agents (Issue #835)
    getAgents,
    getAgent,
    updateAgent,
    getAvailableAgents,
    getAgentsStatus,
    pauseAgent,
    resumeAgent,
    executeAgentGoal,
    // RUM
    getRUMMetrics,
    // Voice (Issue #835)
    getVoiceConfig,
    updateVoiceConfig,
    voiceListen,
    voiceSpeak,
    // LLM
    getLLMConfig,
    updateLLMConfig,
    getLLMModels,
    // Logs
    getLogs,
    // System
    getSystemMetrics,
    getHardwareInfo,
    getSystemHealth,
    getErrorStatistics,
    getRecentErrors,
    getMetricsSummary,
    // Browser MCP (Issue #835)
    getBrowserStatus,
    browserNavigate,
    browserScreenshot,
    browserClick,
    browserFill,
    browserEvaluate,
    browserGoBack,
    browserGoForward,
    browserRefresh,
    // Vision (Issue #835)
    getVisionStatus,
    getVisionHealth,
    analyzeScreen,
    detectElements,
    extractTextOCR,
    // Batch Jobs (Issue #835)
    listBatchJobs,
    createBatchJob,
    getBatchJob,
    cancelBatchJob,
    getBatchJobHealth,
    getBatchStatus,
    // Terminal (Issue #729)
    executeTerminalCommand,
    // Log Forwarding Control (Issue #729)
    getLogForwardingStatus,
    startLogForwarding,
    stopLogForwarding,
    setLogForwardingAutoStart,
    testAllLogForwardingDestinations,
  }
}
