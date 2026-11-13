// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The two sources the org chart's People list and canvas teams need beyond the org chart itself
 * (GH#13938, #14596): the company's contacts and its teams. Extracted from OrgChart.vue (#21469).
 *
 * Each source is independent: a company with no contacts must still get its teams, and a teams
 * endpoint failure must not blank the people. `Promise.allSettled` keeps a partial answer partial
 * instead of turning it into an empty list.
 *
 * The company resolution is a third thing that can fail. It ends in the same failed state as the two
 * sources (never "no people"), the in-flight guard is released on every exit, and nothing is cached
 * as loaded, so the next call retries.
 */
import { ref } from 'vue'
import type { CompanyTeam, ContactSource } from '@/composables/llc/orgPeople'
import { planRequest, type PlanResponse } from '@/composables/llc/workflowPlanRequest'
import type { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useOrgPeopleSources')

// Both routes are read through the generated contract (#13998, #13938), not a hand-declared shape.
const INVOLVED = '/api/llc/contacts/{company_id}/involved'
const TEAMS = '/api/llc/companies/{company_id}/teams'

export type PeopleSourcesApi = ReturnType<typeof useApiClient>

export interface OrgPeopleSourcesDeps {
  api: PeopleSourcesApi
  /** Resolve the active company; '' (or nothing) when there is none. May reject. */
  resolveCompanyId: () => Promise<string | null | undefined>
  /** The company the view operates on now, to tell a switched company from the one asked about. */
  companyId: () => string
}

export function useOrgPeopleSources(deps: OrgPeopleSourcesDeps) {
  // GH#13938: contacts and teams are fetched only when the People list is first
  // opened. The org chart's own mount stays a single request, and a terminate
  // reload keeps reloading exactly the hierarchy it changed.
  const contacts = ref<ContactSource[]>([])
  // #13998: ids of contacts this department carries with no role to explain them.
  // Kept separate from `contacts` so the list the org chart builds stays one
  // list, while the People view can still label the difference honestly.
  const unassignedContactIds = ref<Set<string>>(new Set())
  const teams = ref<CompanyTeam[]>([])
  const loaded = ref(false)
  // A source that did not answer — kept apart from a source that answered
  // "nothing", so the list never states a fact it does not know (#14064).
  const contactsFailed = ref(false)
  const teamsFailed = ref(false)
  // #14596: distinguishes "the teams request has not answered yet" from "it
  // answered with zero teams" — `teams.value` is `[]` in both cases, and the
  // canvas must never say "this company has no teams" before the request that
  // would prove it has actually completed (#14064's failure shape).
  const teamsAttempted = ref(false)
  const loading = ref(false)

  function applyContacts(result: PromiseSettledResult<PlanResponse<typeof INVOLVED, 'get'>>): void {
    if (result.status === 'rejected') {
      // A failed fetch must never be reported as "this company has no people".
      // Absence of data and absence of an answer are different claims (#14064).
      contactsFailed.value = true
      logger.error('Failed to fetch contacts:', result.reason)
      return
    }
    // Two groups, one list to draw: people whose presence a role explains, and
    // people the department carries from before the directory was shared.
    // Merging them here would assert an involvement nobody recorded, so the
    // second group is tracked by id and labelled rather than blended in.
    const body = result.value
    const withRole: ContactSource[] = Array.isArray(body?.with_role) ? body.with_role : []
    const unassigned: ContactSource[] = Array.isArray(body?.unassigned) ? body.unassigned : []
    contacts.value = [...withRole, ...unassigned]
    unassignedContactIds.value = new Set(unassigned.map((c) => c.id))
    contactsFailed.value = false
  }

  function applyTeams(result: PromiseSettledResult<PlanResponse<typeof TEAMS, 'get'>>): void {
    if (result.status === 'rejected') {
      teamsFailed.value = true
      logger.error('Failed to fetch company teams:', result.reason)
      return
    }
    const body = result.value
    const list: CompanyTeam[] = Array.isArray(body?.teams) ? body.teams : []
    teams.value = list
    teamsFailed.value = false
  }

  async function fetchSources(cid: string): Promise<void> {
    const [contactsResult, teamsResult] = await Promise.allSettled([
      planRequest(deps.api, 'get', INVOLVED, { company_id: cid }),
      planRequest(deps.api, 'get', TEAMS, { company_id: cid }),
    ])
    // A switched company owns the state now; its answer is not this one's.
    if (deps.companyId() && cid !== deps.companyId()) return
    applyContacts(contactsResult)
    applyTeams(teamsResult)
    teamsAttempted.value = true
    // Only a complete answer is cached; a partial one retries on re-entry.
    loaded.value = !contactsFailed.value && !teamsFailed.value
  }

  async function load(): Promise<void> {
    if (loaded.value || loading.value) return
    // Claim the guard BEFORE the first await: two clicks in one tick would both
    // pass the check above and double-fire every request.
    loading.value = true
    try {
      // The resolver is awaited directly, with no async wrapper around it: a wrapper adds a microtask
      // hop, which moves the two requests past the point a caller that snapshots right after the
      // fire-and-forget entry (the role lens spec) counts them from.
      const cid = await deps.resolveCompanyId()
      if (cid) await fetchSources(cid)
    } catch (err: unknown) {
      // A rejected company resolution is not "no company", and a throw from the api or the apply step
      // is not "no people": each ends in the same visible failed state, never an unhandled rejection
      // at the fire-and-forget call sites.
      logger.error('Failed to load the people sources:', err)
      contactsFailed.value = true
      teamsFailed.value = true
      teamsAttempted.value = true
    } finally {
      loading.value = false
    }
  }

  /**
   * Force the sources to actually re-fetch (#14603) — mirrors
   * `reloadProcessNodes`/`reloadToolNodes`. `loaded` guards the lazy
   * fetch above, so a contact save has to clear it first or the "refetch"
   * would hit the guard and silently keep showing the pre-edit row.
   */
  async function reload(): Promise<void> {
    loaded.value = false
    await load()
  }

  return {
    contacts,
    unassignedContactIds,
    teams,
    contactsFailed,
    teamsFailed,
    teamsAttempted,
    loading,
    load,
    reload,
  }
}
