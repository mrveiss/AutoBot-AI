// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Provider Fallback Observability Composable (#11996 / umbrella #11994)
 *
 * Surfaces the provider-routing decision path for the always-on admin panel:
 *   - `fetchFallbackStatus()` reads `GET /api/llm/fallback-status` (#9421 /
 *     #11995) for the reload-safe current state (configured chains + active
 *     fallbacks reclaimed from the `llm:fallback:active:*` Redis write).
 *   - `subscribeToFallbackEvents()` consumes live PROVIDER_FALLBACK events on
 *     the "global" channel (#11995) — mirrors `useAgentEvents.ts`.
 *
 * No new backend API is introduced: both a live stream and a read API already
 * exist, so the panel is "always on" (live) AND reload-safe (status endpoint).
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import liveEventService, { type LiveEvent } from '@/services/LiveEventService'
import {
  PROVIDER_FALLBACK,
  type FallbackStatusResponse,
  type ProviderFallbackPayload,
} from '@/constants/providerFallbackEvents'

const logger = createLogger('useProviderFallbackApi')

const EMPTY_STATUS: FallbackStatusResponse = {
  configured_chains: [],
  active_fallbacks: [],
}

export interface UseProviderFallbackApiReturn {
  /** Fetch current fallback state (reload-safe) from the read API. */
  fetchFallbackStatus: () => Promise<FallbackStatusResponse>
  /**
   * Subscribe to live PROVIDER_FALLBACK events on the global channel.
   * Returns an unsubscribe function.
   */
  subscribeToFallbackEvents: (
    callback: (payload: ProviderFallbackPayload) => void,
  ) => () => void
}

export function useProviderFallbackApi(): UseProviderFallbackApiReturn {
  const api = useApiClient()

  async function fetchFallbackStatus(): Promise<FallbackStatusResponse> {
    try {
      const data = await api.get<FallbackStatusResponse>(
        `${getApiBase()}/llm/fallback-status`,
      )
      return {
        configured_chains: data?.configured_chains ?? [],
        active_fallbacks: data?.active_fallbacks ?? [],
      }
    } catch (error: unknown) {
      logger.error('Failed to load provider fallback status', error)
      return { ...EMPTY_STATUS }
    }
  }

  function subscribeToFallbackEvents(
    callback: (payload: ProviderFallbackPayload) => void,
  ): () => void {
    const handler = (event: LiveEvent): void => {
      if (event.event_type !== PROVIDER_FALLBACK) return
      const payload = event.payload as ProviderFallbackPayload
      logger.debug('PROVIDER_FALLBACK received', {
        conversation_id: payload.conversation_id,
        exhausted: payload.exhausted,
      })
      callback(payload)
    }
    return liveEventService.subscribe('global', handler)
  }

  return { fetchFallbackStatus, subscribeToFallbackEvents }
}
