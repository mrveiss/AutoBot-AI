// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * System Secrets API Composable (#1417)
 *
 * Provides REST API integration for encrypted system secrets
 * management via the SLM backend. Admin-only.
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()`, injects the SLM bearer token,
 * and centrally handles 401 for these non-auth endpoints (clear session +
 * redirect to `/login`) — matching the previous axios interceptor that called
 * `authStore.logout()`. Call sites pass endpoints relative to the API base and
 * receive parsed JSON directly.
 *
 * Contract types (#12420 Phase 3): the request/response shapes below are DERIVED
 * from the generated OpenAPI schema (`@/types/generated/api`), which is produced
 * from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare them — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 */

import slmApiClient from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

export type SecretCreate = components['schemas']['SecretCreate']
export type SecretUpdate = components['schemas']['SecretUpdate']
export type SecretResponse = components['schemas']['SecretResponse']
export type ApplySecretsRequest = components['schemas']['ApplySecretsRequest']
export type ApplySecretsResult = components['schemas']['ApplySecretsResponse']

/**
 * `GET /secrets/dependent-roles` returns an untyped `dict` (the backend
 * declares no response_model), so there is no generated schema to derive from —
 * this shape stays hand-declared until the backend types the endpoint.
 */
export interface DependentRolesMapping {
  mapping: Record<string, string[]>
}

export function useSecretsApi() {
  async function listSecrets(): Promise<SecretResponse[]> {
    return slmApiClient.get<SecretResponse[]>('/secrets')
  }

  async function createSecret(data: SecretCreate): Promise<SecretResponse> {
    return slmApiClient.post<SecretResponse>('/secrets', data)
  }

  async function updateSecret(
    key: string,
    data: SecretUpdate
  ): Promise<SecretResponse> {
    return slmApiClient.put<SecretResponse>(
      `/secrets/${encodeURIComponent(key)}`,
      data
    )
  }

  async function deleteSecret(key: string): Promise<void> {
    await slmApiClient.delete(`/secrets/${encodeURIComponent(key)}`)
  }

  async function getDependentRolesMapping(): Promise<DependentRolesMapping> {
    return slmApiClient.get<DependentRolesMapping>('/secrets/dependent-roles')
  }

  async function applySecret(key: string): Promise<ApplySecretsResult> {
    const body: ApplySecretsRequest = { key }
    return slmApiClient.post<ApplySecretsResult>('/secrets/apply', body)
  }

  return {
    listSecrets,
    createSecret,
    updateSecret,
    deleteSecret,
    getDependentRolesMapping,
    applySecret,
  }
}
