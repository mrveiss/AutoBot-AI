// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Shared health-response types (#6920 — deduplicate *HealthResponse interfaces).
 */

/**
 * Vocabulary used by legacy per-module health endpoints and the
 * probe-backed health helpers. Mirrors the backend's `_PROBE_TO_LEGACY`
 * dict values so the two sides stay in sync.
 */
export type LegacyHealthStatus = 'healthy' | 'unavailable' | 'error'

/**
 * Fields shared by every per-module health response. Module-specific
 * interfaces must extend this type rather than redeclaring these fields.
 */
export interface BaseModuleHealthResponse {
  status: LegacyHealthStatus
  redis_connected: boolean
  message?: string
}
