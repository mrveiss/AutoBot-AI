// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Tool Approval Composable (#4952)
 *
 * Subscribes to APPROVAL_REQUIRED live events emitted by the agent loop
 * whenever a sensitive tool (bash, terminal, etc.) needs user authorization.
 * Exposes the pending approval and a submit function that calls the correct
 * REST endpoint — POST /api/agent-terminal/tools/approve/{approval_id} —
 * so the backend _request_approval() polling loop receives an APPROVAL_RESPONSE.
 *
 * Usage:
 *   const { pendingToolApproval, submitToolApproval, clearToolApproval } = useToolApproval()
 *   // Show dialog when pendingToolApproval is non-null
 *   // Call submitToolApproval(true) to approve, submitToolApproval(false) to deny
 */

import { ref, type Ref, onUnmounted, getCurrentInstance } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useEventBus } from '@/composables/useEventBus'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useToolApproval')

export interface PendingToolApproval {
  /** Stable correlation ID — passed to POST /tools/approve/{approval_id} */
  approval_id: string
  /** Human-readable tool name */
  tool_name: string
  /** Sanitized tool arguments */
  arguments: Record<string, unknown>
  /** Why the agent needs this tool */
  reason: string
  /** low | medium | high | critical */
  risk_level: string
  /** How many seconds until the loop times out waiting */
  timeout_seconds: number
  /** Unix epoch seconds when approval expires — used for drift-free countdown (Issue #5024) */
  deadline_ts?: number
  /** Optional task_id carried from the agent context */
  task_id?: string | null
}

export interface UseToolApprovalReturn {
  /** Non-null when the agent loop is waiting for user authorization */
  pendingToolApproval: Ref<PendingToolApproval | null>
  /** True while the HTTP POST to the approval endpoint is in flight */
  submittingApproval: Ref<boolean>
  /**
   * Send the user's decision to the backend.
   * Calls POST /api/agent-terminal/tools/approve/{approval_id}.
   * Clears pendingToolApproval on success.
   */
  submitToolApproval: (approved: boolean, comment?: string) => Promise<void>
  /** Dismiss the dialog without sending a decision (user closed it). */
  clearToolApproval: () => void
}

export function useToolApproval(): UseToolApprovalReturn {
  const pendingToolApproval = ref<PendingToolApproval | null>(null)
  const submittingApproval = ref(false)
  const { subscribe } = useEventBus()

  // Subscribe to the global channel for APPROVAL_REQUIRED events (#4952).
  // The agent loop publishes on the global channel with EventType.APPROVAL_REQUIRED
  // which serialises to the string "APPROVAL_REQUIRED" in the live_event payload.
  const unsub = subscribe('global', (event) => {
    if (event.event_type !== 'APPROVAL_REQUIRED') return
    const p = event.payload as Record<string, unknown>
    const approval: PendingToolApproval = {
      approval_id: String(p['approval_id'] ?? ''),
      tool_name: String(p['tool_name'] ?? 'unknown'),
      arguments: (p['arguments'] as Record<string, unknown>) ?? {},
      reason: String(p['reason'] ?? ''),
      risk_level: String(p['risk_level'] ?? 'high'),
      timeout_seconds: Number(p['timeout_seconds'] ?? 300),
      task_id: p['task_id'] != null ? String(p['task_id']) : null,
    }
    if (!approval.approval_id) {
      logger.error('APPROVAL_REQUIRED event missing approval_id', event)
      return
    }
    logger.debug('Tool approval required', { approval_id: approval.approval_id, tool: approval.tool_name })
    pendingToolApproval.value = approval
  })

  const submitToolApproval = async (approved: boolean, comment?: string): Promise<void> => {
    const approval = pendingToolApproval.value
    if (!approval) {
      logger.warn('submitToolApproval called with no pending approval')
      return
    }
    submittingApproval.value = true
    try {
      await apiClient.post<any>(
        `${getApiBase()}/agent-terminal/tools/approve/${encodeURIComponent(approval.approval_id)}`,
        { approved, comment: comment ?? null, task_id: approval.task_id ?? null }
      )
      logger.debug('Tool approval submitted', { approval_id: approval.approval_id, approved })
      pendingToolApproval.value = null
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      logger.error('Failed to submit tool approval:', err)
      throw err
    } finally {
      submittingApproval.value = false
    }
  }

  const clearToolApproval = (): void => {
    pendingToolApproval.value = null
  }

  // Auto-cleanup on component unmount
  const instance = getCurrentInstance()
  if (instance) {
    onUnmounted(() => {
      unsub()
    })
  } else {
    logger.warn('useToolApproval: not inside a Vue component, cleanup must be manual')
  }

  return { pendingToolApproval, submittingApproval, submitToolApproval, clearToolApproval }
}

export default useToolApproval
