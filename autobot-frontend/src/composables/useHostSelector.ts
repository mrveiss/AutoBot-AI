// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useHostSelector - Composable for the ui/HostSelector component
 *
 * Wraps the GET /api/infrastructure/hosts endpoint through useFetchEndpoint
 * so the component is free of inline fetchWithAuth calls.
 *
 * Issue #6087
 */

import { computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

const logger = createLogger('useHostSelector')

export interface SelectorHost {
  id: string
  name: string
  host: string
  ssh_port?: number
  vnc_port?: number
  username?: string
  os?: string
  capabilities?: string[]
  description?: string
  tags?: string[]
}

interface HostsApiResponse {
  hosts?: SelectorHost[]
}

export interface UseHostSelectorOptions {
  /** Only return hosts with this capability (passed as ?capability=). */
  requiredCapability?: string
  /** Chat session ID (passed as ?chat_id=). */
  chatId?: string
}

export function useHostSelector(options: UseHostSelectorOptions = {}) {
  const hostsEndpoint = useFetchEndpoint<HostsApiResponse, SelectorHost[]>({
    path: '/api/infrastructure/hosts',
    label: 'Infrastructure hosts',
    pickData: (raw) => raw.hosts ?? [],
    onSuccess: (data) => {
      logger.info(`Loaded ${data.length} infrastructure hosts`)
    },
    onError: (msg) => {
      logger.error('Failed to load infrastructure hosts:', msg)
    },
  })

  /**
   * Build query-string extras from the current options and trigger a fetch.
   * Accepts a one-off capability override for composable reuse without
   * reconstructing.
   */
  const loadHosts = async (capability?: string, chatId?: string): Promise<void> => {
    const extras: Record<string, string> = {}
    const cap = capability ?? options.requiredCapability
    const chat = chatId ?? options.chatId
    if (cap) extras['capability'] = cap
    if (chat) extras['chat_id'] = chat
    await hostsEndpoint.load(Object.keys(extras).length ? extras : undefined)
  }

  const hosts = computed<SelectorHost[]>(() => hostsEndpoint.data.value ?? [])
  const loading = hostsEndpoint.loading
  const error = hostsEndpoint.error

  return {
    hosts,
    loading,
    error,
    loadHosts,
  }
}

export default useHostSelector
