// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * External Agent Registry Composable (Issue #963)
 *
 * Provides API integration for managing external A2A-compliant agents.
 */

import { ref, reactive } from 'vue'
import { makeAxiosCompatClient } from '@/utils/slmApiCompat'
import type {
  ExternalAgent,
  ExternalAgentCreate,
  ExternalAgentUpdate,
  ExternalAgentCard,
} from '@/types/slm'

// SLM backend transport: the canonical `slmApiClient` behind the axios-shaped
// facade (#13079/#13140). This composable used to hold its own bare
// `axios.create()` — no baseURL (every call site pasted `getSlmApiBase()` in),
// NO timeout at all, a `sessionStorage`-only bearer interceptor and no 401
// handling. `slmApiClient` supplies the sessionStorage->localStorage token
// fallback (ApiClient.ts:113), the `VITE_SLM_API_TIMEOUT_MS` budget (:44-48)
// and the 401 session teardown (:128-151), and resolves the base URL itself
// (:104) — so the endpoints below are relative.
const client = makeAxiosCompatClient()

export function useExternalAgents() {
  const agents = ref<ExternalAgent[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  function _extractError(e: unknown, fallback: string): string {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    return err.response?.data?.detail || err.message || fallback
  }

  async function fetchAgents(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const response = await client.get<ExternalAgent[]>('/external-agents')
      agents.value = response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to fetch external agents')
    } finally {
      isLoading.value = false
    }
  }

  async function getAgent(agentId: number): Promise<ExternalAgent | null> {
    try {
      const response = await client.get<ExternalAgent>(`/external-agents/${agentId}`)
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to fetch agent')
      return null
    }
  }

  async function createAgent(data: ExternalAgentCreate): Promise<ExternalAgent | null> {
    try {
      const response = await client.post<ExternalAgent>('/external-agents', data)
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to register agent')
      return null
    }
  }

  async function updateAgent(
    agentId: number,
    data: ExternalAgentUpdate
  ): Promise<ExternalAgent | null> {
    try {
      const response = await client.put<ExternalAgent>(`/external-agents/${agentId}`, data)
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to update agent')
      return null
    }
  }

  async function deleteAgent(agentId: number): Promise<boolean> {
    try {
      await client.delete(`/external-agents/${agentId}`)
      agents.value = agents.value.filter((a) => a.id !== agentId)
      return true
    } catch (e) {
      error.value = _extractError(e, 'Failed to delete agent')
      return false
    }
  }

  async function verifyAgent(agentId: number): Promise<ExternalAgent | null> {
    try {
      const response = await client.post<ExternalAgent & { success: boolean }>(
        `/external-agents/${agentId}/verify`
      )
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to verify agent')
      return null
    }
  }

  async function refreshAgentCard(agentId: number): Promise<boolean> {
    try {
      await client.post(`/external-agents/${agentId}/refresh`)
      return true
    } catch (e) {
      error.value = _extractError(e, 'Failed to queue card refresh')
      return false
    }
  }

  async function fetchCards(): Promise<ExternalAgentCard[]> {
    try {
      const response = await client.get<ExternalAgentCard[]>('/external-agents/cards')
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to fetch agent cards')
      return []
    }
  }

  return reactive({
    agents,
    isLoading,
    error,
    fetchAgents,
    getAgent,
    createAgent,
    updateAgent,
    deleteAgent,
    verifyAgent,
    refreshAgentCard,
    fetchCards,
  })
}
