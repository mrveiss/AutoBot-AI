// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Advanced Control API Client
 *
 * Provides type-safe access to the Advanced Control API endpoints.
 * Issue #583: GUI integration for Advanced Control & Session Takeover
 */

import { getConfig } from '@/config/ssot-config';
import { createLogger } from '@/utils/debugUtils';
import type { ApiResponse } from '@/types/api';

const logger = createLogger('AdvancedControlApiClient');

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

export interface TakeoverCompletionRequest {
  resolution?: string;
  handback_notes?: string;
}

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

// ==================================================================================
// API CLIENT
// ==================================================================================

/**
 * Advanced Control API Client
 *
 * Communicates with /api/advanced-control endpoints for desktop streaming,
 * takeover management, and system monitoring.
 */
class AdvancedControlApiClient {
  private getBaseUrl(): string {
    return getConfig().backendUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const baseUrl = this.getBaseUrl();
    const url = `${baseUrl}${endpoint}`;

    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers: { ...defaultHeaders, ...options.headers },
      });

      const data = await response.json();

      if (!response.ok) {
        logger.error(`API request failed: ${response.status}`, data);
        return {
          success: false,
          error: data.detail || data.message || `Request failed with status ${response.status}`,
        };
      }

      return { success: true, data };
    } catch (error) {
      logger.error('API request error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  // ==================================================================================
  // ADVANCED CONTROL INFO
  // ==================================================================================

  /**
   * Get advanced control capabilities info
   * GET /api/advanced-control/
   */
  async getControlInfo(): Promise<ApiResponse<AdvancedControlInfo>> {
    return this.request<AdvancedControlInfo>('/api/advanced-control/');
  }

  // ==================================================================================
  // DESKTOP STREAMING ENDPOINTS
  // ==================================================================================

  /**
   * Create a new desktop streaming session
   * POST /api/advanced-control/streaming/create
   */
  async createStreamingSession(
    request: StreamingSessionRequest
  ): Promise<ApiResponse<StreamingSessionResponse>> {
    return this.request<StreamingSessionResponse>('/api/advanced-control/streaming/create', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Terminate a desktop streaming session
   * DELETE /api/advanced-control/streaming/{session_id}
   */
  async terminateStreamingSession(
    sessionId: string
  ): Promise<ApiResponse<{ success: boolean; session_id: string }>> {
    return this.request(`/api/advanced-control/streaming/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
  }

  /**
   * List all active streaming sessions
   * GET /api/advanced-control/streaming/sessions
   */
  async listStreamingSessions(): Promise<ApiResponse<{
    sessions: StreamingSession[];
    count: number;
  }>> {
    return this.request('/api/advanced-control/streaming/sessions');
  }

  /**
   * Get desktop streaming capabilities
   * GET /api/advanced-control/streaming/capabilities
   */
  async getStreamingCapabilities(): Promise<ApiResponse<StreamingCapabilities>> {
    return this.request<StreamingCapabilities>('/api/advanced-control/streaming/capabilities');
  }

  // ==================================================================================
  // TAKEOVER MANAGEMENT ENDPOINTS
  // ==================================================================================

  /**
   * Request human takeover of autonomous operations
   * POST /api/advanced-control/takeover/request
   */
  async requestTakeover(
    request: TakeoverRequest
  ): Promise<ApiResponse<{ success: boolean; request_id: string }>> {
    return this.request('/api/advanced-control/takeover/request', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Approve a takeover request and start session
   * POST /api/advanced-control/takeover/{request_id}/approve
   */
  async approveTakeover(
    requestId: string,
    approval: TakeoverApprovalRequest
  ): Promise<ApiResponse<{ success: boolean; session_id: string }>> {
    return this.request(`/api/advanced-control/takeover/${encodeURIComponent(requestId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(approval),
    });
  }

  /**
   * Execute an action during a takeover session
   * POST /api/advanced-control/takeover/sessions/{session_id}/action
   */
  async executeTakeoverAction(
    sessionId: string,
    action: TakeoverActionRequest
  ): Promise<ApiResponse<{ success: boolean; result: Record<string, unknown> }>> {
    return this.request(`/api/advanced-control/takeover/sessions/${encodeURIComponent(sessionId)}/action`, {
      method: 'POST',
      body: JSON.stringify(action),
    });
  }

  /**
   * Pause an active takeover session
   * POST /api/advanced-control/takeover/sessions/{session_id}/pause
   */
  async pauseTakeoverSession(
    sessionId: string
  ): Promise<ApiResponse<{ success: boolean; session_id: string; status: string }>> {
    return this.request(`/api/advanced-control/takeover/sessions/${encodeURIComponent(sessionId)}/pause`, {
      method: 'POST',
    });
  }

  /**
   * Resume a paused takeover session
   * POST /api/advanced-control/takeover/sessions/{session_id}/resume
   */
  async resumeTakeoverSession(
    sessionId: string
  ): Promise<ApiResponse<{ success: boolean; session_id: string; status: string }>> {
    return this.request(`/api/advanced-control/takeover/sessions/${encodeURIComponent(sessionId)}/resume`, {
      method: 'POST',
    });
  }

  /**
   * Complete a takeover session and return control
   * POST /api/advanced-control/takeover/sessions/{session_id}/complete
   */
  async completeTakeoverSession(
    sessionId: string,
    completion: TakeoverCompletionRequest = {}
  ): Promise<ApiResponse<{ success: boolean; session_id: string; status: string }>> {
    return this.request(`/api/advanced-control/takeover/sessions/${encodeURIComponent(sessionId)}/complete`, {
      method: 'POST',
      body: JSON.stringify(completion),
    });
  }

  /**
   * Get all pending takeover requests
   * GET /api/advanced-control/takeover/pending
   */
  async getPendingTakeovers(): Promise<ApiResponse<{
    pending_requests: PendingTakeoverRequest[];
    count: number;
  }>> {
    return this.request('/api/advanced-control/takeover/pending');
  }

  /**
   * Get all active takeover sessions
   * GET /api/advanced-control/takeover/active
   */
  async getActiveTakeovers(): Promise<ApiResponse<{
    active_sessions: ActiveTakeoverSession[];
    count: number;
  }>> {
    return this.request('/api/advanced-control/takeover/active');
  }

  /**
   * Get takeover system status
   * GET /api/advanced-control/takeover/status
   */
  async getTakeoverStatus(): Promise<ApiResponse<TakeoverSystemStatus>> {
    return this.request<TakeoverSystemStatus>('/api/advanced-control/takeover/status');
  }

  // ==================================================================================
  // SYSTEM MONITORING ENDPOINTS
  // ==================================================================================

  /**
   * Get comprehensive system monitoring status
   * GET /api/advanced-control/system/status
   */
  async getSystemStatus(): Promise<ApiResponse<SystemMonitoringResponse>> {
    return this.request<SystemMonitoringResponse>('/api/advanced-control/system/status');
  }

  /**
   * Quick health check endpoint
   * GET /api/advanced-control/system/health
   */
  async getSystemHealth(): Promise<ApiResponse<SystemHealthResponse>> {
    return this.request<SystemHealthResponse>('/api/advanced-control/system/health');
  }

  /**
   * Emergency stop for all autonomous operations
   * POST /api/advanced-control/system/emergency-stop
   */
  async emergencyStop(): Promise<ApiResponse<{
    success: boolean;
    message: string;
    takeover_request_id: string;
  }>> {
    return this.request('/api/advanced-control/system/emergency-stop', {
      method: 'POST',
    });
  }

  // ==================================================================================
  // WEBSOCKET HELPERS
  // ==================================================================================

  /**
   * Get WebSocket URL for real-time system monitoring
   */
  getMonitoringWebSocketUrl(): string {
    const cfg = getConfig();
    const wsProtocol = cfg.httpProtocol === 'https' ? 'wss' : 'ws';
    return `${wsProtocol}://${cfg.vm.main}:${cfg.port.backend}/api/advanced-control/ws/monitoring`;
  }

  /**
   * Get WebSocket URL for desktop streaming control
   */
  getDesktopWebSocketUrl(sessionId: string): string {
    const cfg = getConfig();
    const wsProtocol = cfg.httpProtocol === 'https' ? 'wss' : 'ws';
    return `${wsProtocol}://${cfg.vm.main}:${cfg.port.backend}/api/advanced-control/ws/desktop/${encodeURIComponent(sessionId)}`;
  }
}

// Export singleton instance
export const advancedControlApiClient = new AdvancedControlApiClient();
export default advancedControlApiClient;
