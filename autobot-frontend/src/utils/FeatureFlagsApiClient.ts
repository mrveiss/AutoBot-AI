// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Feature Flags API Client
 *
 * Provides type-safe access to the Feature Flags Admin API endpoints.
 * Issue #580: GUI integration for feature flags management
 */

import appConfig from '@/config/AppConfig.js';
import { NetworkConstants } from '@/constants/network';
import { createLogger } from '@/utils/debugUtils';
import type { ApiResponse } from '@/types/api';

const logger = createLogger('FeatureFlagsApiClient');

// Enforcement mode enum matching backend
export type EnforcementMode = 'disabled' | 'log_only' | 'enforced';

// API Response types
export interface FeatureFlagsStatus {
  current_mode: EnforcementMode;
  history: HistoryEntry[];
  endpoint_overrides: Record<string, EnforcementMode>;
  total_endpoints_configured: number;
}

export interface HistoryEntry {
  timestamp: string;
  mode: EnforcementMode;
  changed_by: string;
}

export interface ViolationStatistics {
  total_violations: number;
  period_days: number;
  by_endpoint: Record<string, number>;
  by_user: Record<string, number>;
  by_day: Record<string, number>;
  current_mode: EnforcementMode;
  daily_change_percent?: number;
  recent_violations?: ViolationRecord[];
}

export interface ViolationRecord {
  id: string;
  session_id: string;
  username: string;
  actual_owner: string;
  endpoint: string;
  ip_address: string;
  enforcement_mode: string;
  timestamp: number;
  date: string;
}

export interface EndpointStatistics {
  endpoint: string;
  total_violations: number;
  by_day: Record<string, number>;
  period_days: number;
}

export interface UserStatistics {
  username: string;
  total_violations: number;
  by_day: Record<string, number>;
  period_days: number;
}

// Re-export ApiResponse from canonical source for convenience
export type { ApiResponse } from '@/types/api';

/**
 * Feature Flags API Client
 *
 * Communicates with /api/admin/feature-flags and /api/admin/access-control endpoints
 */
class FeatureFlagsApiClient {
  private baseUrl: string = '';
  private baseUrlPromise: Promise<string> | null = null;

  constructor() {
    this.initializeBaseUrl();
  }

  private async initializeBaseUrl(): Promise<void> {
    try {
      this.baseUrl = await appConfig.getApiUrl('');
    } catch (_error) {
      logger.warn('AppConfig initialization failed, using NetworkConstants fallback');
      this.baseUrl = `http://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}`;
    }
  }

  private async ensureBaseUrl(): Promise<string> {
    if (this.baseUrl) {
      return this.baseUrl;
    }

    if (!this.baseUrlPromise) {
      this.baseUrlPromise = this.initializeBaseUrl().then(() => this.baseUrl);
    }

    return await this.baseUrlPromise;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const baseUrl = await this.ensureBaseUrl();
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
        logger.error('API request failed:', { status: response.status, data });
        return {
          success: false,
          error: data.detail || data.message || `Request failed with status ${response.status}`,
        };
      }

      return data;
    } catch (error) {
      logger.error('API request error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  // ==================================================================================
  // FEATURE FLAGS ENDPOINTS
  // ==================================================================================

  /**
   * Get current feature flags status and rollout statistics
   * GET /api/admin/feature-flags/status
   */
  async getFeatureFlagsStatus(): Promise<ApiResponse<FeatureFlagsStatus>> {
    return this.request<FeatureFlagsStatus>('/api/admin/feature-flags/status');
  }

  /**
   * Update global enforcement mode
   * PUT /api/admin/feature-flags/enforcement-mode
   */
  async updateEnforcementMode(mode: EnforcementMode): Promise<ApiResponse<{
    new_mode: EnforcementMode;
    updated_by: string;
    updated_at: string;
  }>> {
    return this.request('/api/admin/feature-flags/enforcement-mode', {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    });
  }

  /**
   * Set enforcement mode for a specific endpoint
   * PUT /api/admin/feature-flags/endpoint/{endpoint}
   */
  async setEndpointEnforcement(
    endpoint: string,
    mode: EnforcementMode
  ): Promise<ApiResponse<{ endpoint: string; mode: EnforcementMode }>> {
    // URL encode the endpoint path
    const encodedEndpoint = encodeURIComponent(endpoint);
    return this.request(`/api/admin/feature-flags/endpoint/${encodedEndpoint}`, {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    });
  }

  /**
   * Remove endpoint-specific enforcement override
   * DELETE /api/admin/feature-flags/endpoint/{endpoint}
   */
  async removeEndpointEnforcement(
    endpoint: string
  ): Promise<ApiResponse<{ endpoint: string; reverted_to: string }>> {
    const encodedEndpoint = encodeURIComponent(endpoint);
    return this.request(`/api/admin/feature-flags/endpoint/${encodedEndpoint}`, {
      method: 'DELETE',
    });
  }

  // ==================================================================================
  // ACCESS CONTROL METRICS ENDPOINTS
  // ==================================================================================

  /**
   * Get access control violation statistics
   * GET /api/admin/access-control/metrics
   */
  async getAccessControlMetrics(options: {
    days?: number;
    include_details?: boolean;
  } = {}): Promise<ApiResponse<ViolationStatistics>> {
    const params = new URLSearchParams();
    if (options.days !== undefined) {
      params.append('days', options.days.toString());
    }
    if (options.include_details !== undefined) {
      params.append('include_details', options.include_details.toString());
    }

    const queryString = params.toString() ? `?${params.toString()}` : '';
    return this.request<ViolationStatistics>(
      `/api/admin/access-control/metrics${queryString}`
    );
  }

  /**
   * Get violation statistics for a specific endpoint
   * GET /api/admin/access-control/endpoint/{endpoint}
   */
  async getEndpointMetrics(
    endpoint: string,
    days: number = 7
  ): Promise<ApiResponse<EndpointStatistics>> {
    const encodedEndpoint = encodeURIComponent(endpoint);
    return this.request<EndpointStatistics>(
      `/api/admin/access-control/endpoint/${encodedEndpoint}?days=${days}`
    );
  }

  /**
   * Get violation statistics for a specific user
   * GET /api/admin/access-control/user/{username}
   */
  async getUserMetrics(
    username: string,
    days: number = 7
  ): Promise<ApiResponse<UserStatistics>> {
    const encodedUsername = encodeURIComponent(username);
    return this.request<UserStatistics>(
      `/api/admin/access-control/user/${encodedUsername}?days=${days}`
    );
  }

  /**
   * Cleanup old metrics
   * POST /api/admin/access-control/cleanup
   */
  async cleanupMetrics(): Promise<ApiResponse<{ message: string }>> {
    return this.request('/api/admin/access-control/cleanup', {
      method: 'POST',
    });
  }
}

// Export singleton instance
export const featureFlagsApiClient = new FeatureFlagsApiClient();
export default featureFlagsApiClient;
