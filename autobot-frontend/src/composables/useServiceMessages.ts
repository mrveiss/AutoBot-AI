// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Vue composable for the cross-service message audit trail API (#1379).
 * Wraps /api/service-messages/* endpoints.
 */

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { getApiBase } from '@/config/ssot-config'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useServiceMessages')

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface ServiceMessageEntry {
  msg_id: string
  ts: string
  sender: string
  receiver: string
  msg_type: string
  content: string
  correlation_id: string
  meta: Record<string, unknown>
}

export interface LatestMessagesResponse {
  success: boolean
  count: number
  messages: ServiceMessageEntry[]
}

export interface SingleMessageResponse {
  success: boolean
  message: ServiceMessageEntry | null
}

export interface CorrelationChainResponse {
  success: boolean
  correlation_id: string
  count: number
  messages: ServiceMessageEntry[]
}

// ------------------------------------------------------------------
// Composable
// ------------------------------------------------------------------

export function useServiceMessages() {
  const api = useApiClient()

  const messages = ref<ServiceMessageEntry[]>([])
  const chainMessages = ref<ServiceMessageEntry[]>([])
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  const isPolling = ref(false)

  async function fetchLatest(params?: {
    count?: number
    sender?: string
    receiver?: string
    msg_type?: string
  }): Promise<LatestMessagesResponse | null> {
    error.value = null
    return wrap(async () => {
      try {
        const sp = new URLSearchParams()
        if (params?.count) sp.append('count', String(params.count))
        if (params?.sender) sp.append('sender', params.sender)
        if (params?.receiver) sp.append('receiver', params.receiver)
        if (params?.msg_type) sp.append('msg_type', params.msg_type)
        const qs = sp.toString()
        const url = `${getApiBase()}/service-messages/latest${qs ? `?${qs}` : ''}`
        const result = await api.get<LatestMessagesResponse>(url)
        if (result && result.success) {
          messages.value = result.messages
        }
        return result
      } catch (e) {
        error.value = e instanceof Error ? e.message : 'Unknown error'
        logger.error('fetchLatest failed:', e)
        showSubtleErrorNotification('Error', 'Failed to fetch service messages', 'error')
        return { success: false, count: 0, messages: [] }
      }
    })
  }

  async function fetchMessage(
    msgId: string
  ): Promise<SingleMessageResponse | null> {
    try {
      return await api.get<SingleMessageResponse>(`${getApiBase()}/service-messages/${msgId}`)
    } catch (e: unknown) {
      logger.error('Failed to fetch service message', e)
      showSubtleErrorNotification('Error', 'Failed to fetch service message', 'error')
      return null
    }
  }

  async function fetchChain(
    correlationId: string
  ): Promise<CorrelationChainResponse | null> {
    error.value = null
    return wrap(async () => {
      try {
        const result = await api.get<CorrelationChainResponse>(
          `${getApiBase()}/service-messages/chain/${correlationId}`
        )
        if (result && result.success) {
          chainMessages.value = result.messages
        }
        return result
      } catch (e) {
        error.value = e instanceof Error ? e.message : 'Unknown error'
        logger.error('fetchChain failed:', e)
        showSubtleErrorNotification('Error', 'Failed to fetch correlation chain', 'error')
        return null
      }
    })
  }

  let _stopServiceMessagesPoller: (() => void) | null = null

  function startPolling(intervalMs = 15000, params?: Parameters<typeof fetchLatest>[0]) {
    if (_stopServiceMessagesPoller) _stopServiceMessagesPoller()
    isPolling.value = true
    logger.debug(`Polling service messages every ${intervalMs}ms`)
    const poller = usePollingJob<void>(
      async () => { await fetchLatest(params) },
      { intervalMs }
    )
    _stopServiceMessagesPoller = poller.stop
    poller.start('')
  }

  function stopPolling() {
    if (_stopServiceMessagesPoller) _stopServiceMessagesPoller()
    _stopServiceMessagesPoller = null
    isPolling.value = false
  }

  return {
    messages,
    chainMessages,
    loading,
    error,
    isPolling,
    fetchLatest,
    fetchMessage,
    fetchChain,
    startPolling,
    stopPolling
  }
}
