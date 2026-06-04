// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
// Typed models matching the AutoBot REST API response shapes.

// ---------------------------------------------------------------------------
// Generic envelope
// ---------------------------------------------------------------------------

export interface DataResponse<T> {
  success: boolean;
  data?: T | null;
  message?: string | null;
  timestamp?: string | null;
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: string;
  content: string;
  timestamp?: string | null;
}

export interface Session {
  session_id: string;
  title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  message_count?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface SessionList {
  sessions: Session[];
  total?: number | null;
}

export interface SessionMessages {
  session_id: string;
  messages: ChatMessage[];
  total?: number | null;
}

export interface SessionCreate {
  session_id: string;
  title?: string | null;
}

export interface SessionUpdate {
  session_id: string;
  success: boolean;
}

export interface SessionDelete {
  session_id: string;
  success: boolean;
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export interface AgentHealth {
  status: string;
  version?: string | null;
  uptime?: number | null;
  components?: Record<string, unknown> | null;
}

export interface AgentConfig {
  enabled?: boolean | null;
  personality?: string | null;
  model?: string | null;
  settings?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Knowledge
// ---------------------------------------------------------------------------

export interface KnowledgeEntry {
  id?: string | null;
  content?: string | null;
  source?: string | null;
  category?: string | null;
  created_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface KnowledgeStats {
  total_entries?: number | null;
  categories?: Record<string, number> | null;
  last_updated?: string | null;
}

export interface KnowledgeAddResult {
  success: boolean;
  id?: string | null;
  message?: string | null;
}

export interface KnowledgeSearchResult {
  results: KnowledgeEntry[];
  total?: number | null;
  query?: string | null;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface AnalyticsUsage {
  total_requests?: number | null;
  total_tokens?: number | null;
  cost_usd?: number | null;
  period?: string | null;
}

export interface AnalyticsPerformance {
  avg_latency_ms?: number | null;
  p95_latency_ms?: number | null;
  error_rate?: number | null;
  period?: string | null;
}
