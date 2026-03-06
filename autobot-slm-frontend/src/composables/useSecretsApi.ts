// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * System Secrets API Composable (#1417)
 *
 * Provides REST API integration for encrypted system secrets
 * management via the SLM backend. Admin-only.
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'

const SLM_API_BASE = '/api'

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

export function useSecretsApi() {
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

  async function listSecrets(): Promise<SecretResponse[]> {
    const response = await client.get<SecretResponse[]>('/secrets')
    return response.data
  }

  async function createSecret(data: SecretCreate): Promise<SecretResponse> {
    const response = await client.post<SecretResponse>('/secrets', data)
    return response.data
  }

  async function updateSecret(
    key: string,
    data: SecretUpdate
  ): Promise<SecretResponse> {
    const response = await client.put<SecretResponse>(
      `/secrets/${encodeURIComponent(key)}`,
      data
    )
    return response.data
  }

  async function deleteSecret(key: string): Promise<void> {
    await client.delete(`/secrets/${encodeURIComponent(key)}`)
  }

  return {
    listSecrets,
    createSecret,
    updateSecret,
    deleteSecret,
  }
}
