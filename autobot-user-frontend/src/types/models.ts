/**
 * Unified Data Models for AutoBot
 *
 * These TypeScript interfaces mirror the Pydantic models from the backend,
 * ensuring type safety and consistency between frontend and backend data structures.
 */

// ============================================================================
// Configuration Models (matching backend/models/settings.py)
// ============================================================================

export interface LLMSettings {
  default_llm: string
  orchestrator_llm: string
  task_llm: string
  ollama_host: string
  ollama_port: number
  ollama_model: string
  ollama_base_url: string
  openai_api_key?: string | null
  openai_model: string
  huggingface_api_key?: string | null
  huggingface_model: string
}

export interface RedisSettings {
  enabled: boolean
  host: string
  port: number
  db: number
  password?: string | null
}

export interface DataSettings {
  base_directory: string
  chat_history_file: string
  chats_directory: string
  long_term_db_path: string
  reliability_stats_file: string
  knowledge_base_db: string
  chromadb_path: string
}

export interface BackendSettings {
  server_host: string
  server_port: number
  api_endpoint: string
  cors_origins: string[]
  reload: boolean
  log_level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
}

export interface SecuritySettings {
  enable_auth: boolean
  audit_log_file: string
  allowed_users: Record<string, string>
  roles: Record<string, Record<string, any>>
}

export interface DiagnosticsSettings {
  enabled: boolean
  use_llm_for_analysis: boolean
  use_web_search_for_analysis: boolean
  auto_apply_fixes: boolean
}

export interface MemorySettings {
  retention_days: number
  max_entries_per_category: number
}

export interface OrchestratorSettings {
  use_langchain: boolean
  task_transport: 'local' | 'redis'
  max_concurrent_tasks: number
}

export interface AutoBotSettings {
  llm: LLMSettings
  redis: RedisSettings
  data: DataSettings
  backend: BackendSettings
  security: SecuritySettings
  diagnostics: DiagnosticsSettings
  memory: MemorySettings
  orchestrator: OrchestratorSettings
  environment: string
  debug: boolean
}

// ============================================================================
// Chat Models
// ============================================================================

export interface ChatMessage {
  id: string
  sender: 'user' | 'bot' | 'system' | 'error' | 'thought' | 'tool-code' | 'tool-output'
  text: string
  timestamp: string
  message_type?: string
  metadata?: Record<string, any>
  session_id?: string
}

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
  payload: Record<string, any>
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
    results: Record<string, any>
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

export interface SystemMetrics {
  cpu_usage: number
  memory_usage: number
  disk_usage: number
  uptime: number
  active_connections: number
  last_updated: string
}

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

export interface ApiResponse<T = any> {
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
  params?: Record<string, any>
}

export interface LegacyApiResponse<T = any> {
  success: boolean
  data?: T
  message?: string
  error?: string
  timestamp: string
}

export interface PaginatedResponse<T = any> {
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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'urgent'
  created_at: string
  started_at?: string
  completed_at?: string
  estimated_duration?: number
  actual_duration?: number
  result?: Record<string, any>
  error_message?: string
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
  data?: Record<string, any>
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
  metadata?: Record<string, any>
}

export interface WorkflowResponse {
  workflow: Workflow
  message?: string
  success?: boolean
}

// ============================================================================
// Utility Types
// ============================================================================

export type MessageSender = ChatMessage['sender']
export type TaskStatus = AgentTask['status']
export type TaskPriority = AgentTask['priority']
export type LogLevel = BackendSettings['log_level']
export type TransportType = OrchestratorSettings['task_transport']
export type SystemHealth = DiagnosticsReport['system_health']
export type IssueSeverity = DiagnosticIssue['severity']

// Centralized common types
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Priority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'

// ============================================================================
// Type Guards and Validators
// ============================================================================

export function isChatMessage(obj: any): obj is ChatMessage {
  return obj &&
    typeof obj.id === 'string' &&
    typeof obj.sender === 'string' &&
    typeof obj.text === 'string' &&
    typeof obj.timestamp === 'string'
}

export function isWebSocketEvent(obj: any): obj is WebSocketEvent {
  return obj &&
    typeof obj.type === 'string' &&
    obj.payload &&
    typeof obj.payload === 'object'
}

export function isApiResponse<T>(obj: any): obj is ApiResponse<T> {
  return obj &&
    typeof obj.success === 'boolean' &&
    typeof obj.timestamp === 'string'
}

export function isApiError(obj: any): obj is ApiError {
  return obj &&
    typeof obj.message === 'string'
}

// ============================================================================
// Default Values and Constants
// ============================================================================

export const DEFAULT_CHAT_MESSAGE: Partial<ChatMessage> = {
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
