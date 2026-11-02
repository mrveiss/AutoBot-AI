// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Whether the viewer may detach a workflow or tool from a role (#20682).
 *
 * The server refuses `DELETE /api/llc/roles/{company}/{role}/workflows|tools/...` unless the caller's
 * membership role in THAT company is one of GRANTING_ROLES (owner, admin): `require_company_admin` in
 * `llc/services/authz.py`, with no platform-admin bypass. The same standing is read from the members
 * list (`viewer_role`), so the card's detach buttons show to exactly who the server would allow. It is
 * reflected, never enforced: the server re-checks every call. No answer (loading, error, no membership)
 * hides the buttons.
 */
import { ref, watch } from 'vue'
import type { Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useViewerCanDetach')

/** Membership roles `GRANTING_ROLES` allows to change role attachments; mirrors the server. */
export const DETACH_ROLES: readonly string[] = ['owner', 'admin']

export function mayDetach(viewerRole: string | null | undefined): boolean {
  return viewerRole != null && DETACH_ROLES.includes(viewerRole)
}

interface MembersApi {
  get: (url: string) => Promise<unknown>
}

interface MemberStanding {
  viewer_role?: string | null
}

export function useViewerCanDetach(api: MembersApi, companyId: Ref<string | null | undefined>) {
  const canDetach = ref(false)
  let seq = 0

  async function load(id: string | null | undefined): Promise<void> {
    const mine = ++seq
    canDetach.value = false
    if (!id) return
    try {
      const rows = (await api.get(`/api/llc/companies/${id}/members`)) as MemberStanding[]
      if (mine === seq) canDetach.value = mayDetach(rows[0]?.viewer_role)
    } catch (err) {
      logger.error('Failed to read the viewer standing', err)
    }
  }

  watch(companyId, load, { immediate: true })
  return { canDetach }
}
