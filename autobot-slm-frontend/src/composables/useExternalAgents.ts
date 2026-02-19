// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * External Agent Registry Composable (Issue #963)
 *
 * Provides API integration for managing external A2A-compliant agents.
 */

import { ref, reactive } from 'vue'
import axios from 'axios'
import type {
  ExternalAgent,
  ExternalAgentCreate,
  ExternalAgentUpdate,
  ExternalAgentCard,
} from '@/types/slm'

const API_BASE = ''

function makeClient() {
  const client = axios.create({ baseURL: API_BASE })
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })
  return client
}

export function useExternalAgents() {
  const agents = ref<ExternalAgent[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const client = makeClient()

  function _extractError(e: unknown, fallback: string): string {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    return err.response?.data?.detail || err.message || fallback
  }

  async function fetchAgents(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const response = await client.get<ExternalAgent[]>('/api/external-agents')
      agents.value = response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to fetch external agents')
    } finally {
      isLoading.value = false
    }
  }

  async function getAgent(agentId: number): Promise<ExternalAgent | null> {
    try {
      const response = await client.get<ExternalAgent>(`/api/external-agents/${agentId}`)
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to fetch agent')
      return null
    }
  }

  async function createAgent(data: ExternalAgentCreate): Promise<ExternalAgent | null> {
    try {
      const response = await client.post<ExternalAgent>('/api/external-agents', data)
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
      const response = await client.put<ExternalAgent>(`/api/external-agents/${agentId}`, data)
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to update agent')
      return null
    }
  }

  async function deleteAgent(agentId: number): Promise<boolean> {
    try {
      await client.delete(`/api/external-agents/${agentId}`)
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
        `/api/external-agents/${agentId}/verify`
      )
      return response.data
    } catch (e) {
      error.value = _extractError(e, 'Failed to verify agent')
      return null
    }
  }

  async function refreshAgentCard(agentId: number): Promise<boolean> {
    try {
      await client.post(`/api/external-agents/${agentId}/refresh`)
      return true
    } catch (e) {
      error.value = _extractError(e, 'Failed to queue card refresh')
      return false
    }
  }

  async function fetchCards(): Promise<ExternalAgentCard[]> {
    try {
      const response = await client.get<ExternalAgentCard[]>('/api/external-agents/cards')
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
