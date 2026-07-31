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
 *
 * Contract types (#12420 Phase 3): the request/response shapes below are DERIVED
 * from the generated OpenAPI schema (`@/types/generated/api`), which is produced
 * from the SLM backend's own Pydantic models and CI-guarded by
 * `verify-generated-types-slm`. Do not hand-declare them — a backend schema
 * change must surface here as a type error, not as a silent runtime mismatch.
 */

import slmApiClient from '@/utils/ApiClient'
import { useAuthStore } from '@/stores/auth'
import { createAuthGuard } from '@/utils/slmAuthGuard'
import type { components } from '@/types/generated/api'

// =============================================================================
// Type Definitions — derived from the generated OpenAPI contract
// =============================================================================

export type SSOProviderResponse = components['schemas']['SSOProviderResponse']
export type SSOProviderListResponse = components['schemas']['SSOProviderListResponse']
export type SSOProviderCreate = components['schemas']['SSOProviderCreate']
export type SSOProviderUpdate = components['schemas']['SSOProviderUpdate']
export type SSOLoginInitResponse = components['schemas']['SSOLoginInitResponse']
export type SSOTestResponse = components['schemas']['SSOTestResponse']
export type SSOProviderHealthResponse = components['schemas']['SSOProviderHealthResponse']
export type LDAPLoginRequest = components['schemas']['LDAPLoginRequest']

/**
 * `GET /auth/sso/providers` and `POST /auth/sso/ldap/login` declare no
 * response_model on the backend, so there is no generated schema to derive from
 * — these two shapes stay hand-declared until the backend types the endpoints.
 */
export interface ActiveProvider {
  id: string
  name: string
  provider_type: string
  is_social: boolean
}

interface LDAPLoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

// =============================================================================
// Composable
// =============================================================================

export function useSsoApi() {
  const authStore = useAuthStore()

  // Preserve the historic "logout on 401" behaviour: the canonical client skips
  // its session-clearing 401 handler for /auth/** endpoints, so the SSO
  // login-flow methods re-apply it explicitly (shared helper — utils/slmAuthGuard.ts).
  const withAuthGuard = createAuthGuard(authStore.logout)

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
    const body: LDAPLoginRequest = {
      provider_id: providerId,
      username,
      password,
    }
    return withAuthGuard(() =>
      slmApiClient.post<LDAPLoginResponse>('/auth/sso/ldap/login', body)
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
