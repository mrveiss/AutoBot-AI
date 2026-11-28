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

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'
import { useHostSelection } from '@/composables/useHostSelection'
import { fetchDesktopVmEndpoint } from '@/composables/useDesktopVm'
import { desktopVmEntry, type DesktopVmEndpoint } from '@/config/vnc-client'

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

export interface UseHostSelectorOptions {
  /** Only return hosts with this capability (passed as ?capability=). */
  requiredCapability?: string
  /** Chat session ID (passed as ?chat_id=). */
  chatId?: string
  /** List AutoBot's own desktop VM first (chat Desktop picker only). */
  includeDesktopVm?: boolean
}

export function useHostSelector(options: UseHostSelectorOptions = {}) {
  const { t } = useI18n()
  const { hosts: infraHosts, loading, error, loadHosts: loadInfraHosts } = useHostSelection()

  // Map InfrastructureHost → SelectorHost; apply client-side capability filter when set
  // The desktop VM's endpoint comes from the backend (the SLM registry), the same source the controls use.
  const desktopVm = ref<DesktopVmEndpoint | null>(null)
  const loaded = ref(false)
  const registryError = ref(false) // the registry could not be read: not the same as "none registered"
  const loadDesktopVm = async (): Promise<void> => {
    if (!options.includeDesktopVm) return
    registryError.value = false
    try {
      desktopVm.value = await fetchDesktopVmEndpoint()
    } catch (err) {
      logger.warn('Desktop VM endpoint unavailable; no entry offered:', err)
      registryError.value = true
      desktopVm.value = null // no endpoint, no entry: never a guessed address
    }
    loaded.value = true
  }

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
    if (options.includeDesktopVm) {
      list = !desktopVm.value ? list : [{ ...desktopVmEntry(desktopVm.value), name: t('ui.hostSelection.desktopVm'), description: t('ui.hostSelection.desktopVmDesc') }, ...list]
    }
    return list
  })

  const loadHosts = async (capability?: string, _chatId?: string): Promise<void> => {
    await Promise.all([loadInfraHosts(), loadDesktopVm()])
    // Re-assign so the filter in the computed picks up any runtime override
    if (capability) options.requiredCapability = capability
  }

  // One localised line for the picker when it is asked to offer the desktop VM and none is registered.
  const desktopVmHint = computed(() => (options.includeDesktopVm && loaded.value && !desktopVm.value ? t(registryError.value ? 'desktop.interface.registryUnavailable' : 'ui.hostSelection.noDesktopVm') : ''))

  return { hosts, loading, error, loadHosts, desktopVmHint }
}

export default useHostSelector
