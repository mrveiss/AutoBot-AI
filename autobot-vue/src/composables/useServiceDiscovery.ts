// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vue composable for reactive service discovery (Issue #760 Phase 3).
 *
 * Provides reactive access to discovered services with automatic refresh.
 *
 * Usage:
 *   const { discoverUrl, isLoading, error } = useServiceDiscovery();
 *   const redisUrl = await discoverUrl('redis');
 */

import { ref, computed } from 'vue'
import { discoverService, clearDiscoveryCache } from '@/config/ssot-config'
import { useUserStore } from '@/stores/useUserStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useServiceDiscovery')

/**
 * Service discovery state for a single service.
 */
interface ServiceDiscoveryState {
  url: string | null
  isLoading: boolean
  error: string | null
  lastFetched: number | null
}

/**
 * Vue composable for service discovery.
 */
export function useServiceDiscovery() {
  const userStore = useUserStore()
  const services = ref<Map<string, ServiceDiscoveryState>>(new Map())
  const isGlobalLoading = ref(false)
  const globalError = ref<string | null>(null)

  /**
   * Get the auth token from user store.
   */
  function getAuthToken(): string | null {
    // Access token from user store's authState
    const authState = userStore.authState
    if (authState && authState.token && authState.token !== 'single_user_mode') {
      return authState.token
    }
    // For single user mode or no auth, return a placeholder
    // The SLM will handle auth appropriately
    return 'single_user_mode'
  }

  /**
   * Discover a service URL.
   */
  async function discoverUrl(
    serviceName: string,
    forceRefresh = false
  ): Promise<string> {
    // Check local state cache
    const existing = services.value.get(serviceName)
    if (
      !forceRefresh &&
      existing?.url &&
      existing.lastFetched &&
      Date.now() - existing.lastFetched < 60000
    ) {
      return existing.url
    }

    // Update loading state
    services.value.set(serviceName, {
      url: existing?.url ?? null,
      isLoading: true,
      error: null,
      lastFetched: existing?.lastFetched ?? null,
    })

    try {
      const token = getAuthToken()
      if (!token) {
        throw new Error('Not authenticated')
      }

      if (forceRefresh) {
        clearDiscoveryCache()
      }

      const url = await discoverService(serviceName, token)

      services.value.set(serviceName, {
        url,
        isLoading: false,
        error: null,
        lastFetched: Date.now(),
      })

      logger.debug(`Discovered ${serviceName}: ${url}`)
      return url
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Discovery failed'
      services.value.set(serviceName, {
        url: existing?.url ?? null,
        isLoading: false,
        error: errorMsg,
        lastFetched: existing?.lastFetched ?? null,
      })
      logger.error(`Failed to discover ${serviceName}: ${errorMsg}`)
      throw err
    }
  }

  /**
   * Get service state (reactive).
   */
  function getServiceState(serviceName: string): ServiceDiscoveryState | undefined {
    return services.value.get(serviceName)
  }

  /**
   * Check if any service is loading.
   */
  const isLoading = computed(() => {
    for (const state of services.value.values()) {
      if (state.isLoading) return true
    }
    return isGlobalLoading.value
  })

  /**
   * Clear all cached discoveries.
   */
  function clearAll(): void {
    services.value.clear()
    clearDiscoveryCache()
    logger.debug('Cleared all service discovery cache')
  }

  return {
    discoverUrl,
    getServiceState,
    isLoading,
    globalError,
    clearAll,
    services,
  }
}
