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
  available_agents: Array<{ name: string; type: string; status: string; provider: string; parameters: string }>
}
