// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** GUI automation opportunities for the workflow builder (#1242); `reset` drops them on a company switch (#21520). */
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useLatestRequest } from '@/composables/useLatestRequest'
import { getAutomationOpportunities } from '@/composables/useVisionApi'
import type { AutomationOpportunity } from '@/types/visionMultimodal'

const logger = createLogger('useGuiAutomationOpportunities')

export function useGuiAutomationOpportunities() {
  const opportunities = ref<AutomationOpportunity[]>([])
  const loading = ref(false)
  /** True when the last refresh failed: distinct from a refresh that found no opportunities. */
  const loadFailed = ref(false)
  const requests = useLatestRequest() // a company switch revokes the refresh in flight (#21520)
  async function load(): Promise<void> {
    const token = requests.begin()
    loading.value = true
    loadFailed.value = false
    try {
      const res = await getAutomationOpportunities()
      if (!requests.isCurrent(token)) return
      opportunities.value = (res.opportunities || []) as AutomationOpportunity[]
    } catch (e) {
      if (!requests.isCurrent(token)) return
      loadFailed.value = true
      logger.warn('Failed to load automation opportunities:', e)
    } finally {
      if (requests.isCurrent(token)) loading.value = false
    }
  }
  const reset = (): void => {
    requests.invalidate()
    opportunities.value = []
    loading.value = false
    loadFailed.value = false
  }
  return { opportunities, loading, loadFailed, load, reset }
}
