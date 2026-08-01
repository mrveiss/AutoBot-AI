// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * LLM Config API Composable (#2371)
 *
 * Provides REST API integration for LLM provider configuration
 * management via the SLM backend. Admin-only.
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token
 * (same `slm_access_token` storage the auth store reads), and centrally handles
 * 401 for these non-auth endpoints by clearing the session and redirecting to
 * `/login` — matching the previous per-composable axios interceptor that called
 * `authStore.logout()`. Call sites therefore pass endpoints relative to the API
 * base and receive parsed JSON directly (no axios `.data`).
 *
 * Contract types (#12420 Phase 3): the request/response shapes below are DERIVED
 * from the generated OpenAPI schema (`@/types/generated/api`), which is produced
 * from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare them — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 */

import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

export type LLMProviderConfig = components['schemas']['LLMProviderConfig']
export type LLMConfig = components['schemas']['LLMConfig']
export type LLMConfigResponse = components['schemas']['LLMConfigResponse']
export type LLMTestRequest = components['schemas']['LLMTestRequest']
export type LLMTestResponse = components['schemas']['LLMTestResponse']
export type LLMApplyRequest = components['schemas']['LLMApplyRequest']
export type LLMApplyResponse = components['schemas']['LLMApplyResponse']

export function useLlmConfigApi() {
  async function getConfig(): Promise<LLMConfigResponse> {
    return slmApiClient.get<LLMConfigResponse>('/settings/admin/llm')
  }

  async function saveConfig(config: LLMConfig): Promise<LLMConfigResponse> {
    return slmApiClient.put<LLMConfigResponse>('/settings/admin/llm', config)
  }

  async function testConnection(
    request: LLMTestRequest
  ): Promise<LLMTestResponse> {
    return slmApiClient.post<LLMTestResponse>('/settings/admin/llm/test', request)
  }

  async function applyToFleet(nodeIds?: string[]): Promise<LLMApplyResponse> {
    const body: LLMApplyRequest = { node_ids: nodeIds || null }
    return slmApiClient.post<LLMApplyResponse>('/settings/admin/llm/apply', body)
  }

  return {
    getConfig,
    saveConfig,
    testConnection,
    applyToFleet,
  }
}
