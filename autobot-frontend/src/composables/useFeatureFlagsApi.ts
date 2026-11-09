// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Feature flags admin calls (#580, #12363 slice 4).
 *
 * The typed `apiClient.call` for /api/admin/feature-flags and /api/admin/access-control, in place of the
 * retired FeatureFlagsApiClient. Each function resolves to the backend's `{ success, ... }` body and
 * THROWS on a non-2xx (an `HttpError`). The contract types `data` as `unknown` or an open dictionary,
 * so the callers narrow it to the shapes in `@/types/featureFlags` (#20867).
 */

import type { EnforcementMode } from '@/types/featureFlags'
import apiClient from '@/utils/ApiClient'

export function getFeatureFlagsStatus() {
  return apiClient.call('get', '/api/admin/feature-flags/status')
}

export function updateEnforcementMode(mode: EnforcementMode) {
  return apiClient.call('put', '/api/admin/feature-flags/enforcement-mode', { body: { mode } })
}

export function setEndpointEnforcement(endpoint: string, mode: EnforcementMode) {
  return apiClient.call('put', '/api/admin/feature-flags/endpoint/{endpoint}', { path: { endpoint }, body: { mode } })
}

export function removeEndpointEnforcement(endpoint: string) {
  return apiClient.call('delete', '/api/admin/feature-flags/endpoint/{endpoint}', { path: { endpoint } })
}

export function getAccessControlMetrics(options: { days?: number; include_details?: boolean } = {}) {
  return apiClient.call('get', '/api/admin/access-control/metrics', { query: options })
}

export function getEndpointMetrics(endpoint: string, days = 7) {
  return apiClient.call('get', '/api/admin/access-control/endpoint/{endpoint}', { path: { endpoint }, query: { days } })
}

export function getUserMetrics(username: string, days = 7) {
  return apiClient.call('get', '/api/admin/access-control/user/{username}', { path: { username }, query: { days } })
}

export function cleanupMetrics() {
  return apiClient.call('post', '/api/admin/access-control/cleanup')
}

export function useFeatureFlagsApi() {
  return {
    getFeatureFlagsStatus, updateEnforcementMode, setEndpointEnforcement, removeEndpointEnforcement,
    getAccessControlMetrics, getEndpointMetrics, getUserMetrics, cleanupMetrics,
  }
}
