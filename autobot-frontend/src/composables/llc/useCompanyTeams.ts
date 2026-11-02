// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The teams of the company shown by TeamsView (#18245, mockup Teams).
 *
 * Reads `GET /api/llc/companies/{id}/teams` (company-scoped by path, #13938) and the company's members
 * for names: teams carry user ids only. Reading only: writing a team waits for the company-scoped write
 * routes (#14106).
 *
 * The view is not remounted when the route moves to another company, so everything is scoped to the
 * company a request was sent for: the id is captured at send time, a change of company drops the rows,
 * and a response for a company no longer shown is discarded.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { components } from '@/types/generated/api'
import { createLogger } from '@/utils/debugUtils'
import type { Member as CompanyMember } from '@/composables/llc/useCompanyMembers'

const logger = createLogger('useCompanyTeams')

/** A company member row; `is_active` is whether they may still be given work (#13956). */
export type Member = CompanyMember & { is_active?: boolean }
export type CompanyTeam = components['schemas']['CompanyTeam']
type CompanyTeamsResponse = components['schemas']['CompanyTeamsResponse']

/** loading: no answer yet. failed: the read errored (retry may work). unavailable: refused for this company. */
export type TeamsState = 'loading' | 'ready' | 'failed' | 'unavailable'

export interface TeamsApi {
  get<T>(url: string): Promise<T>
}

const statusOf = (err: unknown): number | undefined => (err as { status?: number })?.status

export function useCompanyTeams(api: TeamsApi, companyId: () => string) {
  const { t } = useI18n()
  const teams = ref<CompanyTeam[]>([])
  const members = ref<Member[]>([])
  const state = ref<TeamsState>('loading')
  const membersFailed = ref(false)
  // Bumped when the company changes: a response captured under an older generation is discarded.
  let generation = 0
  // Counts loads: of overlapping reloads in one company only the newest may land.
  let loadSeq = 0

  const nameOf = (userId: string): string => {
    const hit = members.value.find((m) => m.user_id === userId)
    return hit ? hit.display_name : t('llcTeams.unknownMember')
  }
  const isInactive = (userId: string): boolean =>
    members.value.find((m) => m.user_id === userId)?.is_active === false

  async function load(): Promise<void> {
    const id = companyId()
    if (!id) return
    const mine = generation
    const req = ++loadSeq
    const current = () => mine === generation && req === loadSeq
    // A reload keeps the table on screen; only the first load of a company shows the loading state.
    if (teams.value.length === 0) state.value = 'loading'
    const [teamsResult, membersResult] = await Promise.allSettled([
      api.get(`/api/llc/companies/${id}/teams`) as Promise<CompanyTeamsResponse>,
      api.get(`/api/llc/companies/${id}/members`) as Promise<Member[]>,
    ])
    if (!current()) return
    membersFailed.value = membersResult.status === 'rejected'
    members.value = membersResult.status === 'fulfilled' && Array.isArray(membersResult.value) ? membersResult.value : []
    if (teamsResult.status === 'fulfilled') {
      teams.value = Array.isArray(teamsResult.value?.teams) ? teamsResult.value.teams : []
      state.value = 'ready'
      return
    }
    logger.error('Failed to load teams', teamsResult.reason)
    teams.value = []
    const status = statusOf(teamsResult.reason)
    state.value = status === 403 || status === 404 ? 'unavailable' : 'failed'
  }

  // Another company: drop what was shown and read again; late answers for the old one are discarded.
  watch(companyId, () => {
    generation++
    teams.value = []
    members.value = []
    membersFailed.value = false
    state.value = 'loading'
    void load()
  })

  const hasTeams = computed(() => teams.value.length > 0)

  return {
    teams, members, state, membersFailed, hasTeams,
    nameOf, isInactive, load,
  }
}
