// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useCollaborationInvite
 *
 * Issue #6091: Extract inline apiClient calls from InviteUserDialog into composable.
 *
 * Handles fetching users from the user-management API for the invite dialog.
 */

import { ref } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCollaborationInvite')

export interface CollaborationUser {
  id: string
  username: string
  email: string
  avatar: string | null
  display_name?: string
}

interface UserListResponse {
  users: Array<{
    id: string
    username: string
    email: string
    display_name?: string
    avatar_url?: string
  }>
  total: number
  limit: number
  offset: number
}

export function useCollaborationInvite() {
  const users = ref<CollaborationUser[]>([])
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)

  const fetchUsers = async (failureMessage: string): Promise<void> => {
    loading.value = true
    errorMessage.value = null

    try {
      const response = await apiClient.get<UserListResponse>(
        `${getApiBase()}/user-management/users?limit=100&offset=0&include_inactive=false`
      )

      if (response && response.users && Array.isArray(response.users)) {
        users.value = response.users.map(user => ({
          id: user.id,
          username: user.username,
          email: user.email,
          avatar: user.avatar_url || null,
          display_name: user.display_name
        }))
        logger.debug(`Loaded ${users.value.length} users from API`)
      } else {
        logger.warn('Invalid response structure from users API', response)
        errorMessage.value = failureMessage
      }
    } catch (error) {
      logger.error('Failed to fetch users:', error)
      errorMessage.value = error instanceof Error ? error.message : failureMessage
    } finally {
      loading.value = false
    }
  }

  return {
    users,
    loading,
    errorMessage,
    fetchUsers
  }
}
