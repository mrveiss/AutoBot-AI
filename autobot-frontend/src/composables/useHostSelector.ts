// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useHostSelector - Composable for the ui/HostSelector component
 *
 * ✅ GH#9063 consolidation COMPLETE: delegates host loading to useHostSelection
 * (same /api/infrastructure/hosts source) instead of making a separate
 * useFetchEndpoint call. Maps InfrastructureHost → SelectorHost shape.
 *
 * This composable is a THIN WRAPPER around useHostSelection that:
 * - Provides the SelectorHost type shape for UI components
 * - Applies client-side capability filtering
 * - Maintains backward compatibility for components using the old API
 *
 * Data flow: useHostSelector → useHostSelection → /api/infrastructure/hosts
 *
 * Issue #6087
 */

import { computed } from 'vue'
import { useHostSelection } from '@/composables/useHostSelection'

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

export interface UseHostSelectorOptions {
  /** Only return hosts with this capability (passed as ?capability=). */
  requiredCapability?: string
  /** Chat session ID (passed as ?chat_id=). */
  chatId?: string
}

export function useHostSelector(options: UseHostSelectorOptions = {}) {
  const { hosts: infraHosts, loading, error, loadHosts: loadInfraHosts } = useHostSelection()

  // Map InfrastructureHost → SelectorHost; apply client-side capability filter when set
  const hosts = computed<SelectorHost[]>(() => {
    let list: SelectorHost[] = infraHosts.value.map((h) => ({
      id: h.id,
      name: h.name,
      host: h.host,
      ssh_port: h.ssh_port,
      username: h.username,
      os: h.os,
      // copy: source array is readonly (deep-readonly store state)
      capabilities: h.capabilities ? [...h.capabilities] : undefined,
      description: h.purpose,
    }))
    if (options.requiredCapability) {
      list = list.filter((h: SelectorHost) => h.capabilities?.includes(options.requiredCapability!))
    }
    return list
  })

  const loadHosts = async (capability?: string, _chatId?: string): Promise<void> => {
    await loadInfraHosts()
    // Re-assign so the filter in the computed picks up any runtime override
    if (capability) options.requiredCapability = capability
  }

  return { hosts, loading, error, loadHosts }
}

export default useHostSelector
