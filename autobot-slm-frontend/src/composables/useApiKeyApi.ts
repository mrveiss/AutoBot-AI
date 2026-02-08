// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * API Key Management API Composable
 *
 * Provides REST API integration for API key management
 * via the SLM backend.
 * Issue #576 - User Management System Phase 5 (API Keys).
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

const SLM_API_BASE = '/api'

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

  async function createKey(data: APIKeyCreate): Promise<APIKeyCreateResponse> {
    const response = await client.post<APIKeyCreateResponse>(
      '/api-keys',
      data
    )
    return response.data
  }

  async function listKeys(): Promise<APIKeyListResponse> {
    const response = await client.get<APIKeyListResponse>('/api-keys')
    return response.data
  }

  async function getKey(keyId: string): Promise<APIKeyResponse> {
    const response = await client.get<APIKeyResponse>(`/api-keys/${keyId}`)
    return response.data
  }

  async function updateKey(
    keyId: string,
    data: APIKeyUpdate
  ): Promise<APIKeyResponse> {
    const response = await client.patch<APIKeyResponse>(
      `/api-keys/${keyId}`,
      data
    )
    return response.data
  }

  async function revokeKey(keyId: string): Promise<void> {
    await client.delete(`/api-keys/${keyId}`)
  }

  async function getScopes(): Promise<Record<string, string>> {
    const response = await client.get<Record<string, string>>(
      '/api-keys/scopes'
    )
    return response.data
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
