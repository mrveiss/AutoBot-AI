// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The teams of the company shown by TeamsView (#18245, mockup Teams).
 *
 * Reads `GET /api/llc/companies/{id}/teams` (company-scoped by path, #13938) and the company's members
 * for names: teams carry user ids only. Writes go to the company-scoped routes under
 * `/api/llc/companies/{id}/teams` (#14106): the company is the path, there is no organisation header.
 * The server decides who may write (owners and admins of that company) and answers 403 otherwise; the
 * response carries no "may manage" fact, so the controls are shown and a refusal is reported, never
 * guessed from a role here.
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
  post<T>(url: string, data?: unknown): Promise<T>
  delete<T>(url: string): Promise<T>
}

const statusOf = (err: unknown): number | undefined => (err as { status?: number })?.status

/** The people a team can still take: active company members who are not on it. */
export function candidatesFor(team: CompanyTeam, members: readonly Member[]): Member[] {
  const on = new Set(team.member_user_ids)
  return members.filter((m) => !on.has(m.user_id) && m.is_active !== false)
}

export function useCompanyTeams(api: TeamsApi, companyId: () => string) {
  const { t } = useI18n()
  const teams = ref<CompanyTeam[]>([])
  const members = ref<Member[]>([])
  const state = ref<TeamsState>('loading')
  const membersFailed = ref(false)
  // True while the members read is in flight: the teams show first, member names wait (#20816).
  const membersPending = ref(false)
  const errorMessage = ref('')
  const pending = ref(false)
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
    // The members read is not awaited: teams render as soon as their own read answers, and the
    // names fill in when the members arrive (a slow or never-answering read must not hide the teams).
    // A reload after the names are known keeps them; only the first read shows them pending.
    if (members.value.length === 0) membersPending.value = true
    void (api.get(`/api/llc/companies/${id}/members`) as Promise<Member[]>).then(
      (list) => {
        if (!current()) return
        membersFailed.value = false
        members.value = Array.isArray(list) ? list : []
        membersPending.value = false
      },
      () => {
        if (!current()) return
        membersFailed.value = true
        members.value = []
        membersPending.value = false
      },
    )
    const teamsResult = await Promise.allSettled([api.get(`/api/llc/companies/${id}/teams`) as Promise<CompanyTeamsResponse>]).then((r) => r[0])
    if (!current()) return
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

  function writeMessage(err: unknown, failKey: string, conflictKey?: string): string {
    const status = statusOf(err)
    if (status === 403) return t('llcTeams.forbidden')
    if (status === 409 && conflictKey) return t(conflictKey)
    return t(failKey)
  }

  /** Run one write for the company shown, then re-read; false when the server refused it. */
  async function write(action: (id: string) => Promise<unknown>, failKey: string, conflictKey?: string): Promise<boolean> {
    const id = companyId()
    const mine = generation
    pending.value = true
    errorMessage.value = ''
    try {
      await action(id)
      if (mine === generation) await load()
      return true
    } catch (err) {
      logger.error('Team write failed', err)
      if (mine === generation) errorMessage.value = writeMessage(err, failKey, conflictKey)
      return false
    } finally {
      if (mine === generation) pending.value = false
    }
  }

  const teamsUrl = (id: string) => `/api/llc/companies/${id}/teams`
  const createTeam = (name: string) =>
    write((id) => api.post(teamsUrl(id), { name: name.trim() }), 'llcTeams.createError', 'llcTeams.duplicateName')
  const deleteTeam = (team: CompanyTeam) =>
    write((id) => api.delete(`${teamsUrl(id)}/${team.id}`), 'llcTeams.deleteError')
  const addMember = (team: CompanyTeam, userId: string) =>
    write((id) => api.post(`${teamsUrl(id)}/${team.id}/members/${userId}`), 'llcTeams.addError')
  const removeMember = (team: CompanyTeam, userId: string) =>
    write((id) => api.delete(`${teamsUrl(id)}/${team.id}/members/${userId}`), 'llcTeams.removeError')

  // Another company: drop what was shown and read again; late answers for the old one are discarded.
  watch(companyId, () => {
    generation++
    teams.value = []
    members.value = []
    membersFailed.value = false
    membersPending.value = false
    errorMessage.value = ''
    pending.value = false
    state.value = 'loading'
    void load()
  })

  const hasTeams = computed(() => teams.value.length > 0)

  return {
    teams, members, state, membersFailed, membersPending, errorMessage, pending, hasTeams,
    nameOf, isInactive, load, createTeam, deleteTeam, addMember, removeMember,
  }
}
