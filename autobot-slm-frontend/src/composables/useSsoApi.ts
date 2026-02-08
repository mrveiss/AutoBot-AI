// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * SSO Provider Management API Composable
 *
 * Provides REST API integration for SSO/OAuth2/LDAP/SAML provider
 * management via the SLM backend.
 * Issue #576 - User Management System Phase 4 (SSO).
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

// SLM API is proxied via nginx at /api/
const SLM_API_BASE = '/api'

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

// =============================================================================
// Composable
// =============================================================================

export function useSsoApi() {
  const authStore = useAuthStore()

  const client: AxiosInstance = axios.create({
    baseURL: SLM_API_BASE,
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
  })

  client.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        authStore.logout()
      }
      return Promise.reject(error)
    }
  )

  // ===========================================================================
  // SSO Provider CRUD
  // ===========================================================================

  async function listProviders(
    orgId?: string,
    activeOnly?: boolean
  ): Promise<SSOProviderListResponse> {
    const params: Record<string, string | boolean> = {}
    if (orgId) params.org_id = orgId
    if (activeOnly !== undefined) params.active_only = activeOnly
    const response = await client.get<SSOProviderListResponse>(
      '/sso/providers',
      { params }
    )
    return response.data
  }

  async function createProvider(
    data: SSOProviderCreate
  ): Promise<SSOProviderResponse> {
    const response = await client.post<SSOProviderResponse>(
      '/sso/providers',
      data
    )
    return response.data
  }

  async function getProvider(
    providerId: string
  ): Promise<SSOProviderResponse> {
    const response = await client.get<SSOProviderResponse>(
      `/sso/providers/${providerId}`
    )
    return response.data
  }

  async function updateProvider(
    providerId: string,
    data: SSOProviderUpdate
  ): Promise<SSOProviderResponse> {
    const response = await client.patch<SSOProviderResponse>(
      `/sso/providers/${providerId}`,
      data
    )
    return response.data
  }

  async function deleteProvider(providerId: string): Promise<void> {
    await client.delete(`/sso/providers/${providerId}`)
  }

  async function testProvider(
    providerId: string
  ): Promise<SSOTestResponse> {
    const response = await client.post<SSOTestResponse>(
      `/sso/providers/${providerId}/test`
    )
    return response.data
  }

  // ===========================================================================
  // SSO Login Flow
  // ===========================================================================

  async function getActiveProviders(): Promise<ActiveProvider[]> {
    const response = await client.get<ActiveProvider[]>(
      '/sso/providers/active'
    )
    return response.data
  }

  async function initiateSSOLogin(
    providerId: string
  ): Promise<SSOLoginInitResponse> {
    const response = await client.post<SSOLoginInitResponse>(
      `/sso/login/${providerId}/initiate`
    )
    return response.data
  }

  async function loginWithLDAP(
    providerId: string,
    username: string,
    password: string
  ): Promise<LDAPLoginResponse> {
    const response = await client.post<LDAPLoginResponse>(
      `/sso/login/${providerId}/ldap`,
      { username, password }
    )
    return response.data
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
  }
}
