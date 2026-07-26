// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * LLM Config API Composable (#2371)
 *
 * Provides REST API integration for LLM provider configuration
 * management via the SLM backend. Admin-only.
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
  async function getConfig(): Promise<LLMConfigResponse> {
    return slmApiClient.get<LLMConfigResponse>('/settings/admin/llm')
  }

  async function saveConfig(config: LLMConfig): Promise<LLMConfigResponse> {
    return slmApiClient.put<LLMConfigResponse>('/settings/admin/llm', config)
  }

  async function testConnection(
    request: LLMTestRequest
  ): Promise<LLMTestResponse> {
    return slmApiClient.post<LLMTestResponse>('/settings/admin/llm/test', request)
  }

  async function applyToFleet(nodeIds?: string[]): Promise<LLMApplyResponse> {
    return slmApiClient.post<LLMApplyResponse>('/settings/admin/llm/apply', {
      node_ids: nodeIds || null,
    })
  }

  return {
    getConfig,
    saveConfig,
    testConnection,
    applyToFleet,
  }
}
