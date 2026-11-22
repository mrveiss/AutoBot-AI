// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useStopGeneration — stop the assistant's reply that is streaming now (#17829).
 *
 * Calls POST /chat/sessions/{session_id}/turn/cancel (#17273, #18447), which cancels the
 * turn server-side: the LLM request and its tools stop, not only the display. The stream
 * then ends with a `cancelled` event and the controller clears the typing state. The text
 * already shown stays on screen; persisting it is #18445.
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useChatStore } from '@/stores/useChatStore'

const logger = createLogger('useStopGeneration')

export function useStopGeneration() {
  const store = useChatStore()
  const stopping = ref(false)
  const failed = ref(false)

  /** Ask the server to cancel the session's running turn; true when it accepted. */
  async function stop(): Promise<boolean> {
    const sessionId = store.currentSessionId
    if (!sessionId || stopping.value) return false
    stopping.value = true
    failed.value = false
    try {
      await apiClient.post(
        `${getApiBase()}/chat/sessions/${encodeURIComponent(sessionId)}/turn/cancel`,
        {},
      )
      return true
    } catch (e) {
      failed.value = true
      logger.warn('Stopping the reply failed:', e instanceof Error ? e.message : e)
      return false
    } finally {
      stopping.value = false
    }
  }

  return { stopping, failed, stop }
}
