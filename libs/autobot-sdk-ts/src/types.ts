// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// Typed models matching the AutoBot REST API response shapes.
//
// #15528: these used to describe a response the routes never send (invented
// field names, or a DataResponse envelope around a route that returns a flat
// document). Rewritten to match the routes exactly, mirroring the Python SDK's
// already-corrected `autobot_sdk/models.py` (#15114, #15116, #15118).

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

/** One row inside `SessionMessages.messages`. The backend declares this list
 * untyped (`List[Any]`); every field is optional and unlisted keys are simply
 * not modelled -- there is no server-side contract to hold them to. */
export interface ChatMessage {
  id?: string | null;
  sender?: string | null;
  text?: string | null;
  messageType?: string | null;
  metadata?: Record<string, unknown> | null;
  timestamp?: string | null;
  sources?: Record<string, unknown>[] | null;
  toolMarkers?: unknown[] | null;
  authorId?: string | null;
}

/** One row inside `SessionList.sessions`. Same untyped-list caveat as
 * {@link ChatMessage}. */
export interface Session {
  id?: string | null;
  chatId?: string | null;
  title?: string | null;
  name?: string | null;
  messages?: ChatMessage[] | null;
  messageCount?: number | null;
  createdAt?: string | null;
  createdTime?: string | null;
  updatedAt?: string | null;
  lastModified?: string | null;
  updatedAtEpoch?: number | null;
  isActive?: boolean | null;
  fileSize?: number | null;
  fast_mode?: boolean | null;
  companyId?: string | null;
  sessionKind?: string | null;
}

/** `data` payload of `GET /chat/sessions`. */
export interface SessionList {
  sessions: Session[];
  count?: number | null;
  scope?: string | null;
  org_id?: string | null;
  team_id?: string | null;
  intentional_empty?: boolean | null;
}

/** `data` payload of `GET /chat/sessions/{id}`. */
export interface SessionMessages {
  messages: ChatMessage[];
  session_id?: string | null;
  total_count?: number | null;
  page?: number | null;
  per_page?: number | null;
}

/** `data` payload of `POST /chat/sessions`. */
export interface SessionCreate {
  id?: string | null;
  title?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  last_modified?: string | null;
}

/** `data` payload of `PUT /chat/sessions/{id}`. */
export interface SessionUpdate {
  id?: string | null;
  title?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  last_modified?: string | null;
}

export interface SessionDeleteFileHandling {
  files_handled?: boolean | null;
  action_taken?: string | null;
  files_deleted?: number | null;
  files_transferred?: number | null;
  files_failed?: number | null;
  error?: string | null;
}

export interface SessionDeleteTerminalCleanup {
  terminal_sessions_closed?: number | null;
  pending_approvals_cleared?: number | null;
  error?: string | null;
}

export interface SessionDeleteKbCleanup {
  facts_deleted?: number | null;
  facts_preserved?: number | null;
  cleanup_error?: string | null;
}

export interface SessionDeleteTranscriptCleanup {
  transcript_deleted?: boolean | null;
  error?: string | null;
}

/** `data` payload of `DELETE /chat/sessions/{id}`. The outcome flag is
 * `deleted`, not `success` -- the envelope already has a `success`. */
export interface SessionDelete {
  session_id?: string | null;
  deleted?: boolean | null;
  file_handling?: SessionDeleteFileHandling | null;
  terminal_cleanup?: SessionDeleteTerminalCleanup | null;
  kb_cleanup?: SessionDeleteKbCleanup | null;
  transcript_cleanup?: SessionDeleteTranscriptCleanup | null;
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

/** `GET /agent/health/detailed`. */
export interface AgentHealth {
  status?: string | null;
  ai_stack_available?: boolean | null;
  multi_agent_coordination?: boolean | null;
  advanced_capabilities?: boolean | null;
  timestamp?: string | null;
  error?: string | null;
}

export interface AgentConfigHealthCheck {
  last_check?: string | null;
  response_time?: number | null;
  status?: string | null;
}

export interface AgentConfigOptions {
  available_models?: string[] | null;
  available_providers?: string[] | null;
  configurable_settings?: string[] | null;
}

/** One agent's configuration, `GET /agent_config/agents/{id}` -- a flat
 * document, not a `DataResponse` envelope. */
export interface AgentConfig {
  id?: string | null;
  name?: string | null;
  description?: string | null;
  enabled?: boolean | null;
  current_model?: string | null;
  default_model?: string | null;
  provider?: string | null;
  priority?: number | null;
  status?: string | null;
  tasks?: string[] | null;
  mcp_tools?: string[] | null;
  config_source?: string | null;
  configuration_options?: AgentConfigOptions | null;
  health_check?: AgentConfigHealthCheck | null;
}

// ---------------------------------------------------------------------------
// Knowledge
// ---------------------------------------------------------------------------

/** One row inside `KnowledgeEntries.entries`. */
export interface KnowledgeEntry {
  key?: string | null;
  title?: string | null;
  content?: string | null;
  category?: string | null;
  type?: string | null;
  created_at?: string | null;
  metadata?: Record<string, unknown> | null;
}

/** `GET /knowledge_base/stats`. Not a `DataResponse` envelope. */
export interface KnowledgeStats {
  status?: string | null;
  total_documents?: number | null;
  total_chunks?: number | null;
  total_facts?: number | null;
  total_vectors?: number | null;
  categories?: string[] | null;
  db_size?: number | null;
  last_updated?: string | null;
  redis_db?: unknown;
  index_name?: string | null;
  initialized?: boolean | null;
  rag_available?: boolean | null;
  vectorization_stats?: Record<string, unknown> | null;
}

/** `POST /knowledge_base/add_text`. Not a `DataResponse` envelope. */
export interface KnowledgeAddResult {
  status?: string | null;
  message?: string | null;
  fact_id?: string | null;
  text_length?: number | null;
  title?: string | null;
  source?: string | null;
  access_level?: string | null;
  visibility?: string | null;
}

/** `POST /knowledge_base/search`. Not a `DataResponse` envelope. Result rows
 * are freeform on this route (the backend declares them `List[Dict]`), so
 * they're typed as the route types them rather than as {@link KnowledgeEntry},
 * which describes `GET /knowledge_base/entries`'s rows -- a different route. */
export interface KnowledgeSearchResult {
  results: Record<string, unknown>[];
  total_results?: number | null;
  query?: string | null;
  mode?: string | null;
  kb_implementation?: string | null;
  rag_applied?: boolean | null;
  reranking_applied?: boolean | null;
  status?: string | null;
  synthesized_response?: string | null;
  original_query?: string | null;
  reformulated_queries?: string[] | null;
  message?: string | null;
}

/** `GET /knowledge_base/entries`. Not a `DataResponse` envelope, and a
 * distinct shape from {@link KnowledgeSearchResult} -- the two share no
 * field. Cursor-paginated: `next_cursor` is the token to pass back in, not
 * an offset. */
export interface KnowledgeEntries {
  entries: KnowledgeEntry[];
  next_cursor?: string | null;
  count?: number | null;
  has_more?: boolean | null;
  message?: string | null;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

/** `GET /analytics/usage/statistics`. Not a `DataResponse` envelope; the
 * route groups its numbers into per-subject blocks. */
export interface AnalyticsUsage {
  api_usage?: Record<string, unknown> | null;
  websocket_usage?: Record<string, unknown> | null;
  system_usage?: Record<string, unknown> | null;
  knowledge_base_usage?: Record<string, unknown> | null;
  analysis_period?: Record<string, unknown> | null;
  error?: string | null;
}

/** `GET /analytics/performance/metrics`. Not a `DataResponse` envelope. */
export interface AnalyticsPerformance {
  system_performance?: Record<string, unknown> | null;
  api_performance?: Record<string, unknown> | null;
  advanced_metrics?: Record<string, unknown> | null;
  detailed_metrics?: Record<string, unknown> | null;
  hardware_performance?: Record<string, unknown> | null;
  network_io?: Record<string, unknown> | null;
  historical_context?: Record<string, unknown> | null;
  error?: string | null;
}
