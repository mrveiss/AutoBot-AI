// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Developer Speedup Composable
 * Issue #902 - Developer Speedup Tools
 */

import { ref, onMounted, getCurrentInstance } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from './useLoadingState'

const logger = createLogger('useDevSpeedup')

// ===== Type Definitions =====

export interface CodeTemplate {
  id: string
  name: string
  description: string
  language: string
  template: string
  variables: string[]
  category: string
}

export interface SpeedupAction {
  id: string
  action: string
  timestamp: string
  input: string
  output: string
}

export interface UseDevSpeedupOptions {
  autoFetch?: boolean
}

// ===== Composable Implementation =====

export function useDevSpeedup(options: UseDevSpeedupOptions = {}) {
  const { autoFetch = false } = options

  // State
  const templates = ref<CodeTemplate[]>([])
  const actionHistory = ref<SpeedupAction[]>([])
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  // ===== API Methods =====

  async function fetchTemplates(category?: string): Promise<void> {
    error.value = null
    return wrap(async () => {
      try {
        const params = category ? `?category=${category}` : ''
        const data = await ApiClient.get<{ templates: CodeTemplate[] }>(`${getApiBase()}/dev-speedup/templates${params}`)
        templates.value = data.templates || []
        logger.debug('Fetched templates:', templates.value.length)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch templates'
        logger.error('Failed to fetch templates:', err)
        error.value = message
      }
    })
  }

  async function fetchHistory(): Promise<void> {
    try {
      const data = await ApiClient.get<{ actions: SpeedupAction[] }>(`${getApiBase()}/dev-speedup/history`)
      actionHistory.value = data.actions || []
      logger.debug('Fetched action history:', actionHistory.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch history'
      logger.error('Failed to fetch history:', err)
      error.value = message
    }
  }

  // ===== Lifecycle =====

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) {
        Promise.all([fetchTemplates(), fetchHistory()])
      }
    })
  }

  return {
    // State
    templates,
    actionHistory,
    isLoading,
    error,

    // Methods
    fetchTemplates,
    fetchHistory,
  }
}

export default useDevSpeedup
