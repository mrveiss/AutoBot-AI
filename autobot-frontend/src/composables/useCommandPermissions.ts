// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * useCommandPermissions
 *
 * Encapsulates all HTTP fetching for CommandPermissionDialog:
 *   - approveOrDeny:   POST /agent-terminal/sessions/{id}/approve  (allow/deny)
 *   - postComment:     POST /chat/direct  (feedback comment)
 *
 * Both mutations use apiClient.post wrapped in useLoadingState so the
 * dialog only wires one composable instead of managing two loading refs.
 *
 * Issue #6088: extract inline fetching from CommandPermissionDialog.
 */

import { ref, computed } from 'vue'
import type { Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { useLoadingState } from '@/composables/useLoadingState'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useCommandPermissions')

export interface ApproveResult {
  status: string
  error?: string
  [key: string]: unknown
}

export function useCommandPermissions() {
  const { isLoading: isApproving, wrap: wrapApprove } = useLoadingState()
  const { isLoading: isCommenting, wrap: wrapComment } = useLoadingState()

  const errorApprove = ref<Error | null>(null)
  const errorComment = ref<Error | null>(null)

  const isProcessing: Ref<boolean> = computed(() => isApproving.value || isCommenting.value)
  const error: Ref<Error | null> = computed(() => errorApprove.value ?? errorComment.value)

  /**
   * POST /agent-terminal/sessions/{terminalSessionId}/approve
   * Returns the raw response object so the caller can inspect status.
   */
  const approveOrDeny = async (
    terminalSessionId: string,
    approved: boolean,
    userId = 'web_user'
  ): Promise<ApproveResult> => {
    errorApprove.value = null
    return wrapApprove(async () => {
      const result = await apiClient.post<any>(
        `${getApiBase()}/agent-terminal/sessions/${terminalSessionId}/approve`,
        { approved, user_id: userId }
      ) as ApproveResult
      logger.debug('approveOrDeny response:', { approved, status: result.status })
      return result
    })
  }

  /**
   * POST /chat/direct — submit user feedback comment.
   */
  const postComment = async (
    chatId: string | null | undefined,
    message: string
  ): Promise<unknown> => {
    errorComment.value = null
    return wrapComment(async () => {
      const response = await apiClient.post<any>(`${getApiBase()}/chat/direct`, {
        message,
        chat_id: chatId ?? null
      })
      logger.debug('postComment response received')
      return response
    })
  }

  return {
    isProcessing,
    isApproving,
    isCommenting,
    error,
    errorApprove,
    errorComment,
    approveOrDeny,
    postComment
  }
}
