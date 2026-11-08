// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The member list of the company shown by MembersView (#19960, #20073).
 *
 * The view is not remounted when the route moves to another company, so everything here is scoped to
 * the company a request was sent for: the company id is captured at send time (the URL and the user id
 * always agree), a change of company drops the rows, and a response that arrives for a company no
 * longer shown is discarded. The server stays the authority on who may change what; the viewer's role
 * and grantable roles it sends are only reflected, to hide what it would refuse.
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { components } from '@/types/generated/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyMembers')

/** The members response: the rows, and the caller's own standing beside them (#21096). */
export type MembersResponse = components['schemas']['CompanyMembersResponse']
type MemberRow = components['schemas']['CompanyMemberRow']

/** A member row. `display_name` is never null: `list_members` resolves the whole ladder server-side (#14939). */
export type Member = Pick<MemberRow, 'user_id' | 'display_name' | 'role'> & Partial<MemberRow>

export interface MembersApi {
  get<T>(url: string): Promise<T>
  patch<T>(url: string, body: unknown): Promise<T>
  delete<T>(url: string): Promise<T>
}

/** Whether a members reply is the envelope (#21096): a legacy bare array, or anything else, is not. */
export function isMembersEnvelope(res: unknown): res is MembersResponse {
  return Array.isArray((res as { members?: unknown } | null | undefined)?.members)
}

/** Whether the viewer may change a member who holds *current*: the server's grantable list decides. */
export function canChangeRole(grantable: readonly string[], current: string): boolean {
  return grantable.length > 0 && (current !== 'owner' || grantable.includes('owner'))
}

/** Whether *role* is a choice the viewer may make for a member who holds *current* (that one stays shown). */
export function canGrantRole(grantable: readonly string[], role: string, current: string): boolean {
  return role === current || grantable.includes(role)
}

function statusOf(err: unknown): number | undefined {
  return (err as { status?: number })?.status
}

/**
 * The roles the add form offers. Before the standing is known (not loaded yet, or the load failed) nothing
 * is granted: the form must not invite a write the server may refuse.
 */
export function rolesToOffer<T extends string>(all: readonly T[], grantable: readonly string[], known: boolean): T[] {
  return known ? all.filter((r) => grantable.includes(r)) : []
}

export function useCompanyMembers(api: MembersApi, companyId: () => string) {
  const { t } = useI18n()
  const members = ref<Member[]>([])
  const grantableRoles = ref<string[]>([])
  // The server's verdict on the owner/admin writes (#20542); it comes with the response, rows or none (#21096).
  const viewerCanManage = ref(false)
  const standingKnown = ref(false)
  const isLoading = ref(false)
  const errorMessage = ref('')
  const pendingUserId = ref<string | null>(null)
  // Bumped when the company changes: a response captured under an older generation is discarded.
  let generation = 0
  // Counts loads: of overlapping reloads in one company only the newest may land.
  let loadSeq = 0

  const base = (id: string) => `/api/llc/companies/${id}/members`

  async function load(): Promise<void> {
    const id = companyId()
    if (!id) return
    const mine = generation
    const req = ++loadSeq
    const current = () => mine === generation && req === loadSeq
    // A reload keeps the table on screen; only the first load of a company shows the loading state.
    isLoading.value = members.value.length === 0
    errorMessage.value = ''
    try {
      const res = await api.get<MembersResponse>(base(id))
      if (!current()) return
      // A reply without the envelope (a backend still on the old array shape) is a failed load.
      if (!isMembersEnvelope(res)) throw new Error('members response is not the envelope')
      members.value = res.members
      grantableRoles.value = res.viewer_grantable_roles
      viewerCanManage.value = res.viewer_can_manage
      standingKnown.value = true
    } catch (err) {
      logger.error('Failed to load members', err)
      if (!current()) return
      errorMessage.value = t('llcMembers.loadError')
      // A failed RELOAD keeps the last rows (stale, controls withheld); a failed first load has none to keep.
      resetStanding(members.value.length > 0)
    } finally {
      if (current()) isLoading.value = false
    }
  }

  function resetStanding(keepRows = false): void {
    if (!keepRows) members.value = []
    grantableRoles.value = []
    viewerCanManage.value = false
    standingKnown.value = false
  }

  function roleChangeMessage(err: unknown): string {
    const status = statusOf(err)
    if (status === 403) return t('llcMembers.roleChangeForbidden')
    if (status === 409) return t('llcMembers.roleChangeLastOwner')
    return t('llcMembers.roleChangeError')
  }

  /** PATCH the role; the row changes only once the server accepts it. False when it did not. */
  async function changeRole(member: Member, newRole: string): Promise<boolean> {
    // Stale rows (the standing is unconfirmed): refuse, whatever the template showed (#21096).
    if (!standingKnown.value) return false
    const id = companyId()
    const mine = generation
    pendingUserId.value = member.user_id
    errorMessage.value = ''
    try {
      await api.patch(`${base(id)}/${member.user_id}`, { role: newRole })
      if (mine !== generation) return false
      const row = members.value.find((m) => m.user_id === member.user_id)
      if (row) row.role = newRole
      // The change may alter the viewer's own standing (an owner demoting themselves): ask again.
      await load()
      return true
    } catch (err) {
      logger.error('Failed to change member role', err)
      if (mine === generation) errorMessage.value = roleChangeMessage(err)
      return false
    } finally {
      if (mine === generation) pendingUserId.value = null
    }
  }

  /** DELETE the member; refused (no request) while the standing is unconfirmed. */
  async function removeMember(member: Member): Promise<void> {
    if (!standingKnown.value) return
    const id = companyId()
    const mine = generation
    pendingUserId.value = member.user_id
    errorMessage.value = ''
    try {
      await api.delete(`${base(id)}/${member.user_id}`)
      if (mine === generation) await load()
    } catch (err) {
      logger.error('Failed to remove member', err)
      if (mine === generation) errorMessage.value = t('llcMembers.removeError')
    } finally {
      if (mine === generation) pendingUserId.value = null
    }
  }

  // Another company: drop what the old one loaded and fetch the new one's.
  watch(companyId, () => {
    generation += 1
    resetStanding()
    errorMessage.value = ''
    pendingUserId.value = null
    isLoading.value = false
    void load()
  })

  return { members, grantableRoles, viewerCanManage, standingKnown, isLoading, errorMessage, pendingUserId, load, changeRole, removeMember }
}
