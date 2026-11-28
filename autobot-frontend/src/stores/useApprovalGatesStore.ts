// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The approvals waiting for the signed-in person, from any page (#20917).
 *
 * One list, `GET /api/approval-gates/pending` (the server scopes it to the viewer). A live event on
 * the `global` channel is only a reason to ask again: the payload is never merged into the list.
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiClient } from '@/plugins/api'
import liveEventService, { type LiveEvent } from '@/services/LiveEventService'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'

const logger = createLogger('useApprovalGatesStore')

export type PendingApproval = components['schemas']['ApprovalGateResponse']
export type ApprovalVerb = 'approve' | 'reject'

const PENDING_ENDPOINT = '/api/approval-gates/pending'
const GLOBAL_CHANNEL = 'global'
/** Every event that changes what is pending: a new gate, or one decided, withdrawn or expired. */
const REFETCH_EVENTS = new Set([
  'approval_pending',
  'approval_approved',
  'approval_rejected',
  'approval_revision_requested',
  'approval_withdrawn',
  'approval_expired',
])

export const useApprovalGatesStore = defineStore('approvalGates', () => {
  const pending = ref<PendingApproval[]>([])
  const loadFailed = ref(false)
  const deciding = ref<Set<string>>(new Set())
  const count = computed(() => pending.value.length)
  let unsubscribe: (() => void) | null = null

  async function load(): Promise<void> {
    try {
      pending.value = await useApiClient().get<PendingApproval[]>(PENDING_ENDPOINT)
      loadFailed.value = false
    } catch (err) {
      loadFailed.value = true
      logger.error('Failed to load pending approvals', err)
    }
  }

  async function decide(id: string, verb: ApprovalVerb): Promise<boolean> {
    deciding.value = new Set(deciding.value).add(id)
    try {
      await useApiClient().post(`/api/approval-gates/${id}/${verb}`, {})
      await load()
      return true
    } catch (err) {
      logger.error('Approval decision failed', err)
      return false
    } finally {
      const next = new Set(deciding.value)
      next.delete(id)
      deciding.value = next
    }
  }

  function onEvent(event: LiveEvent): void {
    if (REFETCH_EVENTS.has(event.event_type)) void load()
  }

  /** Load the list and keep it current; safe to call again. */
  async function start(): Promise<void> {
    if (!unsubscribe) unsubscribe = liveEventService.subscribe(GLOBAL_CHANNEL, onEvent)
    await load()
  }

  function stop(): void {
    unsubscribe?.()
    unsubscribe = null
    pending.value = []
  }

  return { pending, count, loadFailed, deciding, load, decide, start, stop }
})
