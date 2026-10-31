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
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyMembers')

export interface Member {
  user_id: string
  /** Never null: `list_members` resolves the whole ladder server-side (#14939). */
  display_name: string
  role: string
  /** The caller's own role in this company; the same on every row. Null without a membership. */
  viewer_role?: string | null
  /** The roles the server would let the caller grant or revoke (#20073). */
  viewer_grantable_roles?: string[]
}

export interface MembersApi {
  get<T>(url: string): Promise<T>
  patch<T>(url: string, body: unknown): Promise<T>
  delete<T>(url: string): Promise<T>
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

export function useCompanyMembers(api: MembersApi, companyId: () => string) {
  const { t } = useI18n()
  const members = ref<Member[]>([])
  const grantableRoles = ref<string[]>([])
  const isLoading = ref(false)
  const errorMessage = ref('')
  const pendingUserId = ref<string | null>(null)
  // Bumped when the company changes: a response captured under an older generation is discarded.
  let generation = 0

  const base = (id: string) => `/api/llc/companies/${id}/members`

  async function load(): Promise<void> {
    const id = companyId()
    if (!id) return
    const mine = generation
    isLoading.value = true
    errorMessage.value = ''
    try {
      const rows = await api.get<Member[]>(base(id))
      if (mine !== generation) return
      members.value = rows
      grantableRoles.value = rows[0]?.viewer_grantable_roles ?? []
    } catch (err) {
      logger.error('Failed to load members', err)
      if (mine !== generation) return
      errorMessage.value = t('llcMembers.loadError')
      members.value = []
      grantableRoles.value = []
    } finally {
      if (mine === generation) isLoading.value = false
    }
  }

  function roleChangeMessage(err: unknown): string {
    const status = statusOf(err)
    if (status === 403) return t('llcMembers.roleChangeForbidden')
    if (status === 409) return t('llcMembers.roleChangeLastOwner')
    return t('llcMembers.roleChangeError')
  }

  /** PATCH the role; the row changes only once the server accepts it. False when it did not. */
  async function changeRole(member: Member, newRole: string): Promise<boolean> {
    const id = companyId()
    const mine = generation
    pendingUserId.value = member.user_id
    errorMessage.value = ''
    try {
      await api.patch(`${base(id)}/${member.user_id}`, { role: newRole })
      if (mine !== generation) return false
      const row = members.value.find((m) => m.user_id === member.user_id)
      if (row) row.role = newRole
      return true
    } catch (err) {
      logger.error('Failed to change member role', err)
      if (mine === generation) errorMessage.value = roleChangeMessage(err)
      return false
    } finally {
      if (mine === generation) pendingUserId.value = null
    }
  }

  async function removeMember(member: Member): Promise<void> {
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
    members.value = []
    grantableRoles.value = []
    errorMessage.value = ''
    pendingUserId.value = null
    isLoading.value = false
    void load()
  })

  return { members, grantableRoles, isLoading, errorMessage, pendingUserId, load, changeRole, removeMember }
}
