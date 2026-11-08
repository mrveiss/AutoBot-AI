// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#10531/#10532/#10534: shared source of a company's "people" for the
// assignee / reviewer / handoff pickers — AI agents (org chart) and human
// members. Agents expose `id` = AgentOrgNode UUID PK (the assignment keyspace,
// #10032), NOT the logical slug.
import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import type { MembersResponse } from '@/composables/llc/useCompanyMembers'
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

/**
 * Members who are still members but can no longer be given work (#13956) —
 * deactivated, or soft-deleted while their membership row remains.
 *
 * Reported separately rather than dropped on the floor. These pickers choose an
 * assignment *target*, so an inactive person must not be selectable; but a
 * surface that shows a shorter list with no explanation invites the reading
 * that those people are gone from the company, which is a different claim. A
 * picker can state the count; the org chart still shows the people themselves.
 */
export interface InactiveMember {
  user_id: string
  name: string
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
  const inactiveHumans = ref<InactiveMember[]>([])
  const isLoading = ref(false)
  // #20542: the server's verdict on the owner/admin writes, read off the members response this load already makes.
  const viewerCanManage = ref(false)
  // #15945: an empty list after a failed load is not an empty company; a picker must tell them apart.
  const loadFailed = ref(false)

  async function load(): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    loadFailed.value = false
    try {
      const [org, members] = await Promise.all([
        api.get<{ nodes: OrgNode[] }>(`/api/llc/companies/${companyId}/org-chart`),
        api.get<MembersResponse>(`/api/llc/companies/${companyId}/members`),
      ])
      const flat: AgentOption[] = []
      flattenAgents(org?.nodes ?? [], flat)
      agents.value = flat
      // #14939: `display_name` is never null -- `list_members` resolves the whole ladder server-side.
      // #21096: the verdict is the response's own, so a company with no rows still carries it.
      const rows = members?.members ?? []
      viewerCanManage.value = members?.viewer_can_manage === true
      // `is_active !== false` rather than a truthy test: a server that predates
      // this field omits it, and treating "absent" as inactive would empty
      // every picker during a rolling update.
      humans.value = rows
        .filter((m) => m.is_active !== false)
        .map((m) => ({
          user_id: m.user_id,
          name: m.display_name,
          role: m.role,
        }))
      inactiveHumans.value = rows
        .filter((m) => m.is_active === false)
        .map((m) => ({ user_id: m.user_id, name: m.display_name }))
    } catch (err) {
      logger.error('Failed to load company people', err)
      agents.value = []
      humans.value = []
      inactiveHumans.value = []
      viewerCanManage.value = false
      loadFailed.value = true
    } finally {
      isLoading.value = false
    }
  }

  return { agents, humans, inactiveHumans, viewerCanManage, isLoading, loadFailed, load }
}
