// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { createAutobotBackendClient } from '@/composables/useAutobotApi'
import type { AgentOrgStatusList, AgentsAvailableData, AgentsStatusData } from '@/types/agents'

/** Read routes behind the SLM Tools -> Agents tab (#22141). Unwraps the DataResponse envelope. */
export function useAgentsApi() {
  const client = createAutobotBackendClient()

  async function getAvailableAgents(): Promise<AgentsAvailableData> {
    return (await client.get<{ data: AgentsAvailableData }>('/agent/agents/available')).data
  }

  async function getAgentsStatus(): Promise<AgentsStatusData> {
    return (await client.get<{ data: AgentsStatusData }>('/agent/agents/status')).data
  }

  // agent_org status items: per-agent tasksCompleted / successRate, null when unmeasured (#17514)
  async function getAgentOrgStatus(): Promise<AgentOrgStatusList> {
    return client.get<AgentOrgStatusList>('/agents/status')
  }

  return { getAvailableAgents, getAgentsStatus, getAgentOrgStatus }
}
