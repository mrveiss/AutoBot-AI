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
 */

import slmApiClient from '@/utils/ApiClient'

export interface SecretCreate {
  key: string
  value: string
  category?: string
  description?: string
}

export interface SecretUpdate {
  value?: string
  category?: string
  description?: string
}

export interface SecretResponse {
  id: number
  key: string
  category: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface DependentRolesMapping {
  mapping: Record<string, string[]>
}

export interface ApplySecretsResult {
  success: boolean
  key: string
  dependent_roles: string[]
  target_node_ids: string[]
  output: string
  returncode: number
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
    return slmApiClient.post<ApplySecretsResult>('/secrets/apply', { key })
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
