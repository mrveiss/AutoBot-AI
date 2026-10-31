// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The SLM agent ledger, admin only (#18391 AC2): every company's claims, the
 * shared resources agents queue for, the conflicts, the dev-loop history per
 * issue and the ledger's own activity — plus which sources the SLM cannot
 * read at all, so a gap is never shown as "none".
 *
 * The routes are `/api/monitoring/agent-ledger/*` (admin, `ADMIN_SYSTEM`).
 * Reading the answers, and what a yield request came back with, is the kit's
 * (`@autobot/ui` ledger helpers), shared with the Company OS ledger view.
 */

import { ref, type Ref } from 'vue'
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
} from '@autobot/ui'
import { slmApiClient } from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']
/** The ledger row shapes are the kit's, one declaration for both consoles (#19910). */
export type { ActivityRow, ClaimRow, ConflictRow, IdleSubscriberRow, PeerMessageRow, PresenceRow }
export type ContentionRow = Schemas['ContentionRow']
export type DevLoopActionRow = Schemas['DevLoopActionRow']
export type LedgerSourceStatus = Schemas['LedgerSourceStatus']

const LEDGER = '/monitoring/agent-ledger'

function read<T>(path: string, field: string): Promise<LedgerSection<T>> {
  return readLedgerSection<T>(() => slmApiClient.rawRequest(`${LEDGER}${path}`), field)
}

/** Ask a claim's holder to release it — the same yield request an agent sends. Never a release. */
export function askHolderToRelease(scope: string, holderTaskId: string, reason = ''): Promise<LedgerAskOutcome> {
  return sendLedgerAsk(() =>
    slmApiClient.rawRequest(`${LEDGER}/claims/yield-request`, {
      method: 'POST',
      body: { scope, holder_task_id: holderTaskId, reason },
    })
  )
}

/** One issue's dev-loop actions, read when the issue is opened. */
export function readDevLoopHistory(issue: number): Promise<LedgerSection<DevLoopActionRow>> {
  return read<DevLoopActionRow>(`/dev-loop/${issue}`, 'actions')
}

export function useSlmAgentLedger() {
  const sources: Ref<LedgerSection<LedgerSourceStatus>> = ref(loadingLedgerSection())
  const contention: Ref<LedgerSection<ContentionRow>> = ref(loadingLedgerSection())
  const claims: Ref<LedgerSection<ClaimRow>> = ref(loadingLedgerSection())
  const conflicts: Ref<LedgerSection<ConflictRow>> = ref(loadingLedgerSection())
  const activity: Ref<LedgerSection<ActivityRow>> = ref(loadingLedgerSection())
  const devLoopIssues: Ref<LedgerSection<number>> = ref(loadingLedgerSection())
  // Live state, read from the user backend's snapshot (#18632).
  const presence: Ref<LedgerSection<PresenceRow>> = ref(loadingLedgerSection())
  const peerMessages: Ref<LedgerSection<PeerMessageRow>> = ref(loadingLedgerSection())
  const idleSubscribers: Ref<LedgerSection<IdleSubscriberRow>> = ref(loadingLedgerSection())

  async function refresh(): Promise<void> {
    const [s, p, m, i, n, c, x, a, d] = await Promise.all([
      read<LedgerSourceStatus>('/sources', 'sources'),
      read<PresenceRow>('/presence', 'agents'),
      read<PeerMessageRow>('/peer-messages', 'recipients'),
      read<IdleSubscriberRow>('/idle-subscribers', 'subscribers'),
      read<ContentionRow>('/contention', 'resources'),
      read<ClaimRow>('/claims', 'claims'),
      read<ConflictRow>('/conflicts', 'conflicts'),
      read<ActivityRow>('/activity', 'activity'),
      read<number>('/dev-loop', 'issues'),
    ])
    sources.value = s
    presence.value = p
    peerMessages.value = m
    idleSubscribers.value = i
    contention.value = n
    claims.value = c
    conflicts.value = x
    activity.value = a
    devLoopIssues.value = d
  }

  return { sources, presence, peerMessages, idleSubscribers, contention, claims, conflicts, activity, devLoopIssues, refresh }
}
