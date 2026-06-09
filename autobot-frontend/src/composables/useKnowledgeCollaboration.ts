// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Knowledge Collaboration Composable
 *
 * Issue #679: API client for hierarchical knowledge access control.
 */

import { ref, computed } from 'vue'
import { ApiClient } from '@/utils/ApiClient'
import { extractErrorMessage } from '@/utils/errorExtract'
import { useLoadingState } from '@/composables/useLoadingState'

export interface KnowledgeScope {
  scope: string
  description: string
}

export interface KnowledgeFact {
  id: string
  content: string
  title: string
  visibility: string
  metadata: Record<string, unknown>
}

export interface ShareRequest {
  user_ids?: string[]
  group_ids?: string[]
}

export interface PermissionsRequest {
  visibility: string
  organization_id?: string
  group_ids?: string[]
}

export interface AccessInfo {
  fact_id: string
  owner_id: string
  visibility: string
  organization_id?: string
  group_ids: string[]
  shared_with: string[]
  can_edit: boolean
  can_share: boolean
  can_delete: boolean
  has_access: boolean
}

export interface ScopedSearchOptions {
  top_k?: number
  mode?: string
  category?: string
  tags?: string[]
  min_score?: number
  enable_rag?: boolean
  enable_reranking?: boolean
}

export interface ScopedSearchResult {
  results: unknown[]
  total: number
}

export function useKnowledgeCollaboration() {
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  const apiClient = new ApiClient()

  const getFactsByScope = async (
    scope?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number; total: number }> => {
    error.value = null
    return wrap(async () => {
      try {
        const params = new URLSearchParams({
          limit: limit.toString(),
          offset: offset.toString(),
        })

        if (scope) {
          params.append('scope', scope)
        }

        const response = await apiClient.get<{ facts: KnowledgeFact[]; count: number; total: number }>(
          `/knowledge/collaboration/facts?${params.toString()}`
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to fetch facts')
        throw err
      }
    })
  }

  const getOrganizationFacts = async (
    organizationId: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number }> => {
    error.value = null
    return wrap(async () => {
      try {
        const params = new URLSearchParams({
          limit: limit.toString(),
          offset: offset.toString(),
        })

        const response = await apiClient.get<{ facts: KnowledgeFact[]; count: number }>(
          `/knowledge/collaboration/facts/organization/${organizationId}?${params.toString()}`
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to fetch organization facts')
        throw err
      }
    })
  }

  const getGroupFacts = async (
    groupId: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number }> => {
    error.value = null
    return wrap(async () => {
      try {
        const params = new URLSearchParams({
          limit: limit.toString(),
          offset: offset.toString(),
        })

        const response = await apiClient.get<{ facts: KnowledgeFact[]; count: number }>(
          `/knowledge/collaboration/facts/group/${groupId}?${params.toString()}`
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to fetch group facts')
        throw err
      }
    })
  }

  const shareKnowledge = async (
    factId: string,
    shareRequest: ShareRequest
  ): Promise<Record<string, unknown>> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.post<Record<string, unknown>>(
          `/knowledge/collaboration/facts/${factId}/share`,
          shareRequest
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to share knowledge')
        throw err
      }
    })
  }

  const unshareKnowledge = async (
    factId: string,
    entityId: string,
    entityType: 'user' | 'group'
  ): Promise<Record<string, unknown>> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.delete<Record<string, unknown>>(
          `/knowledge/collaboration/facts/${factId}/share/${entityId}?entity_type=${entityType}`
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to unshare knowledge')
        throw err
      }
    })
  }

  const updatePermissions = async (
    factId: string,
    permissionsRequest: PermissionsRequest
  ): Promise<Record<string, unknown>> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.put<Record<string, unknown>>(
          `/knowledge/collaboration/facts/${factId}/permissions`,
          permissionsRequest
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to update permissions')
        throw err
      }
    })
  }

  const getAccessInfo = async (factId: string): Promise<AccessInfo> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.get<AccessInfo>(
          `/knowledge/collaboration/facts/${factId}/access`
        )

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to get access information')
        throw err
      }
    })
  }

  const getAccessibleScopes = async (): Promise<{
    user_id: string
    organization_id?: string
    group_count: number
    accessible_scopes: KnowledgeScope[]
  }> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.get<{
          user_id: string
          organization_id?: string
          group_count: number
          accessible_scopes: KnowledgeScope[]
        }>('/knowledge/search/accessible-scopes')

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Failed to get accessible scopes')
        throw err
      }
    })
  }

  const scopedSearch = async (
    query: string,
    options: ScopedSearchOptions = {}
  ): Promise<ScopedSearchResult> => {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.post<ScopedSearchResult>('/knowledge/search/scoped', {
          query,
          top_k: options.top_k || 10,
          mode: options.mode || 'hybrid',
          category: options.category,
          tags: options.tags,
          min_score: options.min_score || 0.0,
          enable_rag: options.enable_rag || false,
          enable_reranking: options.enable_reranking || false,
        })

        return response
      } catch (err: unknown) {
        error.value = extractErrorMessage(err, 'Search failed')
        throw err
      }
    })
  }

  return {
    loading,
    error: computed(() => error.value),
    getFactsByScope,
    getOrganizationFacts,
    getGroupFacts,
    shareKnowledge,
    unshareKnowledge,
    updatePermissions,
    getAccessInfo,
    getAccessibleScopes,
    scopedSearch,
  }
}
