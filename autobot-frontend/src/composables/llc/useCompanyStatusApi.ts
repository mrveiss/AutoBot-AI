// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * LLC company status-transition API (GH#12231).
 *
 * Wraps the four backend status-transition endpoints added in #12211/#12234:
 *   POST /api/llc/companies/{id}/activate  -> ACTIVE
 *   POST /api/llc/companies/{id}/suspend   -> PAUSED   (optional reason)
 *   POST /api/llc/companies/{id}/offboard  -> OFFBOARDING
 *   POST /api/llc/companies/{id}/archive   -> ARCHIVED
 *
 * Each call returns the full updated CompanyRead (parsed JSON, no envelope).
 * The valid-transition map mirrors the backend guards in
 * autobot-backend/llc/services/company.py so the UI only ever offers a
 * transition the backend will accept (a 409 is still surfaced as an error).
 */
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyStatusApi')

/** The five LLC company lifecycle states (LLCCompanyStatus enum). */
export type CompanyStatus = 'onboarding' | 'active' | 'paused' | 'offboarding' | 'archived'

/** The four status-transition actions an operator can trigger. */
export type CompanyStatusAction = 'activate' | 'suspend' | 'offboard' | 'archive'

/** Subset of the backend CompanyRead schema a transition returns. */
export interface CompanyStatusResult {
  id: string
  name: string
  llc_status: CompanyStatus
  pause_reason?: string | null
  paused_at?: string | null
}

/**
 * Current status -> the transitions valid from it. Mirrors the backend
 * `_ACTIVATE_FROM` / `_SUSPEND_FROM` / `_OFFBOARD_FROM` / `_ARCHIVE_FROM`
 * frozensets. ARCHIVED is terminal (no outgoing transitions).
 */
export const VALID_TRANSITIONS: Record<CompanyStatus, CompanyStatusAction[]> = {
  onboarding: ['activate', 'suspend'],
  active: ['suspend', 'offboard'],
  paused: ['activate', 'archive'],
  offboarding: ['archive'],
  archived: [],
}

/** Transitions that discard/park a company — the UI must confirm these. */
export const DESTRUCTIVE_ACTIONS: ReadonlySet<CompanyStatusAction> = new Set([
  'offboard',
  'archive',
])

/** Actions valid from the given status (empty for an unknown/terminal state). */
export function transitionsFor(status: string | undefined | null): CompanyStatusAction[] {
  if (!status) return []
  return VALID_TRANSITIONS[status as CompanyStatus] ?? []
}

export function useCompanyStatusApi() {
  async function transition(
    companyId: string,
    action: CompanyStatusAction,
    reason?: string,
  ): Promise<CompanyStatusResult> {
    const api = useApiClient()
    const body = action === 'suspend' && reason ? { reason } : undefined
    try {
      return await api.post<CompanyStatusResult>(
        `/api/llc/companies/${companyId}/${action}`,
        body,
      )
    } catch (err) {
      logger.error(`Company ${action} failed for ${companyId}`, err)
      throw err
    }
  }

  return {
    activate: (id: string) => transition(id, 'activate'),
    suspend: (id: string, reason?: string) => transition(id, 'suspend', reason),
    offboard: (id: string) => transition(id, 'offboard'),
    archive: (id: string) => transition(id, 'archive'),
    transition,
  }
}
