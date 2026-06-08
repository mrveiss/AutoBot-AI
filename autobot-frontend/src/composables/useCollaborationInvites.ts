// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useCollaborationInvites
 *
 * Issue #6091: Extract inline fetching from InviteUserDialog to composable.
 *
 * Handles fetching users from the user-management API for the invite dialog.
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

export function useCollaborationInvites() {
  const errorMessage = ref<string | null>(null)

  const endpoint = useFetchEndpoint<UserListResponse, CollaborationUser[]>({
    path: '/api/user-management/users',
    label: 'fetchCollaborationUsers',
    pickData: (raw) => {
      if (!raw || !Array.isArray(raw.users)) {
        logger.warn('Invalid response structure from users API', raw)
        return null
      }
      return raw.users.map(user => ({
        id: user.id,
        username: user.username,
        email: user.email,
        avatar: user.avatar_url ?? null,
        display_name: user.display_name,
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
    await endpoint.load({ limit: '100', offset: '0', include_inactive: 'false' })
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
