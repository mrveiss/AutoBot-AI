// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Advanced Control types (#583, #12363).
 *
 * Narrow shapes for the /api/advanced-control replies. The generated contract types most of these
 * as `unknown[]` or open dictionaries, so the call sites narrow to these (tracked in #20867).
 */

// ==================================================================================
// STREAMING SESSION TYPES
// ==================================================================================

export interface StreamingSessionRequest {
  user_id: string;
  resolution?: string;
  depth?: number;
}

export interface StreamingSessionResponse {
  session_id: string;
  vnc_port: number;
  novnc_port: number | null;
  display: string;
  vnc_url: string;
  web_url: string | null;
  websocket_endpoint: string;
}

export interface StreamingSession {
  session_id: string;
  user_id: string;
  vnc_port: number;
  novnc_port: number | null;
  display: string;
  created_at: string;
  status: 'active' | 'paused' | 'terminated';
}

export interface StreamingCapabilities {
  vnc_available: boolean;
  novnc_available: boolean;
  max_sessions: number;
  supported_resolutions: string[];
  supported_depths: number[];
}

// ==================================================================================
// TAKEOVER TYPES
// ==================================================================================

export type TakeoverTrigger =
  | 'MANUAL_REQUEST'
  | 'CRITICAL_ERROR'
  | 'SECURITY_CONCERN'
  | 'USER_INTERVENTION_REQUIRED'
  | 'SYSTEM_OVERLOAD'
  | 'APPROVAL_REQUIRED'
  | 'TIMEOUT_EXCEEDED';

export type TakeoverPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type TakeoverStatus = 'pending' | 'approved' | 'active' | 'paused' | 'completed' | 'rejected';

export interface TakeoverRequest {
  trigger: TakeoverTrigger;
  reason: string;
  requesting_agent?: string;
  affected_tasks?: string[];
  priority?: TakeoverPriority;
  timeout_minutes?: number;
  auto_approve?: boolean;
}

export interface TakeoverApprovalRequest {
  human_operator: string;
  takeover_scope?: Record<string, unknown>;
}

export interface TakeoverActionRequest {
  action_type: string;
  action_data: Record<string, unknown>;
}

export type TakeoverCompletionRequest = {
  resolution?: string;
  handback_notes?: string;
};

export interface PendingTakeoverRequest {
  request_id: string;
  trigger: TakeoverTrigger;
  reason: string;
  requesting_agent: string | null;
  affected_tasks: string[];
  priority: TakeoverPriority;
  created_at: string;
  timeout_at: string | null;
  auto_approve: boolean;
}

export interface ActiveTakeoverSession {
  session_id: string;
  request_id: string;
  human_operator: string;
  status: TakeoverStatus;
  started_at: string;
  paused_at: string | null;
  actions_executed: number;
  takeover_scope: Record<string, unknown>;
}

export interface TakeoverSystemStatus {
  pending_requests_count: number;
  active_sessions_count: number;
  paused_tasks_count: number;
  total_completed_sessions: number;
  system_status: 'normal' | 'takeover_active' | 'emergency';
}

// ==================================================================================
// SYSTEM MONITORING TYPES
// ==================================================================================

export interface ResourceUsage {
  cpu_percent: number;
  memory_percent: number;
  disk_usage: number;
  process_count: number;
  load_average: [number, number, number] | null;
}

export interface SystemMonitoringResponse {
  system_status: {
    status: string;
    timestamp: number;
    uptime_seconds: number;
    streaming_capabilities: StreamingCapabilities;
  };
  active_sessions: StreamingSession[];
  pending_takeovers: PendingTakeoverRequest[];
  active_takeovers: ActiveTakeoverSession[];
  resource_usage: ResourceUsage;
}

export interface SystemHealthResponse {
  status: 'healthy' | 'unhealthy';
  desktop_streaming_available: boolean;
  novnc_available: boolean;
  active_streaming_sessions: number;
  pending_takeovers: number;
  active_takeovers: number;
  paused_tasks: number;
  error?: string;
}

export interface AdvancedControlInfo {
  name: string;
  version: string;
  features: string[];
  endpoints: {
    streaming: string;
    takeover: string;
    system: string;
    websockets: {
      monitoring: string;
      desktop: string;
    };
  };
}
