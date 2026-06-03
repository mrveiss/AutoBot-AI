/**
 * Unified Data Models for AutoBot
 *
 * These TypeScript interfaces mirror the Pydantic models from the backend,
 * ensuring type safety and consistency between frontend and backend data structures.
 */

// ============================================================================
// Configuration Models (matching backend/models/settings.py)
// ============================================================================

// Interfaces mirror the shape returned by GET /api/settings/ (section-keyed
// JSON persisted by the backend SettingsManager). Rewritten for #5214 after
// the #5207 audit found the prior declaration (llm/redis/data/diagnostics/
// orchestrator/environment/debug) did not correspond to any backend payload.
export interface MessageDisplaySettings {
  show_thoughts: boolean
  show_json: boolean
  show_utility: boolean
  show_planning: boolean
  show_debug: boolean
}

export interface ChatSettings {
  auto_scroll: boolean
  max_messages: number
  message_retention_days: number
}

// Nested LLM config embedded under `backend.llm` in the settings payload.
// Fields are persisted as free-form JSON; typed loosely to avoid over-fitting.
export interface BackendLLMSettings {
  ollama?: Record<string, unknown>
  unified?: Record<string, unknown>
  [key: string]: unknown
}

export interface BackendSettings {
  api_endpoint: string
  server_host: string
  server_port: number
  chat_data_dir: string
  chat_history_file: string
  knowledge_base_db: string
  reliability_stats_file: string
  audit_log_file: string
  cors_origins: string[]
  timeout: number
  max_retries: number
  streaming: boolean
  llm: BackendLLMSettings
}

export interface UISettings {
  theme: string
  font_size: string
  language: string
  animations: boolean
  developer_mode: boolean
}

export interface SecuritySettings {
  enable_encryption: boolean
  session_timeout_minutes: number
}

export interface LoggingSettings {
  level: string
  log_levels: string[]
  console: boolean
  file: boolean
  max_file_size: number
  log_requests: boolean
  log_sql: boolean
  log_file_path: string
}

export interface KnowledgeBaseSettings {
  enabled: boolean
  update_frequency_days: number
}

export interface VoiceInterfaceSettings {
  enabled: boolean
  voice: string
  speech_rate: number
}

export interface MemorySettings {
  long_term: { enabled: boolean; retention_days: number }
  short_term: { enabled: boolean; duration_minutes: number }
  vector_storage: { enabled: boolean; update_frequency_days: number }
  chromadb: { enabled: boolean; path: string; collection_name: string }
  redis: { enabled: boolean; host: string; port: number }
}

export interface DeveloperSettings {
  enabled: boolean
  enhanced_errors: boolean
  endpoint_suggestions: boolean
  debug_logging: boolean
}

export interface AutoBotSettings {
  message_display: MessageDisplaySettings
  chat: ChatSettings
  backend: BackendSettings
  ui: UISettings
  security: SecuritySettings
  logging: LoggingSettings
  knowledge_base: KnowledgeBaseSettings
  voice_interface: VoiceInterfaceSettings
  memory: MemorySettings
  developer: DeveloperSettings
}

// ============================================================================
// Chat Models
// Issue #2066: ChatMessage is now defined canonically in types/api.ts.
// Re-exported here for backward compatibility.
// ============================================================================

import type { ChatMessage, MessageSender, ChatMessageDisplayType } from '@/types/api'
export type { ChatMessage, MessageSender, ChatMessageDisplayType }

export interface ChatSession {
  id: string
  name: string
  created_at: string
  updated_at: string
  message_count: number
  last_message?: ChatMessage
}

export interface ChatHistory {
  sessions: ChatSession[]
  current_session?: ChatSession
  messages: ChatMessage[]
}

// ============================================================================
// WebSocket Event Models
// ============================================================================

export interface WebSocketEvent {
  type: string
  payload: Record<string, unknown>
  timestamp?: string
}

export interface GoalReceivedEvent extends WebSocketEvent {
  type: 'goal_received'
  payload: {
    goal: string
    session_id?: string
  }
}

export interface PlanReadyEvent extends WebSocketEvent {
  type: 'plan_ready'
  payload: {
    llm_response: string
    plan_steps?: string[]
  }
}

export interface GoalCompletedEvent extends WebSocketEvent {
  type: 'goal_completed'
  payload: {
    results: Record<string, unknown>
    success: boolean
    execution_time?: number
  }
}

export interface CommandExecutionEvent extends WebSocketEvent {
  type: 'command_execution_start' | 'command_execution_end'
  payload: {
    command: string
    status?: 'running' | 'completed' | 'failed'
    output?: string
    error?: string
  }
}

export interface LLMResponseEvent extends WebSocketEvent {
  type: 'llm_response'
  payload: {
    response: string
    model?: string
    tokens_used?: number
  }
}

export interface ErrorEvent extends WebSocketEvent {
  type: 'error'
  payload: {
    message: string
    error_type?: string
    stack_trace?: string
  }
}

// ============================================================================
// Knowledge Base Models
// ============================================================================

export interface KnowledgeFact {
  id: string
  fact: string
  category?: string
  confidence?: number
  source?: string
  created_at: string
  updated_at: string
}

export interface KnowledgeSearchResult {
  facts: KnowledgeFact[]
  total_results: number
  query: string
  search_time: number
}

export interface KnowledgeCategory {
  name: string
  description?: string
  fact_count: number
  last_updated: string
}

// ============================================================================
// System Models
// ============================================================================

/**
 * Deprecated re-export alias for backwards compatibility (#5212).
 *
 * The previous flat shape (`cpu_usage`, `memory_usage`, `disk_usage`,
 * `active_connections`, `last_updated`) described fields the backend never
 * returned. The authoritative shape now lives in
 * `@/models/repositories/SystemRepository` as `SystemMetricsResponse`.
 *
 * @deprecated Import `SystemMetricsResponse` from `@/models/repositories/SystemRepository` instead.
 */
export type { SystemMetricsResponse as SystemMetrics } from '@/models/repositories/SystemRepository'

export interface LLMStatus {
  status: 'connected' | 'disconnected' | 'error'
  model: string
  provider: string
  last_response_time?: number
  error_message?: string
}

export interface DiagnosticsReport {
  system_health: 'healthy' | 'warning' | 'error'
  issues: DiagnosticIssue[]
  recommendations: string[]
  generated_at: string
}

export interface DiagnosticIssue {
  type: 'error' | 'warning' | 'info'
  component: string
  message: string
  suggested_fix?: string
  severity: 'low' | 'medium' | 'high' | 'critical'
}

// ============================================================================
// API Response Models
// ============================================================================

export interface ApiResponse<T = unknown> {
  data: T
  ok: boolean
  status: number
  statusText: string
  headers: Headers
}

export interface RequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: string | FormData
  signal?: AbortSignal
  timeout?: number
  skipCache?: boolean
  params?: Record<string, string | number | boolean>
}

export interface LegacyApiResponse<T = unknown> {
  success: boolean
  data?: T
  message?: string
  error?: string
  timestamp: string
}

export interface PaginatedResponse<T = unknown> {
  items: T[]
  total: number
  page: number
  page_size: number
  has_next: boolean
  has_previous: boolean
}

export interface ValidationError {
  field: string
  message: string
  code?: string
}

export interface ApiError {
  message: string
  code?: string | number
  details?: string
  validation_errors?: ValidationError[]
}

// ============================================================================
// File Management Models
// ============================================================================

export interface FileInfo {
  name: string
  path: string
  is_directory: boolean
  size?: number | null
  mime_type?: string | null
  last_modified: string
  permissions: string
  extension?: string | null
}

export interface DirectoryListing {
  current_path: string
  parent_path?: string | null
  files: FileInfo[]
  total_files: number
  total_directories: number
  total_size: number
}

export interface FileUploadResponse {
  success: boolean
  message: string
  file_info?: FileInfo | null
  upload_id?: string | null
}

export interface FileOperation {
  path: string
}

export interface FileViewResponse {
  file_info: FileInfo
  content?: string | null
  is_text: boolean
}

export interface FileStats {
  sandbox_root: string
  total_files: number
  total_directories: number
  total_size: number
  total_size_mb: number
  max_file_size_mb: number
  allowed_extensions: string[]
}

export interface DirectoryCreateResponse {
  message: string
  directory_info: FileInfo
}

// Legacy models for backward compatibility
export interface UploadedFile {
  id: string
  filename: string
  original_name: string
  size: number
  mime_type: string
  upload_date: string
  path: string
}

export interface FileListResponse {
  files: UploadedFile[]
  total_size: number
  total_files: number
}

// ============================================================================
// Voice Interface Models
// ============================================================================

export interface VoiceSettings {
  enabled: boolean
  language: string
  voice_id?: string
  speech_rate: number
  pitch: number
  volume: number
}

export interface VoiceStatus {
  is_listening: boolean
  is_speaking: boolean
  last_recognized_text?: string
  confidence_level?: number
}

// ============================================================================
// Agent Models
// ============================================================================

export interface AgentTask {
  id: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'abstained'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  created_at: string
  started_at?: string
  completed_at?: string
  estimated_duration?: number
  actual_duration?: number
  result?: Record<string, unknown>
  error_message?: string
  // GH#6626: Confidence-based abstention fields
  abstained?: boolean
  abstention_reason?: string
}

export interface AgentCapabilities {
  can_execute_commands: boolean
  can_access_files: boolean
  can_browse_web: boolean
  can_use_gui: boolean
  available_tools: string[]
  supported_languages: string[]
}

export interface AgentStatus {
  is_active: boolean
  current_task?: AgentTask
  pending_tasks: number
  completed_tasks_today: number
  last_activity: string
  capabilities: AgentCapabilities
}

// ============================================================================
// Workflow Models
// ============================================================================

export interface WorkflowStep {
  id: string
  name: string
  description?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'requires_approval'
  type?: string
  data?: Record<string, unknown>
  approval_status?: 'pending' | 'approved' | 'rejected'
}

export interface Workflow {
  id: string
  name: string
  description?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  steps: WorkflowStep[]
  created_at: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

export interface WorkflowResponse {
  workflow: Workflow
  message?: string
  success?: boolean
}

// ============================================================================
// Utility Types
// ============================================================================

// MessageSender re-exported from '@/types/api' above (Issue #2066)
export type TaskStatus = AgentTask['status']
export type TaskPriority = AgentTask['priority']
export type LogLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical'
export type TransportType = 'local' | 'redis'
export type SystemHealth = DiagnosticsReport['system_health']
export type IssueSeverity = DiagnosticIssue['severity']

// Centralized common types
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'

// ============================================================================
// Type Guards and Validators
// ============================================================================

function isRecord(obj: unknown): obj is Record<string, unknown> {
  return typeof obj === 'object' && obj !== null
}

export function isChatMessage(obj: unknown): obj is import('@/types/api').ChatMessage {
  if (!isRecord(obj)) return false
  return typeof obj.id === 'string' &&
    typeof obj.sender === 'string' &&
    typeof obj.content === 'string' &&
    (typeof obj.timestamp === 'string' || obj.timestamp instanceof Date)
}

export function isWebSocketEvent(obj: unknown): obj is WebSocketEvent {
  if (!isRecord(obj)) return false
  return typeof obj.type === 'string' &&
    typeof obj.payload === 'object' &&
    obj.payload !== null
}

export function isApiResponse<T>(obj: unknown): obj is ApiResponse<T> {
  if (!isRecord(obj)) return false
  return typeof obj.success === 'boolean' &&
    typeof obj.timestamp === 'string'
}

export function isApiError(obj: unknown): obj is ApiError {
  if (!isRecord(obj)) return false
  return typeof obj.message === 'string'
}

// ============================================================================
// Default Values and Constants
// ============================================================================

export const DEFAULT_CHAT_MESSAGE: Partial<import('@/types/api').ChatMessage> = {
  sender: 'user',
  message_type: 'text',
  metadata: {}
}

export const DEFAULT_AGENT_TASK: Partial<AgentTask> = {
  status: 'pending',
  priority: 'medium'
}

export const SYSTEM_MESSAGE_TYPES = [
  'goal_received',
  'plan_ready',
  'goal_completed',
  'command_execution_start',
  'command_execution_end',
  'error',
  'progress',
  'llm_response',
  'settings_updated',
  'file_uploaded',
  'knowledge_base_update',
  'llm_status',
  'diagnostics_report'
] as const

export type SystemMessageType = typeof SYSTEM_MESSAGE_TYPES[number]
