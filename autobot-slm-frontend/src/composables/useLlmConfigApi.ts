// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * LLM Config API Composable (#2371)
 *
 * Provides REST API integration for LLM provider configuration
 * management via the SLM backend. Admin-only.
 */

import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getSlmApiBase } from '@/config/ssot-config'

const SLM_API_BASE = getSlmApiBase()

export interface LLMProviderConfig {
  name: string
  enabled: boolean
  api_key: string
  endpoint: string
  model: string
  temperature: number
  max_tokens: number
}

export interface LLMConfig {
  active_provider: string
  providers: LLMProviderConfig[]
  ollama_host: string
  ollama_port: number
  gpu_models: string[]
  cpu_models: string[]
  max_loaded_models: number
  num_parallel: number
  keep_alive: string
  flash_attention: boolean
  kv_cache_type: string
}

export interface LLMConfigResponse {
  config: LLMConfig
  message: string
}

export interface LLMTestRequest {
  provider: string
  endpoint?: string
  api_key?: string
  model?: string
}

export interface LLMTestResponse {
  success: boolean
  message: string
  provider: string
  latency_ms: number | null
}

export interface LLMApplyResponse {
  success: boolean
  message: string
  node_count: number
  output: string | null
}

export function useLlmConfigApi() {
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

  async function getConfig(): Promise<LLMConfigResponse> {
    const response = await client.get<LLMConfigResponse>('/settings/admin/llm')
    return response.data
  }

  async function saveConfig(config: LLMConfig): Promise<LLMConfigResponse> {
    const response = await client.put<LLMConfigResponse>(
      '/settings/admin/llm',
      config
    )
    return response.data
  }

  async function testConnection(
    request: LLMTestRequest
  ): Promise<LLMTestResponse> {
    const response = await client.post<LLMTestResponse>(
      '/settings/admin/llm/test',
      request
    )
    return response.data
  }

  async function applyToFleet(
    nodeIds?: string[]
  ): Promise<LLMApplyResponse> {
    const response = await client.post<LLMApplyResponse>(
      '/settings/admin/llm/apply',
      { node_ids: nodeIds || null }
    )
    return response.data
  }

  return {
    getConfig,
    saveConfig,
    testConnection,
    applyToFleet,
  }
}
