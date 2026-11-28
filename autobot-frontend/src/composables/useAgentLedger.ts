// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The Company OS agent ledger, read-only (#18391): who is working on what, the
 * claims they hold, who waits behind them, and what happened recently.
 *
 * Every section carries its own state, because the backend reports an unreadable
 * store as a typed 503 (`LedgerUnavailable`) rather than an empty list: the screen
 * must say "couldn't read the ledger" for that section, never "no claims".
 * Company scoping is the backend's (the org context header ApiClient sends).
 */

import { computed, ref, type Ref } from 'vue'
import {
  loadingLedgerSection,
  readLedgerSection,
  sendLedgerAsk,
  type LedgerAskOutcome,
  type LedgerSection,
  type ActivityRow,
  type ClaimRow,
  type ConflictRow,
  type IdleSubscriberRow,
  type PeerMessageRow,
  type PresenceRow,
  type LedgerSectionStatus,
} from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']
/** The ledger row shapes are the kit's, one declaration for both consoles (#19910). */
export type { ActivityRow, ClaimRow, ConflictRow, IdleSubscriberRow, PeerMessageRow, PresenceRow }
export type WaiterRow = Schemas['WaiterRow']

/** Section states and answers are read by the kit, shared with the SLM ledger view. */
export type { LedgerSection }
export type SectionState = LedgerSectionStatus

/** One contended (or merely held) resource: its holders and its queue, in order. */
export interface ScopeView {
  scope: string
  kind: string
  holders: ClaimRow[]
  waiters: WaiterRow[]
}

const LEDGER = '/coordination/ledger'

/** GET one ledger path and pick its list field; a 503 with the typed body is `unavailable`. */
function fetchSection<T>(path: string, field: string): Promise<LedgerSection<T>> {
  return readLedgerSection<T>(() => apiClient.rawRequest(`${getApiBase()}${LEDGER}${path}`, { method: 'GET' }), field)
}

/** Group claims and waiters by scope; waiters stay in queue order. */
export function groupByScope(claims: ClaimRow[], waiters: WaiterRow[]): ScopeView[] {
  const byScope = new Map<string, ScopeView>()
  const entry = (scope: string, kind: string) => {
    if (!byScope.has(scope)) byScope.set(scope, { scope, kind, holders: [], waiters: [] })
    return byScope.get(scope)!
  }
  for (const c of claims) entry(c.scope, c.kind).holders.push(c)
  for (const w of waiters) entry(w.scope, byScope.get(w.scope)?.kind ?? w.scope.split(':')[0]).waiters.push(w)
  for (const s of byScope.values()) s.waiters.sort((a, b) => a.position - b.position)
  return [...byScope.values()].sort((a, b) => b.waiters.length - a.waiters.length || a.scope.localeCompare(b.scope))
}

/**
 * What happened to a request that the holder release a claim (#18391 AC4, route #18599).
 * Asking never releases anything: `sent` means the request was delivered and the
 * holder decides -- silence means hold. Each failure stays distinguishable.
 */
export type AskOutcome = LedgerAskOutcome
// sent | too-soon (429: asked about this scope within the window) | not-found (404: no
// such claim for this company, or it changed hands) | unavailable (typed 503) | error
// (anything else, a lost response included: the request may have been delivered)

/** Ask the holder of `scope` to release it -- the same yield request an agent sends. */
export function askHolderToRelease(scope: string, holderTaskId: string, reason = ''): Promise<AskOutcome> {
  return sendLedgerAsk(() =>
    apiClient.rawRequest(`${getApiBase()}${LEDGER}/claims/yield-request`, {
      method: 'POST',
      body: { scope, holder_task_id: holderTaskId, reason },
    })
  )
}

export function useAgentLedger() {
  const presence: Ref<LedgerSection<PresenceRow>> = ref(loadingLedgerSection())
  const claims: Ref<LedgerSection<ClaimRow>> = ref(loadingLedgerSection())
  const waitlists: Ref<LedgerSection<WaiterRow>> = ref(loadingLedgerSection())
  const conflicts: Ref<LedgerSection<ConflictRow>> = ref(loadingLedgerSection())
  const activity: Ref<LedgerSection<ActivityRow>> = ref(loadingLedgerSection())
  const peerMessages: Ref<LedgerSection<PeerMessageRow>> = ref(loadingLedgerSection())
  const idleSubscribers: Ref<LedgerSection<IdleSubscriberRow>> = ref(loadingLedgerSection())

  /** Contention needs both claims and waitlists; it is only as readable as the worse of the two. */
  const contention = computed<LedgerSection<ScopeView>>(() => {
    for (const s of [claims.value, waitlists.value]) {
      if (s.state !== 'ready') return { state: s.state, rows: [], source: s.source }
    }
    return { state: 'ready', rows: groupByScope(claims.value.rows, waitlists.value.rows) }
  })

  async function refresh(): Promise<void> {
    const [p, c, w, x, a, m, i] = await Promise.all([
      fetchSection<PresenceRow>('/presence', 'agents'),
      fetchSection<ClaimRow>('/claims', 'claims'),
      fetchSection<WaiterRow>('/waitlists', 'waiters'),
      fetchSection<ConflictRow>('/conflicts', 'conflicts'),
      fetchSection<ActivityRow>('/activity', 'activity'),
      fetchSection<PeerMessageRow>('/peer-messages', 'recipients'),
      fetchSection<IdleSubscriberRow>('/idle-subscribers', 'subscribers'),
    ])
    presence.value = p
    claims.value = c
    waitlists.value = w
    conflicts.value = x
    activity.value = a
    peerMessages.value = m
    idleSubscribers.value = i
  }

  return { presence, claims, waitlists, conflicts, activity, peerMessages, idleSubscribers, contention, refresh }
}
