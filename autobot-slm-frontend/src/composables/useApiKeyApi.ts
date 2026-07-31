// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * API Key Management API Composable
 *
 * Provides REST API integration for API key management
 * via the SLM backend.
 * Issue #576 - User Management System Phase 5 (API Keys).
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token
 * (same `slm_access_token` storage the auth store reads), and centrally handles
 * 401 for these non-auth endpoints by clearing the session and redirecting to
 * `/login` — matching the previous per-composable axios interceptor that called
 * `authStore.logout()`. Call sites therefore pass endpoints relative to the API
 * base and receive parsed JSON directly (no axios `.data`).
 *
 * Contract types (#12420 Phase 3): every request/response shape below is
 * DERIVED from the generated OpenAPI schema (`@/types/generated/api`), which is
 * produced from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare these — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 * Re-run `npm run gen:types:openapi && npm run gen:types` after a backend change.
 */

import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

export type APIKeyCreate = components['schemas']['APIKeyCreate']
export type APIKeyCreateResponse = components['schemas']['APIKeyCreateResponse']
export type APIKeyResponse = components['schemas']['APIKeyResponse']
export type APIKeyListResponse = components['schemas']['APIKeyListResponse']
export type APIKeyUpdate = components['schemas']['APIKeyUpdate']
export type APIScopesResponse = components['schemas']['APIScopesResponse']

export function useApiKeyApi() {
  async function createKey(data: APIKeyCreate): Promise<APIKeyCreateResponse> {
    return slmApiClient.post<APIKeyCreateResponse>('/api-keys', data)
  }

  async function listKeys(): Promise<APIKeyListResponse> {
    return slmApiClient.get<APIKeyListResponse>('/api-keys')
  }

  async function getKey(keyId: string): Promise<APIKeyResponse> {
    return slmApiClient.get<APIKeyResponse>(`/api-keys/${keyId}`)
  }

  async function updateKey(
    keyId: string,
    data: APIKeyUpdate
  ): Promise<APIKeyResponse> {
    return slmApiClient.patch<APIKeyResponse>(`/api-keys/${keyId}`, data)
  }

  async function revokeKey(keyId: string): Promise<void> {
    await slmApiClient.delete(`/api-keys/${keyId}`)
  }

  /**
   * Available API-key scopes as a `{ scope: description }` map.
   *
   * The endpoint returns an ENVELOPE — `APIScopesResponse { scopes: dict }`
   * (`autobot-slm-backend/api/api_keys.py:118-121`) — not the bare map. This
   * composable previously typed the response as `Record<string, string>` and
   * returned it unwrapped, so the scope picker in SecuritySettings.vue iterated
   * the envelope and rendered a single bogus entry keyed `scopes`. Wiring the
   * generated contract exposed that; unwrap here so callers keep the bare map.
   *
   * The backend declares `scopes` as an untyped `dict`, so the generated value
   * type is `unknown`; the values are scope descriptions, normalised to string.
   */
  async function getScopes(): Promise<Record<string, string>> {
    const response = await slmApiClient.get<APIScopesResponse>('/api-keys/scopes')
    return Object.fromEntries(
      Object.entries(response.scopes ?? {}).map(([scope, description]) => [
        scope,
        String(description),
      ])
    )
  }

  return {
    createKey,
    listKeys,
    getKey,
    updateKey,
    revokeKey,
    getScopes,
  }
}
