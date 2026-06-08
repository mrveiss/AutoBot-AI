// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Marketplace Sources Composable
 * Issue #6481 - User-extensible plugin marketplace sources.
 */

import { ref } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useMarketplaceSources')

export interface MarketplaceSource {
  id: string
  name: string
  url: string | null
  description: string | null
  is_builtin: boolean
  created_at: string | null
}

interface ListResponse { sources: MarketplaceSource[] }

export function useMarketplaceSources() {
  const sources = ref<MarketplaceSource[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function listSources(): Promise<void> {
    error.value = null
    loading.value = true
    try {
      const data = await ApiClient.get<any>(`${getApiBase()}/marketplace-sources`) as ListResponse
      sources.value = data.sources ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to list marketplace sources'
      error.value = msg
      logger.error('listSources error: %s', msg)
    } finally {
      loading.value = false
    }
  }

  async function addSource(payload: { name: string; url: string; description?: string }): Promise<MarketplaceSource | null> {
    error.value = null
    try {
      const data = await ApiClient.post<any>(
        `${getApiBase()}/marketplace-sources`,
        payload,
      ) as MarketplaceSource
      await listSources()
      return data
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add marketplace source'
      error.value = msg
      logger.error('addSource error: %s', msg)
      return null
    }
  }

  async function deleteSource(id: string): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.delete<any>(`${getApiBase()}/marketplace-sources/${id}`)
      await listSources()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to remove marketplace source'
      error.value = msg
      logger.error('deleteSource error: %s', msg)
      return false
    }
  }

  return {
    sources,
    loading,
    error,
    listSources,
    addSource,
    deleteSource,
  }
}
