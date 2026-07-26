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
 */

import slmApiClient from '@/utils/ApiClient'

export interface APIKeyCreate {
  name: string
  description?: string
  scopes: string[]
  expires_days?: number
}

export interface APIKeyCreateResponse {
  id: string
  key: string
  key_prefix: string
  name: string
  scopes: string[]
  expires_at: string | null
  created_at: string
}

export interface APIKeyResponse {
  id: string
  key_prefix: string
  name: string
  description: string | null
  scopes: string[]
  is_active: boolean
  expires_at: string | null
  last_used_at: string | null
  usage_count: number
  created_at: string
}

export interface APIKeyListResponse {
  keys: APIKeyResponse[]
  total: number
}

export interface APIKeyUpdate {
  name?: string
  description?: string
}

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

  async function getScopes(): Promise<Record<string, string>> {
    return slmApiClient.get<Record<string, string>>('/api-keys/scopes')
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
