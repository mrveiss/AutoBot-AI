// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useCollaborationInvite
 *
 * Issue #6091: Extract inline apiClient calls from InviteUserDialog into composable.
 *
 * Handles fetching the caller's organisation members from the scoped user search API for the invite dialog.
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

/** `GET /user-management/users/search` response: the caller's own organisation only. */
interface UserSearchResponse {
  users: Array<{
    id: string
    name: string
    type: string
  }>
  available: boolean
  message?: string
}

/** Server-side cap on the search route's `limit`. */
const SEARCH_LIMIT = 50

export function useCollaborationInvite() {
  const users = ref<CollaborationUser[]>([])
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)

  const fetchUsers = async (failureMessage: string): Promise<void> => {
    loading.value = true
    errorMessage.value = null

    try {
      const response = await apiClient.get<UserSearchResponse>(
        `${getApiBase()}/user-management/users/search?q=&limit=${SEARCH_LIMIT}`
      )

      if (response && response.available !== false && Array.isArray(response.users)) {
        users.value = response.users.map(user => ({
          id: user.id,
          username: user.name,
          email: '',
          avatar: null,
          display_name: user.name
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
