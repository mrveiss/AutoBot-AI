// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * AutoBot Backend API Composable
 *
 * Provides REST API integration for the main AutoBot backend (the main backend server).
 * Used for settings, tools, and monitoring functionality that requires the main backend.
 * Issue #729 - Migrating admin functionality to SLM.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

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

// GH#8996: admin cross-user view of all active shared chat links
export interface SharedLinkAdminItem {
  id: string
  token: string
  session_id: string
  owner: string
  has_password: boolean
  expires_at: string | null
  created_at: string
}

// Envelope from create_success_response: { success, data: { links, count }, message, timestamp }
export interface SharedLinksAdminResponse {
  success: boolean
  data: { links: SharedLinkAdminItem[]; count: number }
  message: string
}

export interface RUMMetrics {
  page_views: number
  unique_users: number
  avg_load_time_ms: number
  error_count: number
  timestamp: string
}

export interface VoiceSpeakResponse {
  response?: string
  text?: string
  status?: string
  error?: string
}

// GH#8998 / #10488: LLM fallback monitoring (moved from main frontend to SLM admin)
export interface LLMFallbackChain {
  primary_model: string
  fallback_chain: string
  provider: string
}

export interface LLMActiveFallback {
  conversation_id: string
  primary_model: string
  fallback_model: string
  primary_provider: string
  fallback_provider: string
  timestamp: number
}

export interface LLMFallbackStatus {
  configured_chains: LLMFallbackChain[]
  active_fallbacks: LLMActiveFallback[]
}

// Budget audit (#10488 Workstream A): read-only operator oversight of
// agent/project/task/tenant budget policies + hard-stop auto-pause config.
// Mirrors the backend BudgetPolicyResponse model (api/budget_policies.py).
export interface BudgetPolicy {
  id: string
  scope: string
  scope_id: string
  period: string
  threshold_usd: number
  warning_pct: number
  action: string
  enabled: boolean
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface BudgetPoliciesList {
  policies: BudgetPolicy[]
  count: number
}

// =============================================================================
// Advanced Control (#12653) — desktop streaming + human takeover.
//
// The endpoint paths and payload shapes below used to be re-declared inline in
// AdvancedControlTool.vue, which also re-implemented this composable's
// transport with a raw `fetch` (no autobot_access_token fallback, no 401
// handling, no timeout). Declaring them here keeps the SLM app's knowledge of
// the autobot backend in exactly one place, next to every other tool.
// =============================================================================

export interface AdvancedControlCapabilities {
  vnc_available?: boolean
  novnc_available?: boolean
  max_sessions?: number
  supported_resolutions?: string[]
  supported_depths?: number[]
  [k: string]: unknown
}

export interface AdvancedControlStreamingSession {
  session_id: string
  user_id?: string
  display?: string
  vnc_port?: number
  status?: string
  created_at?: string
  [k: string]: unknown
}

export interface AdvancedControlPendingRequest {
  request_id: string
  trigger?: string
  reason?: string
  priority?: string
  created_at?: string
  [k: string]: unknown
}

export interface AdvancedControlActiveSession {
  session_id: string
  human_operator?: string
  status?: string
  [k: string]: unknown
}

export type AdvancedControlTakeoverStatus = Record<string, unknown>

/** Triggers accepted by POST /advanced-control/takeover/request. */
export const ADVANCED_CONTROL_TRIGGERS = [
  'MANUAL_REQUEST',
  'CRITICAL_ERROR',
  'SECURITY_CONCERN',
  'USER_INTERVENTION_REQUIRED',
  'SYSTEM_OVERLOAD',
  'APPROVAL_REQUIRED',
  'TIMEOUT_EXCEEDED',
] as const

/** Priorities accepted by POST /advanced-control/takeover/request. */
export const ADVANCED_CONTROL_PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const

export interface AdvancedControlSessionRequest {
  user_id: string
  resolution?: string
  depth?: number
}

export interface AdvancedControlTakeoverRequest {
  trigger: string
  reason: string
  priority?: string
  requesting_agent?: string | null
}

/** Lifecycle transitions on an approved takeover session. */
export type AdvancedControlSessionAction = 'pause' | 'resume' | 'complete'

// =============================================================================
// Agent org chart / processes / config revisions / Redis service / RBAC (#13079)
//
// The endpoint paths and payload shapes below used to be re-declared inline in
// OrgChartTab.vue, ProcessMonitorTab.vue, ConfigHistoryTab.vue,
// RedisServicePanel.vue, UserManagementSettings.vue, CacheSettings.vue and
// BackendSettings.vue. Each of those files also re-implemented this
// composable's transport with a raw `fetch` that sent only
// `Bearer ${authStore.token}` — no `autobot_access_token` fallback, no 401
// cleanup, no timeout, no shared base-URL resolution. Declaring them here keeps
// the SLM app's knowledge of the autobot backend in exactly one place
// (ADR-008 decision rule 3), as `AdvancedControlTool.vue` already does.
// =============================================================================

/** Node of the agent hierarchy returned by GET /agents/org (#1405). */
export interface AgentOrgNode {
  agent_id: string
  name: string
  org_role: string
  title: string | null
  capabilities: string | null
  direct_reports_count: number
  children: AgentOrgNode[]
}

/** Entry of GET /agents/{id}/reports (#1405). */
export interface AgentDirectReport {
  agent_id: string
  name: string
  org_role: string
}

/** Entry of GET /agents/{id}/delegations (#1405). */
export interface AgentDelegation {
  id: string
  delegator_id: string
  assignee_id: string
  task_description: string
  status: string
  escalated_to: string | null
  created_at: string | null
}

/** GET /agents/{id}/activity (#1405). */
export interface AgentActivitySummary {
  manager_id: string
  total_delegated: number
  by_status: Record<string, number>
}

/** Body of POST /agents/{id}/delegate (#1405). */
export interface AgentDelegationRequest {
  assignee_id: string
  task_description: string
}

/** Row of GET /agents/{id}/processes (#1406). */
export interface ProcessRun {
  id: string
  agent_id: string
  task_id: string | null
  command: string
  args: string[]
  status: string
  exit_code: number | null
  signal: string | null
  log_excerpt: string | null
  log_path: string | null
  timeout_seconds: number
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

/** Body of POST /processes/spawn (#1406). */
export interface ProcessSpawnRequest {
  agent_id: string
  command: string
  args: string[]
  timeout_seconds: number
}

/** Entry of GET /config-revisions/{entityType}/{entityId} (#1404). */
export interface ConfigRevision {
  id: string
  entity_type: string
  entity_id: string
  before_config: Record<string, unknown> | null
  after_config: Record<string, unknown>
  changed_keys: string[]
  source: string
  created_by: string
  created_at: string | null
}

/** GET /redis-service/status (#3381). */
export interface RedisServiceStatus {
  status: 'running' | 'stopped' | 'unknown'
  uptime_seconds: number | null
  memory_used_bytes: number | null
  memory_peak_bytes: number | null
  connected_clients: number | null
  last_checked: string | null
  error?: string
}

/** Lifecycle verbs accepted by POST /redis-service/{action} (#3381). */
export type RedisServiceAction = 'start' | 'stop' | 'restart'

/** GET /settings/rbac/status. */
export interface RbacStatus {
  initialized: boolean
  message: string
}

/** Body of POST /settings/rbac/initialize. */
export interface RbacInitializeRequest {
  create_admin: boolean
  admin_username: string
}

/** Outcome of the GET /health reachability probe behind "Test connection". */
export interface BackendHealthProbe {
  ok: boolean
  status: number
}

/**
 * Unwrap the FastAPI `{ "detail": "..." }` error body (#13079).
 *
 * The raw-`fetch` call sites this client replaced read `detail` off the parsed
 * body and showed it to the operator. Axios rejects with a generic
 * "Request failed with status code 500" message instead, so the detail has to
 * be pulled off `error.response.data` explicitly to keep the same error shape.
 */
export function autobotApiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail.length > 0) return detail
  if (err instanceof Error && err.message.length > 0) return err.message
  return fallback
}

export function useAutobotApi() {
  const authStore = useAuthStore()

  const client: AxiosInstance = axios.create({
    baseURL: getBackendUrl(),
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
    // Backend GET /api/prompts returns { prompts: [...], defaults: {...} }
    // where each prompt has { id, name, type, path, content } (Issue #11555)
    const response = await client.get<{
      prompts: Array<{ id: string; name: string; type: string; path: string; content: string }>
      defaults: Record<string, string>
    }>('/prompts')
    const defaults = response.data.defaults ?? {}
    return (response.data.prompts ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      content: p.content,
      category: p.type,
      is_default: Object.prototype.hasOwnProperty.call(defaults, p.id),
      modified_at: '',
    }))
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
    // Backend exposes PUT /api/prompts/:id (also POST) — PATCH is not supported (Issue #11555)
    const response = await client.put<PromptTemplate>(`/prompts/${id}`, data)
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

  async function voiceSpeak(text: string, userRole: string = 'admin'): Promise<VoiceSpeakResponse> {
    const formData = new FormData()
    formData.append('text', text)
    formData.append('user_role', userRole)
    const response = await client.post<VoiceSpeakResponse>('/voice/speak', formData, {
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

  /**
   * Get LLM fallback monitoring status (GH#8998 / #10488).
   * Backend returns a flat payload (no create_success_response envelope):
   * { configured_chains: [...], active_fallbacks: [...] }.
   * The /autobot-api proxy strips its prefix -> backend /api/llm-providers/fallback-status.
   */
  async function getLLMFallbackStatus(): Promise<LLMFallbackStatus> {
    const response = await client.get<LLMFallbackStatus>('/llm-providers/fallback-status')
    return {
      configured_chains: response.data.configured_chains || [],
      active_fallbacks: response.data.active_fallbacks || [],
    }
  }

  /**
   * Budget audit (#10488 Workstream A): read-only list of all budget policies
   * across the system for operator oversight. The user app keeps create/edit/
   * delete; the SLM console is audit-only and issues no mutation calls.
   *
   * Backend returns a flat payload (response_model=BudgetPoliciesListResponse,
   * NOT the create_success_response envelope): { policies: [...], count: N }.
   * The /autobot-api proxy strips its prefix -> backend /api/budget-policies.
   */
  async function getBudgetPolicies(): Promise<BudgetPoliciesList> {
    const response = await client.get<BudgetPoliciesList>('/budget-policies')
    return {
      policies: response.data.policies || [],
      count: response.data.count ?? 0,
    }
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
    const response = await client.get('/system/health/detailed')
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
    // #10379: no backend /metrics/summary exists; derive CPU/Memory/Disk metric
    // cards from the detailed system-health endpoint (same data, correct path).
    const response = await client.get('/system/health/detailed')
    const components: Record<string, string> = response.data?.components || {}
    const pct = (s?: string): number => {
      const n = parseFloat(s ?? '')
      return isNaN(n) ? 0 : n
    }
    const card = (name: string, v: number) => ({
      name,
      value: `${v}%`,
      status: (v > 90 ? 'critical' : v > 75 ? 'warning' : 'good') as 'good' | 'warning' | 'critical',
    })
    return {
      metrics: [
        card('CPU', pct(components.cpu_usage)),
        card('Memory', pct(components.memory_usage)),
        card('Disk', pct(components.disk_usage)),
      ],
    }
  }

  // =============================================================================
  // Shared Chat Links (GH#8996 - admin cross-user view)
  // =============================================================================

  async function getSharedLinksAdmin(): Promise<SharedLinksAdminResponse> {
    const response = await client.get<SharedLinksAdminResponse>('/chat/shared-links/admin')
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
    // #10429: backend exposes /batch-jobs/status (returns status: "healthy"),
    // never /batch-jobs/health (404). Repointed to the real route.
    const response = await client.get('/batch-jobs/status')
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

  // =============================================================================
  // Advanced Control API (#12653 - desktop streaming + human takeover)
  // =============================================================================

  const AC = '/advanced-control'

  async function getAdvancedControlCapabilities(): Promise<AdvancedControlCapabilities> {
    const response = await client.get<AdvancedControlCapabilities>(`${AC}/streaming/capabilities`)
    return response.data
  }

  async function listAdvancedControlSessions(): Promise<AdvancedControlStreamingSession[]> {
    const response = await client.get<{ sessions: AdvancedControlStreamingSession[]; count: number }>(
      `${AC}/streaming/sessions`
    )
    return response.data.sessions ?? []
  }

  async function createAdvancedControlSession(
    request: AdvancedControlSessionRequest
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`${AC}/streaming/create`, request)
    return response.data
  }

  async function terminateAdvancedControlSession(sessionId: string): Promise<Record<string, unknown>> {
    const response = await client.delete(`${AC}/streaming/${encodeURIComponent(sessionId)}`)
    return response.data
  }

  async function getAdvancedControlTakeoverStatus(): Promise<AdvancedControlTakeoverStatus> {
    const response = await client.get<AdvancedControlTakeoverStatus>(`${AC}/takeover/status`)
    return response.data
  }

  async function getPendingTakeovers(): Promise<AdvancedControlPendingRequest[]> {
    const response = await client.get<{ pending_requests: AdvancedControlPendingRequest[]; count: number }>(
      `${AC}/takeover/pending`
    )
    return response.data.pending_requests ?? []
  }

  async function getActiveTakeovers(): Promise<AdvancedControlActiveSession[]> {
    const response = await client.get<{ active_sessions: AdvancedControlActiveSession[]; count: number }>(
      `${AC}/takeover/active`
    )
    return response.data.active_sessions ?? []
  }

  async function requestTakeover(
    request: AdvancedControlTakeoverRequest
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`${AC}/takeover/request`, request)
    return response.data
  }

  async function approveTakeover(
    requestId: string,
    humanOperator: string
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`${AC}/takeover/${encodeURIComponent(requestId)}/approve`, {
      human_operator: humanOperator,
    })
    return response.data
  }

  async function takeoverSessionAction(
    sessionId: string,
    action: AdvancedControlSessionAction,
    body?: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const response = await client.post(
      `${AC}/takeover/sessions/${encodeURIComponent(sessionId)}/${action}`,
      body
    )
    return response.data
  }

  // =============================================================================
  // Agent Org Chart (#1405 / #13079)
  // =============================================================================

  async function getAgentOrgTree(): Promise<AgentOrgNode[]> {
    const response = await client.get<AgentOrgNode[]>('/agents/org')
    return response.data ?? []
  }

  async function getAgentDirectReports(agentId: string): Promise<AgentDirectReport[]> {
    const response = await client.get<AgentDirectReport[]>(
      `/agents/${encodeURIComponent(agentId)}/reports`
    )
    return response.data ?? []
  }

  async function getAgentActivity(agentId: string): Promise<AgentActivitySummary> {
    const response = await client.get<AgentActivitySummary>(
      `/agents/${encodeURIComponent(agentId)}/activity`
    )
    return response.data
  }

  async function getAgentDelegations(
    agentId: string,
    options?: { role?: string; limit?: number }
  ): Promise<AgentDelegation[]> {
    const params = new URLSearchParams()
    if (options?.role) params.append('role', options.role)
    if (options?.limit !== undefined) params.append('limit', String(options.limit))
    const query = params.toString()
    const response = await client.get<AgentDelegation[]>(
      `/agents/${encodeURIComponent(agentId)}/delegations${query ? `?${query}` : ''}`
    )
    return response.data ?? []
  }

  async function delegateAgentTask(
    agentId: string,
    request: AgentDelegationRequest
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`/agents/${encodeURIComponent(agentId)}/delegate`, request)
    return response.data
  }

  // =============================================================================
  // Agent Processes (#1406 / #13079)
  // =============================================================================

  async function getAgentProcesses(
    agentId: string,
    options?: { limit?: number; status?: string }
  ): Promise<ProcessRun[]> {
    const params = new URLSearchParams()
    params.append('limit', String(options?.limit ?? 50))
    if (options?.status) params.append('status', options.status)
    const response = await client.get<{ processes: ProcessRun[] }>(
      `/agents/${encodeURIComponent(agentId)}/processes?${params}`
    )
    return response.data?.processes ?? []
  }

  /**
   * Process logs are served as plain text, not JSON. `responseType: 'text'`
   * disables axios' default JSON parsing so the body arrives verbatim — the
   * raw `fetch` this replaced used `response.text()` for the same reason.
   */
  async function getProcessLogs(processId: string): Promise<string> {
    const response = await client.get<string>(
      `/processes/${encodeURIComponent(processId)}/logs`,
      { responseType: 'text' }
    )
    return response.data
  }

  async function signalProcess(
    processId: string,
    signal: string
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`/processes/${encodeURIComponent(processId)}/signal`, {
      signal,
    })
    return response.data
  }

  async function spawnProcess(request: ProcessSpawnRequest): Promise<Record<string, unknown>> {
    const response = await client.post('/processes/spawn', request)
    return response.data
  }

  // =============================================================================
  // Config Revisions (#1404 / #13079)
  // =============================================================================

  async function getConfigRevisions(
    entityType: string,
    entityId: string,
    limit: number = 50
  ): Promise<ConfigRevision[]> {
    const response = await client.get<ConfigRevision[]>(
      `/config-revisions/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}?limit=${limit}`
    )
    return response.data ?? []
  }

  async function rollbackConfigRevision(
    entityType: string,
    entityId: string,
    revisionId: string
  ): Promise<Record<string, unknown>> {
    const response = await client.post(
      `/config-revisions/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${encodeURIComponent(revisionId)}/rollback`
    )
    return response.data
  }

  // =============================================================================
  // Redis Service control (#3381 / #13079)
  // =============================================================================

  async function getRedisServiceStatus(): Promise<RedisServiceStatus> {
    const response = await client.get<RedisServiceStatus>('/redis-service/status')
    return response.data
  }

  async function performRedisServiceAction(
    action: RedisServiceAction
  ): Promise<Record<string, unknown>> {
    const response = await client.post(`/redis-service/${action}`)
    return response.data
  }

  // =============================================================================
  // RBAC bootstrap + Redis cache admin (#13079)
  // =============================================================================

  async function getRbacStatus(): Promise<RbacStatus> {
    const response = await client.get<RbacStatus>('/settings/rbac/status')
    return response.data
  }

  async function initializeRbac(request: RbacInitializeRequest): Promise<{ message?: string }> {
    const response = await client.post<{ message?: string }>('/settings/rbac/initialize', request)
    return response.data
  }

  async function clearRedisDatabase(database: string): Promise<Record<string, unknown>> {
    const response = await client.post(`/cache/redis/clear/${encodeURIComponent(database)}`)
    return response.data
  }

  /**
   * Reachability probe behind the "Test connection" control (#13079).
   *
   * `validateStatus` accepts every status code so the probe reports
   * "reachable but rejected" rather than throwing, and — critically — never
   * trips the response interceptor that clears `autobot_access_token`: a
   * connectivity diagnostic must not be able to log the operator out.
   */
  async function probeBackendHealth(): Promise<BackendHealthProbe> {
    const response = await client.get('/health', { validateStatus: () => true })
    return { ok: response.status >= 200 && response.status < 300, status: response.status }
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
    // Shared Chat Links (GH#8996)
    getSharedLinksAdmin,
    // Voice (Issue #835)
    getVoiceConfig,
    updateVoiceConfig,
    voiceListen,
    voiceSpeak,
    // LLM
    getLLMConfig,
    updateLLMConfig,
    getLLMModels,
    getLLMFallbackStatus,
    // Budget audit (#10488)
    getBudgetPolicies,
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
    // Advanced Control (#12653)
    getAdvancedControlCapabilities,
    listAdvancedControlSessions,
    createAdvancedControlSession,
    terminateAdvancedControlSession,
    getAdvancedControlTakeoverStatus,
    getPendingTakeovers,
    getActiveTakeovers,
    requestTakeover,
    approveTakeover,
    takeoverSessionAction,
    // Agent Org Chart (#1405 / #13079)
    getAgentOrgTree,
    getAgentDirectReports,
    getAgentActivity,
    getAgentDelegations,
    delegateAgentTask,
    // Agent Processes (#1406 / #13079)
    getAgentProcesses,
    getProcessLogs,
    signalProcess,
    spawnProcess,
    // Config Revisions (#1404 / #13079)
    getConfigRevisions,
    rollbackConfigRevision,
    // Redis Service control (#3381 / #13079)
    getRedisServiceStatus,
    performRedisServiceAction,
    // RBAC bootstrap + Redis cache admin + health probe (#13079)
    getRbacStatus,
    initializeRbac,
    clearRedisDatabase,
    probeBackendHealth,
    // Log Forwarding Control (Issue #729)
    getLogForwardingStatus,
    startLogForwarding,
    stopLogForwarding,
    setLogForwardingAutoStart,
    testAllLogForwardingDestinations,
  }
}
