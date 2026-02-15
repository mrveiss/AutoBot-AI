/**
 * Knowledge Collaboration Composable
 *
 * Issue #679: API client for hierarchical knowledge access control.
 */

import { ref, computed } from 'vue'
import { ApiClient } from '@/utils/ApiClient'

export interface KnowledgeScope {
  scope: string
  description: string
}

export interface KnowledgeFact {
  id: string
  content: string
  title: string
  visibility: string
  metadata: Record<string, any>
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

export function useKnowledgeCollaboration() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const apiClient = new ApiClient()

  /**
   * Get facts filtered by scope
   */
  const getFactsByScope = async (
    scope?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number; total: number }> => {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      })

      if (scope) {
        params.append('scope', scope)
      }

      const response = await apiClient.get(
        `/knowledge/collaboration/facts?${params.toString()}`
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch facts'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get facts for a specific organization
   */
  const getOrganizationFacts = async (
    organizationId: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number }> => {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      })

      const response = await apiClient.get(
        `/knowledge/collaboration/facts/organization/${organizationId}?${params.toString()}`
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch organization facts'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get facts for a specific group/team
   */
  const getGroupFacts = async (
    groupId: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ facts: KnowledgeFact[]; count: number }> => {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      })

      const response = await apiClient.get(
        `/knowledge/collaboration/facts/group/${groupId}?${params.toString()}`
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to fetch group facts'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Share a knowledge fact with users and/or groups
   */
  const shareKnowledge = async (
    factId: string,
    shareRequest: ShareRequest
  ): Promise<any> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.post(
        `/knowledge/collaboration/facts/${factId}/share`,
        shareRequest
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to share knowledge'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Revoke access from a user or group
   */
  const unshareKnowledge = async (
    factId: string,
    entityId: string,
    entityType: 'user' | 'group'
  ): Promise<any> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.delete(
        `/knowledge/collaboration/facts/${factId}/share/${entityId}?entity_type=${entityType}`
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to unshare knowledge'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Update knowledge permissions
   */
  const updatePermissions = async (
    factId: string,
    permissionsRequest: PermissionsRequest
  ): Promise<any> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.put(
        `/knowledge/collaboration/facts/${factId}/permissions`,
        permissionsRequest
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to update permissions'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get access information for a fact
   */
  const getAccessInfo = async (factId: string): Promise<AccessInfo> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.get(
        `/knowledge/collaboration/facts/${factId}/access`
      )

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to get access information'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get accessible scopes for the current user
   */
  const getAccessibleScopes = async (): Promise<{
    user_id: string
    organization_id?: string
    group_count: number
    accessible_scopes: KnowledgeScope[]
  }> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.get('/knowledge/search/accessible-scopes')

      return response
    } catch (err: any) {
      error.value = err.message || 'Failed to get accessible scopes'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Perform scoped search
   */
  const scopedSearch = async (
    query: string,
    options: {
      top_k?: number
      mode?: string
      category?: string
      tags?: string[]
      min_score?: number
      enable_rag?: boolean
      enable_reranking?: boolean
    } = {}
  ): Promise<any> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiClient.post('/knowledge/search/scoped', {
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
    } catch (err: any) {
      error.value = err.message || 'Search failed'
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading: computed(() => loading.value),
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
