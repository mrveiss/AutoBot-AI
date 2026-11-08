// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useCollaborationInvites
 *
 * Issue #6091: Extract inline fetching from InviteUserDialog to composable.
 *
 * Handles fetching the caller's organisation members from the scoped user search API for the invite dialog.
 * Uses useFetchEndpoint (Pattern A) for GET reads — provides AbortController,
 * race-condition safety, and abort-on-unmount automatically.
 */

import { ref, computed } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCollaborationInvites')

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
const SEARCH_LIMIT = '50'

export function useCollaborationInvites() {
  const errorMessage = ref<string | null>(null)

  const endpoint = useFetchEndpoint<UserSearchResponse, CollaborationUser[]>({
    path: '/api/user-management/users/search',
    label: 'fetchCollaborationUsers',
    pickData: (raw) => {
      if (!raw || raw.available === false || !Array.isArray(raw.users)) {
        logger.warn('Invalid response structure from users API', raw)
        return null
      }
      return raw.users.map(user => ({
        id: user.id,
        username: user.name,
        email: '',
        avatar: null,
        display_name: user.name,
      }))
    },
    onError: (message) => {
      logger.error('Failed to fetch collaboration users:', message)
      errorMessage.value = message
    },
    onNoData: () => {
      logger.warn('No users returned from API')
    },
  })

  const users = computed(() => endpoint.data.value ?? [])

  async function fetchUsers(failureMessage: string): Promise<void> {
    errorMessage.value = null
    await endpoint.load({ q: '', limit: SEARCH_LIMIT })
    // onError fires with the raw network message; override with i18n copy when provided
    if (endpoint.error.value && failureMessage) {
      errorMessage.value = failureMessage
    }
  }

  return {
    users,
    loading: endpoint.loading,
    errorMessage,
    fetchUsers,
  }
}
