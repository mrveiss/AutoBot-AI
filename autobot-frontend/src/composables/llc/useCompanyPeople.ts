// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#10531/#10532/#10534: shared source of a company's "people" for the
// assignee / reviewer / handoff pickers — AI agents (org chart) and human
// members. Agents expose `id` = AgentOrgNode UUID PK (the assignment keyspace,
// #10032), NOT the logical slug.
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyPeople')

export interface AgentOption {
  id: string // AgentOrgNode UUID PK — assignee_agent_id / target_agent_id
  name: string
}
export interface HumanOption {
  user_id: string
  name: string
  role: string
}

interface OrgNode {
  node_id: string
  name: string
  is_human: boolean
  children?: OrgNode[]
}

function flattenAgents(nodes: OrgNode[], out: AgentOption[]): void {
  for (const n of nodes) {
    if (!n.is_human) out.push({ id: n.node_id, name: n.name })
    if (n.children?.length) flattenAgents(n.children, out)
  }
}

export function useCompanyPeople(companyId: string) {
  const agents = ref<AgentOption[]>([])
  const humans = ref<HumanOption[]>([])
  const isLoading = ref(false)

  async function load(): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    try {
      const [org, members] = await Promise.all([
        api.get<{ nodes: OrgNode[] }>(`/api/llc/companies/${companyId}/org-chart`),
        api.get<{ user_id: string; display_name: string | null; role: string }[]>(
          `/api/llc/companies/${companyId}/members`,
        ),
      ])
      const flat: AgentOption[] = []
      flattenAgents(org?.nodes ?? [], flat)
      agents.value = flat
      humans.value = (members ?? []).map((m) => ({
        user_id: m.user_id,
        name: m.display_name || m.user_id,
        role: m.role,
      }))
    } catch (err) {
      logger.error('Failed to load company people', err)
      agents.value = []
      humans.value = []
    } finally {
      isLoading.value = false
    }
  }

  return { agents, humans, isLoading, load }
}
