// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Feature flags types (#580, #12363).
 *
 * Narrow shapes for the /api/admin/feature-flags and /api/admin/access-control replies. The generated
 * contract types their `data` as an open dictionary or `unknown`, so the panel narrows to these (#20867).
 */

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
