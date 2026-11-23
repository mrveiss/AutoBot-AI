// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #22141: the typed agent shape of GET /agent/agents/available and /agent/agents/status
export interface AvailableAgent {
  name: string
  description: string
  capabilities: string[]
  status: string
}

export interface AgentsAvailableData {
  total_agents: number
  agents: AvailableAgent[]
}

export interface AgentsStatusData {
  ai_stack_status: string
  total_agents: number
  available_agents: Array<{ name: string; type: string; status: string | null; provider: string; parameters: string }>
}

// GET /agents/status (agent_org): per-agent runtime stats; null = unmeasured (#17514), never 0
export interface AgentOrgStatusItem {
  id: string
  name: string
  type: string
  status: string | null
  tasksCompleted: number | null
  successRate: number | null
}

export interface AgentOrgStatusList {
  agents: AgentOrgStatusItem[]
  total: number
}
