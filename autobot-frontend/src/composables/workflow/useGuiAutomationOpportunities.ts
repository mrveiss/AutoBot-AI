// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** GUI automation opportunities for the workflow builder (#1242); `reset` drops them on a company switch (#21520). */
import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getAutomationOpportunities } from '@/composables/useVisionApi'
import type { AutomationOpportunity } from '@/types/visionMultimodal'

const logger = createLogger('useGuiAutomationOpportunities')

export function useGuiAutomationOpportunities() {
  const opportunities = ref<AutomationOpportunity[]>([])
  const loading = ref(false)
  async function load(): Promise<void> {
    loading.value = true
    try {
      const res = await getAutomationOpportunities()
      opportunities.value = (res.opportunities || []) as AutomationOpportunity[]
    } catch (e) {
      logger.warn('Failed to load automation opportunities:', e)
    } finally {
      loading.value = false
    }
  }
  const reset = (): void => {
    opportunities.value = []
  }
  return { opportunities, loading, load, reset }
}
