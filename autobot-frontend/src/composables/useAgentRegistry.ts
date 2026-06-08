// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Agent Registry Composable (#1794)
 *
 * Fetches backend (runtime) agents and specialized (definition) agents from
 * the agent_config API, providing reactive state for the Agent Registry view.
 */

import { ref, computed } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useAgentRegistry')

// ===== Type Definitions =====

export interface BackendAgent {
  id: string
  name: string
  description: string
  type: 'backend'
  model: string
  enabled: boolean
  status: 'connected' | 'disconnected'
  priority: number
  tasks: string[]
  mcp_tools: string[]
  invoked_by: string
  source_file: string
  config_source: 'slm' | 'local'
}

export interface SpecializedAgent {
  id: string
  name: string
  description: string
  type: 'specialized'
  model: string | null
  color: string
  tools: string[]
  category: string
  source_file: string
  excerpt: string
  system_prompt?: string
}

export interface AgentSummary {
  total: number
  total_specialized: number
  healthy: number
  disconnected: number
}

export interface UseAgentRegistryOptions {
  autoFetch?: boolean
}

// ===== Composable Implementation =====

export function useAgentRegistry(options: UseAgentRegistryOptions = {}) {
  const { autoFetch = false } = options

  const backendAgents = ref<BackendAgent[]>([])
  const specializedAgents = ref<SpecializedAgent[]>([])
  const summary = ref<AgentSummary | null>(null)
  const selectedAgent = ref<SpecializedAgent | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const { isLoading: isLoadingDetail, wrap: wrapDetail } = useLoadingState()
  const errors = ref<string[]>([])
  const error = computed<string | null>(() =>
    errors.value.length > 0 ? errors.value.join('; ') : null,
  )

  // ----- Computed -----

  const agentCategories = computed(() => {
    const counts: Record<string, number> = {}
    for (const agent of specializedAgents.value) {
      counts[agent.category] = (counts[agent.category] || 0) + 1
    }
    return counts
  })

  const agentsByCategory = computed(() => {
    const grouped: Record<string, SpecializedAgent[]> = {}
    for (const agent of specializedAgents.value) {
      if (!grouped[agent.category]) {
        grouped[agent.category] = []
      }
      grouped[agent.category].push(agent)
    }
    return grouped
  })

  // ----- Actions -----

  async function fetchAllAgents() {
    errors.value = []
    return wrap(async () => {
      try {
        const data = await ApiClient.get<any>(`${getApiBase()}/agent_config/agents/all`)
        backendAgents.value = data.agents || []
        specializedAgents.value = data.specialized_agents || []
        summary.value = data.summary || null
        logger.debug(
          'Fetched %d backend + %d specialized agents',
          backendAgents.value.length,
          specializedAgents.value.length
        )
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        errors.value = [...errors.value, msg]
        logger.error('Failed to fetch agents: %s', msg)
      }
    })
  }

  async function fetchAgentDetail(agentId: string) {
    return wrapDetail(async () => {
      try {
        const data = await ApiClient.get<any>(
          `${getApiBase()}/agent_config/agents/specialized/${agentId}`
        )
        selectedAgent.value = data
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        logger.error('Failed to fetch specialized agent %s: %s', agentId, msg)
        selectedAgent.value = null
      }
    })
  }

  if (autoFetch) {
    fetchAllAgents()
  }

  return {
    backendAgents,
    specializedAgents,
    summary,
    selectedAgent,
    agentCategories,
    agentsByCategory,
    isLoading,
    isLoadingDetail,
    error,
    fetchAllAgents,
    fetchAgentDetail,
  }
}
