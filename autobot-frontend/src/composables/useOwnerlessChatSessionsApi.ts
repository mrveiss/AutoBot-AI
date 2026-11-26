// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #20904: list the chat sessions that record no owner and PROPOSE an owner for one.
 * A proposal only creates a pending approval (#17038); nothing is assigned until a human approves it.
 */
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']

const logger = createLogger('useOwnerlessChatSessionsApi')

export function useOwnerlessChatSessionsApi() {
  const report = ref<Schemas['OwnerlessChatSessionsReport'] | null>(null)
  const loadFailed = ref(false)

  async function load(): Promise<void> {
    loadFailed.value = false
    try {
      report.value = await apiClient.get('/api/admin/ownerless-chat-sessions')
    } catch (err) {
      loadFailed.value = true
      logger.error('Could not load the ownerless chat session report', err)
    }
  }

  /** Propose `owner` for `sessionId`; resolves with the pending approval's id. */
  async function propose(sessionId: string, owner: string): Promise<string> {
    const body: Schemas['OwnerlessChatSessionRequest'] = { session_id: sessionId, owner }
    const reply: Schemas['OwnerlessChatSessionRequestResponse'] = await apiClient.post(
      '/api/admin/ownerless-chat-sessions/requests',
      body,
    )
    return reply.approval_id
  }

  return { report, loadFailed, load, propose }
}
