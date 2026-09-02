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
 * `GET /secrets/dependent-roles`. Derived since #13139 gave the endpoint a
 * `response_model` (`autobot-slm-backend/api/secrets.py`, returning
 * `DependentRolesResponse(mapping=_SECRET_TO_DEPENDENT_ROLES)`), replacing the
 * hand-declared shape this file used to carry.
 */
export type DependentRolesResponse = components['schemas']['DependentRolesResponse']

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

  async function getDependentRolesMapping(): Promise<DependentRolesResponse> {
    return slmApiClient.get<DependentRolesResponse>('/secrets/dependent-roles')
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
