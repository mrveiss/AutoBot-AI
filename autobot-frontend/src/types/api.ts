// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// API Types - TypeScript definitions for backend API integration
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
  status?: string;
}

// Chat API Types
//
// Canonical ChatMessage type — single source of truth for all chat messages.
// Matches backend ChatMessageRequest (content, role, message_type, session_id)
// while preserving frontend-specific fields (sender, type, status, attachments).
// Issue #2066: Unified from four divergent definitions.

/** All valid sender/speaker values across frontend rendering contexts. */
export type MessageSender =
  | 'user'
  | 'assistant'
  | 'bot'        // Legacy alias for 'assistant' in some WebSocket paths
  | 'system'
  | 'error'
  | 'thought'
  | 'tool-code'
  | 'tool-output';

/** Display-layer message type used for filtering in the chat UI. */
export type ChatMessageDisplayType =
  | 'thought'
  | 'planning'
  | 'debug'
  | 'utility'
  | 'sources'
  | 'json'
  | 'response'
  | 'message'
  | 'command_approval_request'
  | 'overseer_plan'
  | 'overseer_step'
  | 'terminal_output'
  | 'terminal_command';

/** A single RAG retrieval source attached to an assistant message (Issue #4448). */
export interface RagSource {
  /** Human-readable title or file name of the source document. */
  title: string;
  /** Relative file path of the source document. */
  path: string;
  /** Retrieval relevance score (0–1). */
  score: number;
  /** Knowledge-base chunk identifier. */
  chunk_id: string;
}

/** Thinking mode metadata for Claude 3.7+ reasoning models (MVA-3090). */
export interface ThinkingMetadata {
  /** Whether thinking mode was used for this response. */
  used: boolean;
  /** Number of thinking tokens consumed (null if thinking not used). */
  tokens_used: number | null;
}

export interface ChatMessage {
  id: string;
  /** Message text content — canonical field name, matches backend `content`. */
  content: string;
  /** Speaker identity for frontend rendering. Backend equivalent: `role`. */
  sender: MessageSender;
  timestamp: string | Date;
  /** Backend message type identifier (snake_case, e.g. 'llm_response'). */
  message_type?: string;
  /** Frontend display type for UI filtering (thought, planning, debug, etc.). */
  type?: ChatMessageDisplayType | string;
  /** Session this message belongs to (matches backend `session_id`). */
  session_id?: string;
  /** Delivery status — frontend-only, not persisted to backend. */
  status?: 'sending' | 'sent' | 'error';
  /** Error detail when status is 'error' — frontend-only. */
  error?: string;
  attachments?: FileAttachment[];
  metadata?: {
    model?: string;
    tokens?: number;
    duration?: number;
    [key: string]: string | number | boolean | undefined;
  };
  /**
   * RAG retrieval sources persisted alongside the message (Issue #4448).
   * Present on assistant messages when the knowledge base was queried.
   * Empty array when RAG was not used or message has no citations.
   */
  sources?: RagSource[];
  /**
   * Thinking mode metadata for Claude 3.7+ reasoning models (MVA-3090).
   * Present on assistant messages when extended thinking was used.
   */
  thinking_metadata?: ThinkingMetadata;
}

/** A user-defined slash command preset (GH#4449). */
export interface SlashCommandPreset {
  /** Unique identifier (UUID). */
  id: string;
  /** Slash command trigger, e.g. "summarize" (no leading slash). */
  name: string;
  /** Short description shown in the autocomplete dropdown. */
  description: string;
  /** Full prompt text inserted into the chat input when the command is triggered. */
  content: string;
  /** ISO timestamp of creation. */
  createdAt: string;
  /** ISO timestamp of last update. */
  updatedAt: string;
}

export interface SlashCommandPresetCreate {
  name: string;
  description: string;
  content: string;
}

export interface SlashCommandPresetUpdate {
  name?: string;
  description?: string;
  content?: string;
}

export interface ChatSession {
  id: string;
  chatId: string;
  name?: string;
  title?: string;
  messages: ChatMessage[];
  lastMessage?: string;
  timestamp: Date | string;
  createdAt?: Date | string;
  updatedAt?: Date | string;
}

export interface FileAttachment {
  id: string;
  name: string;
  type: string;
  size: number;
  url: string;
}

// File Upload Response
export interface FileUploadResponse {
  path: string;
  filename: string;
  size: number;
  success: boolean;
  message?: string;
}

// WebSocket Types
export interface WebSocketMessage {
  type: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

export interface LLMResponse {
  response: string;
  sender?: string;
  content?: string;
  message_type?: string;
  sources?: Record<string, unknown>[];
}

// System Health Types

/**
 * All status values that the backend health endpoint may return.
 * Backend sends: 'healthy', 'unhealthy', 'degraded'.
 * Frontend display layer uses: 'healthy', 'warning', 'error'.
 * Legacy values kept for backward compatibility: 'online', 'offline'.
 */
export type ServiceHealthStatusValue =
  | 'healthy'
  | 'unhealthy'
  | 'degraded'
  | 'warning'
  | 'error'
  | 'online'
  | 'offline';

export interface ServiceStatus {
  name: string;
  version?: string;
  status: ServiceHealthStatusValue;
  statusText?: string;
  responseTime?: number;
  lastCheck?: number | string;
  consecutiveFailures?: number;
  error?: string;
  timestamp?: number | string;
  details?: Record<string, unknown>;
}

export interface SystemAlert {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  visible: boolean;
  statusDetails?: ServiceStatus;
  timestamp: number;
  type?: string;
}

// Workflow Types
export interface WorkflowApproval {
  workflowId: string;
  stepId: string;
  approved: boolean;
  comment?: string;
}

export interface WorkflowStep {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  steps: WorkflowStep[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  createdAt: Date;
  updatedAt: Date;
}

// Browser/Research Types
export interface BrowserTestResult {
  results?: TestResult[];
  passed?: number;
  total?: number;
  tests?: TestResult[];
  steps?: TestStep[];
}

export interface TestResult {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration?: number;
  error?: string;
}

export interface TestStep {
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: Record<string, unknown>;
}

// Knowledge Base Types
export interface KnowledgeBaseStats {
  totalItems: number;
  categories: number;
  documentCount: number;
  categoryCount: number;
}

export interface KnowledgeBaseStatus {
  status: 'loading' | 'ready' | 'error' | 'empty' | 'online' | 'offline';
  last_updated: string | null;
  // Fields from backend /api/knowledge_base/stats response
  total_documents?: number;
  total_chunks?: number;
  total_facts?: number;
  total_vectors?: number;
  categories?: string[];
  db_size?: number;
  initialized?: boolean;
  rag_available?: boolean;
  // Fields only available during active operations (not sent by stats endpoint)
  progress?: number;
  current_operation?: string | null;
  documents_processed?: number;
  documents_total?: number;
  message?: string;
}

// Terminal Types
export interface TerminalSession {
  id: string;
  sessionId: string;
  isActive: boolean;
  lastActivity: Date;
}

// Settings Types
export interface AppSettings {
  message_display: {
    show_json: boolean;
    show_planning: boolean;
    show_debug: boolean;
    show_thoughts: boolean;
    show_utility: boolean;
    show_sources: boolean;
  };
  browser_integration: {
    enabled: boolean;
    auto_search: boolean;
    auto_screenshot: boolean;
    show_browser_actions: boolean;
  };
  chat: {
    auto_scroll: boolean;
  };
}

// Error Types
export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  details?: Record<string, unknown>;
}

// Environment Configuration
export interface EnvironmentConfig {
  API_BASE_URL: string;
  WS_BASE_URL: string;
  VNC_URL?: string;
  NODE_ENV: string;
}
