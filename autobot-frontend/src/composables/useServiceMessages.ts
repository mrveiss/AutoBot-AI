/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Vue composable for the cross-service message audit trail API (#1379).
 * Wraps /api/service-messages/* endpoints.
 */

import { ref, onUnmounted } from 'vue'
import { useApiWithState } from './useApi'
import { createLogger } from '@/utils/debugUtils'

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
  const { api, withErrorHandling } = useApiWithState()

  const messages = ref<ServiceMessageEntry[]>([])
  const chainMessages = ref<ServiceMessageEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  let pollingTimer: ReturnType<typeof setInterval> | null = null
  const isPolling = ref(false)

  async function fetchLatest(params?: {
    count?: number
    sender?: string
    receiver?: string
    msg_type?: string
  }): Promise<LatestMessagesResponse | null> {
    loading.value = true
    error.value = null
    try {
      const result = await withErrorHandling(
        async () => {
          const sp = new URLSearchParams()
          if (params?.count) sp.append('count', String(params.count))
          if (params?.sender) sp.append('sender', params.sender)
          if (params?.receiver) sp.append('receiver', params.receiver)
          if (params?.msg_type) sp.append('msg_type', params.msg_type)
          const qs = sp.toString()
          const url = `/api/service-messages/latest${qs ? `?${qs}` : ''}`
          const resp = await api.get(url)
          return (await resp.json()) as LatestMessagesResponse
        },
        {
          errorMessage: 'Failed to fetch service messages',
          fallbackValue: { success: false, count: 0, messages: [] }
        }
      )
      if (result && result.success) {
        messages.value = result.messages
      }
      return result
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('fetchLatest failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function fetchMessage(
    msgId: string
  ): Promise<SingleMessageResponse | null> {
    return withErrorHandling(
      async () => {
        const resp = await api.get(`/api/service-messages/${msgId}`)
        return (await resp.json()) as SingleMessageResponse
      },
      { errorMessage: 'Failed to fetch service message', fallbackValue: null }
    )
  }

  async function fetchChain(
    correlationId: string
  ): Promise<CorrelationChainResponse | null> {
    loading.value = true
    error.value = null
    try {
      const result = await withErrorHandling(
        async () => {
          const resp = await api.get(
            `/api/service-messages/chain/${correlationId}`
          )
          return (await resp.json()) as CorrelationChainResponse
        },
        {
          errorMessage: 'Failed to fetch correlation chain',
          fallbackValue: null
        }
      )
      if (result && result.success) {
        chainMessages.value = result.messages
      }
      return result
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      logger.error('fetchChain failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  function startPolling(intervalMs = 15000, params?: Parameters<typeof fetchLatest>[0]) {
    stopPolling()
    isPolling.value = true
    pollingTimer = setInterval(() => fetchLatest(params), intervalMs)
    logger.debug(`Polling service messages every ${intervalMs}ms`)
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
    isPolling.value = false
  }

  onUnmounted(() => stopPolling())

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
