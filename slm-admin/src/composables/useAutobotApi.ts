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
    return response.data
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
    // MCP
    getMCPServers,
    getMCPServer,
    startMCPServer,
    stopMCPServer,
    restartMCPServer,
    // Agents
    getAgents,
    getAgent,
    updateAgent,
    // RUM
    getRUMMetrics,
    // Voice
    getVoiceConfig,
    updateVoiceConfig,
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
  }
}
