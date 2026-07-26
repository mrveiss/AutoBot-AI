// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SSO Provider Management API Composable
 *
 * Provides REST API integration for SSO/OAuth2/LDAP/SAML provider
 * management via the SLM backend.
 * Issue #576 - User Management System Phase 4 (SSO).
 *
 * Migrated onto the canonical `slmApiClient` (#12420 Phase 2). The client
 * resolves the base URL via `getSlmApiBase()` and injects the SLM bearer token.
 *
 * 401 handling — the previous axios interceptor logged the user out on ANY 401.
 * For the provider CRUD endpoints (non-auth) the canonical client reproduces
 * this: it clears the session and redirects to `/login`. The client, however,
 * intentionally skips its session-clearing handler for `/auth/**` endpoints (a
 * 401 there is a credential failure, not a rejected session), so the SSO login
 * flow methods that hit `/auth/sso/**` wrap their call in `withAuthGuard` to
 * preserve the historic "logout on 401" behavior explicitly.
 */

import slmApiClient from '@/utils/ApiClient'
import { useAuthStore } from '@/stores/auth'

// =============================================================================
// Type Definitions
// =============================================================================

export interface SSOProviderResponse {
  id: string
  org_id: string | null
  provider_type: string
  name: string
  is_active: boolean
  is_social: boolean
  allow_user_creation: boolean
  default_role: string | null
  group_mapping: Record<string, string>
  last_sync_at: string | null
  created_at: string
  updated_at: string
}

export interface SSOProviderListResponse {
  providers: SSOProviderResponse[]
  total: number
}

export interface SSOProviderCreate {
  provider_type: string
  name: string
  config: Record<string, unknown>
  org_id?: string
  is_active?: boolean
  is_social?: boolean
  allow_user_creation?: boolean
  default_role?: string
  group_mapping?: Record<string, string>
}

export interface SSOProviderUpdate {
  name?: string
  config?: Record<string, unknown>
  is_active?: boolean
  allow_user_creation?: boolean
  default_role?: string
  group_mapping?: Record<string, string>
}

export interface SSOLoginInitResponse {
  provider_id: string
  provider_type: string
  provider_name: string
  redirect_url: string
  state: string | null
}

export interface ActiveProvider {
  id: string
  name: string
  provider_type: string
  is_social: boolean
}

export interface SSOTestResponse {
  success: boolean
  message: string
  details?: Record<string, unknown>
}

interface LDAPLoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface SSOProviderHealthResponse {
  provider_id: string
  name: string
  success_count: number
  failure_count: number
  last_success_at: string | null
  health_status: 'healthy' | 'warning' | 'error' | 'unknown'
}

// =============================================================================
// Composable
// =============================================================================

export function useSsoApi() {
  const authStore = useAuthStore()

  // The canonical client skips its session-clearing 401 handler for `/auth/**`
  // endpoints, so the SSO login-flow methods below preserve the historic
  // interceptor behavior (logout on any 401) explicitly and re-throw as before.
  async function withAuthGuard<T>(op: () => Promise<T>): Promise<T> {
    try {
      return await op()
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('HTTP 401')) {
        authStore.logout()
      }
      throw error
    }
  }

  // ===========================================================================
  // SSO Provider CRUD (non-auth endpoints — client handles 401 centrally)
  // ===========================================================================

  async function listProviders(
    orgId?: string,
    activeOnly?: boolean
  ): Promise<SSOProviderListResponse> {
    const params = new URLSearchParams()
    if (orgId) params.set('org_id', orgId)
    if (activeOnly !== undefined) params.set('active_only', String(activeOnly))
    const query = params.toString()
    return slmApiClient.get<SSOProviderListResponse>(
      query ? `/sso-providers?${query}` : '/sso-providers'
    )
  }

  async function createProvider(
    data: SSOProviderCreate
  ): Promise<SSOProviderResponse> {
    return slmApiClient.post<SSOProviderResponse>('/sso-providers', data)
  }

  async function getProvider(
    providerId: string
  ): Promise<SSOProviderResponse> {
    return slmApiClient.get<SSOProviderResponse>(`/sso-providers/${providerId}`)
  }

  async function updateProvider(
    providerId: string,
    data: SSOProviderUpdate
  ): Promise<SSOProviderResponse> {
    return slmApiClient.patch<SSOProviderResponse>(
      `/sso-providers/${providerId}`,
      data
    )
  }

  async function deleteProvider(providerId: string): Promise<void> {
    await slmApiClient.delete(`/sso-providers/${providerId}`)
  }

  async function testProvider(
    providerId: string
  ): Promise<SSOTestResponse> {
    return slmApiClient.get<SSOTestResponse>(
      `/sso-providers/${providerId}/test`
    )
  }

  // ===========================================================================
  // SSO Login Flow (`/auth/**` — client skips 401, guard preserves logout)
  // ===========================================================================

  async function getActiveProviders(): Promise<ActiveProvider[]> {
    return withAuthGuard(() =>
      slmApiClient.get<ActiveProvider[]>('/auth/sso/providers')
    )
  }

  async function initiateSSOLogin(
    providerId: string
  ): Promise<SSOLoginInitResponse> {
    return withAuthGuard(() =>
      slmApiClient.get<SSOLoginInitResponse>(`/auth/sso/${providerId}/login`)
    )
  }

  async function loginWithLDAP(
    providerId: string,
    username: string,
    password: string
  ): Promise<LDAPLoginResponse> {
    return withAuthGuard(() =>
      slmApiClient.post<LDAPLoginResponse>('/auth/sso/ldap/login', {
        provider_id: providerId,
        username,
        password,
      })
    )
  }

  async function getProvidersHealth(): Promise<SSOProviderHealthResponse[]> {
    return slmApiClient.get<SSOProviderHealthResponse[]>(
      '/sso-providers/health'
    )
  }

  return {
    // Provider CRUD
    listProviders,
    createProvider,
    getProvider,
    updateProvider,
    deleteProvider,
    testProvider,
    // Login flow
    getActiveProviders,
    initiateSSOLogin,
    loginWithLDAP,
    // Health dashboard
    getProvidersHealth,
  }
}
