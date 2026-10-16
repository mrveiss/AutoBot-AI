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
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'

const logger = createLogger('useAgentLedger')

type Schemas = components['schemas']
export type ClaimRow = Schemas['ClaimRow']
export type WaiterRow = Schemas['WaiterRow']
export type PresenceRow = Schemas['PresenceRow']
export type ActivityRow = Schemas['ActivityRow']
export type ConflictRow = Schemas['ConflictRow']
export type PeerMessageRow = Schemas['PeerMessageRow']
export type IdleSubscriberRow = Schemas['IdleSubscriberRow']

/** loading -> ready (data, possibly empty) | unavailable (typed 503) | error (anything else). */
export type SectionState = 'loading' | 'ready' | 'unavailable' | 'error'

export interface LedgerSection<T> {
  state: SectionState
  rows: T[]
  /** For `unavailable`: which store the backend could not read. */
  source?: string
}

/** One contended (or merely held) resource: its holders and its queue, in order. */
export interface ScopeView {
  scope: string
  kind: string
  holders: ClaimRow[]
  waiters: WaiterRow[]
}

const LEDGER = '/coordination/ledger'

function emptySection<T>(): LedgerSection<T> {
  return { state: 'loading', rows: [] }
}

/** GET one ledger path and pick its list field; a 503 with the typed body is `unavailable`. */
async function fetchSection<T>(path: string, field: string): Promise<LedgerSection<T>> {
  try {
    const response = await apiClient.rawRequest(`${getApiBase()}${LEDGER}${path}`, { method: 'GET' })
    const body = (await response.json().catch(() => null)) as Record<string, unknown> | null
    if (response.status === 503 && body?.error === 'ledger_unavailable') {
      return { state: 'unavailable', rows: [], source: String(body.source ?? '') }
    }
    if (!response.ok || !body || !Array.isArray(body[field])) {
      logger.warn(`ledger ${path} answered ${response.status}`)
      return { state: 'error', rows: [] }
    }
    return { state: 'ready', rows: body[field] as T[] }
  } catch (err: unknown) {
    logger.warn(`ledger ${path} failed:`, err)
    return { state: 'error', rows: [] }
  }
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

export function useAgentLedger() {
  const presence: Ref<LedgerSection<PresenceRow>> = ref(emptySection())
  const claims: Ref<LedgerSection<ClaimRow>> = ref(emptySection())
  const waitlists: Ref<LedgerSection<WaiterRow>> = ref(emptySection())
  const conflicts: Ref<LedgerSection<ConflictRow>> = ref(emptySection())
  const activity: Ref<LedgerSection<ActivityRow>> = ref(emptySection())
  const peerMessages: Ref<LedgerSection<PeerMessageRow>> = ref(emptySection())
  const idleSubscribers: Ref<LedgerSection<IdleSubscriberRow>> = ref(emptySection())

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
