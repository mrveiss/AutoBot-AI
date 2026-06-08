// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeBrowser Composable
 *
 * Fetching layer extracted from KnowledgeBrowser.vue (#6037).
 * Provides bare imperative API functions for all KB browser endpoints:
 * - main categories listing
 * - categorized facts tree (by_category)
 * - cursor-based entries pagination
 * - folder content search
 * - single fact content retrieval
 *
 * All calls delegate to ApiClient so auth, retries, and error logging
 * are handled centrally. No fetchWithAuth in this file.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

// ==================== Types ====================

export interface MainCategory {
  id: string
  name: string
  description: string
  icon: string
  color: string
  count: number
}

export interface MainCategoriesResponse {
  categories: MainCategory[]
  kb_connected: boolean
}

export interface EntriesPage {
  items: Record<string, unknown>[]
  nextCursor: string
  hasMore: boolean
}

export interface FolderSearchResult {
  results: Record<string, unknown>[]
}

export interface FactContentResponse {
  content: string
  [key: string]: unknown
}

// ==================== Bare imperative API ====================

/**
 * Fetch main KB categories (autobot-documentation, system-knowledge, user-knowledge).
 */
export const fetchMainCategories = (): Promise<MainCategoriesResponse> =>
  apiClient.get<MainCategoriesResponse>(`${getApiBase()}/knowledge_base/categories/main`)

/**
 * Fetch all knowledge facts grouped by category for the browser tree.
 */
export const fetchFactsByCategory = (): Promise<Record<string, unknown>> =>
  apiClient.get<Record<string, unknown>>(`${getApiBase()}/knowledge_base/facts/by_category`)

/**
 * Fetch a paginated page of user knowledge entries.
 * Supports both cursor-based and offset-based backend formats.
 */
export const fetchEntriesPage = async (cursor: string): Promise<EntriesPage> => {
  const params = new URLSearchParams({ limit: '100', cursor: cursor || '0' })
  const data = await apiClient.get<Record<string, unknown>>(
    `${getApiBase()}/knowledge_base/entries?${params}`
  )

  if (data.next_cursor !== undefined) {
    return {
      items: (data.entries as Record<string, unknown>[]) || [],
      nextCursor: (data.next_cursor as string) || '0',
      hasMore: (data.has_more as boolean) || false,
    }
  }

  if (data.offset !== undefined) {
    const total = (data.total as number) || 0
    const currentOffset = (data.offset as number) || 0
    const entries = (data.entries as Record<string, unknown>[]) || []
    const hasMore = currentOffset + entries.length < total
    return {
      items: entries,
      nextCursor: hasMore ? String(currentOffset + entries.length) : '0',
      hasMore,
    }
  }

  return { items: (data.entries as Record<string, unknown>[]) || [], nextCursor: '0', hasMore: false }
}

/**
 * Search a folder's contents by category (used for lazy-loading folder nodes).
 */
export const fetchFolderContents = (category: string): Promise<FolderSearchResult> =>
  apiClient.post<FolderSearchResult>(`${getApiBase()}/knowledge_base/search`, {
    query: '',
    category,
    n_results: 100,
  })

/**
 * Fetch the full content of a single fact by its key.
 */
export const fetchFactContent = (factKey: string): Promise<FactContentResponse> =>
  apiClient.get<FactContentResponse>(`${getApiBase()}/knowledge_base/fact/${factKey}`)
