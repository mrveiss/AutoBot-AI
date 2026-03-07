// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Approval Gates Composable (#1402)
 *
 * Reactive state and API methods for workflow approval gates.
 */

import { computed, ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useApprovalGates')

export interface ApprovalComment {
  id: string
  approval_id: string
  author: string
  author_type: string
  body: string
  created_at: string | null
}

export interface TaskApprovalLink {
  id: string
  approval_id: string
  task_id: string
  task_type: string
}

export interface Approval {
  id: string
  title: string
  description: string | null
  approval_type: string
  status: string
  requested_by_agent: string | null
  decided_by_user: string | null
  workflow_id: string | null
  workflow_step: string | null
  context: Record<string, unknown> | null
  decided_at: string | null
  created_at: string | null
  updated_at: string | null
  comments: ApprovalComment[]
  task_links: TaskApprovalLink[]
}

export interface CreateApprovalPayload {
  title: string
  approval_type: string
  description?: string
  requested_by_agent?: string
  workflow_id?: string
  workflow_step?: string
  context?: Record<string, unknown>
  task_ids?: string[]
}

export function useApprovalGates() {
  const approvals = ref<Approval[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const pendingApprovals = computed(() =>
    approvals.value.filter((a) => a.status === 'pending')
  )

  const pendingCount = computed(() => pendingApprovals.value.length)

  // -- API helpers ----------------------------------------------------

  async function apiGet<T>(path: string): Promise<T> {
    const url = await appConfig.getApiUrl(path)
    const res = await fetchWithAuth(url)
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`GET ${path} failed (${res.status}): ${text}`)
    }
    return res.json()
  }

  async function apiPost<T>(
    path: string,
    body: Record<string, unknown>
  ): Promise<T> {
    const url = await appConfig.getApiUrl(path)
    const res = await fetchWithAuth(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`POST ${path} failed (${res.status}): ${text}`)
    }
    return res.json()
  }

  async function apiDelete(path: string): Promise<void> {
    const url = await appConfig.getApiUrl(path)
    const res = await fetchWithAuth(url, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) {
      const text = await res.text()
      throw new Error(`DELETE ${path} failed (${res.status}): ${text}`)
    }
  }

  // -- CRUD -----------------------------------------------------------

  async function fetchApprovals(params?: {
    status?: string
    approval_type?: string
    workflow_id?: string
    agent_id?: string
    limit?: number
    offset?: number
  }): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const query = new URLSearchParams()
      if (params?.status) query.set('status_filter', params.status)
      if (params?.approval_type)
        query.set('approval_type', params.approval_type)
      if (params?.workflow_id)
        query.set('workflow_id', params.workflow_id)
      if (params?.agent_id) query.set('agent_id', params.agent_id)
      if (params?.limit) query.set('limit', String(params.limit))
      if (params?.offset) query.set('offset', String(params.offset))

      const qs = query.toString()
      const path = `/api/approval-gates${qs ? '?' + qs : ''}`
      approvals.value = await apiGet<Approval[]>(path)
    } catch (e) {
      error.value = (e as Error).message
      logger.error('Failed to fetch approvals:', e)
    } finally {
      loading.value = false
    }
  }

  async function getApproval(id: string): Promise<Approval | null> {
    try {
      return await apiGet<Approval>(`/api/approval-gates/${id}`)
    } catch (e) {
      logger.error('Failed to get approval:', e)
      return null
    }
  }

  async function createApproval(
    payload: CreateApprovalPayload
  ): Promise<Approval | null> {
    try {
      const approval = await apiPost<Approval>(
        '/api/approval-gates',
        payload as unknown as Record<string, unknown>
      )
      approvals.value.unshift(approval)
      return approval
    } catch (e) {
      logger.error('Failed to create approval:', e)
      error.value = (e as Error).message
      return null
    }
  }

  // -- Transitions ----------------------------------------------------

  async function approve(
    id: string,
    comment?: string
  ): Promise<Approval | null> {
    try {
      const result = await apiPost<Approval>(
        `/api/approval-gates/${id}/approve`,
        { comment }
      )
      _updateLocal(result)
      return result
    } catch (e) {
      logger.error('Failed to approve:', e)
      error.value = (e as Error).message
      return null
    }
  }

  async function reject(
    id: string,
    comment?: string
  ): Promise<Approval | null> {
    try {
      const result = await apiPost<Approval>(
        `/api/approval-gates/${id}/reject`,
        { comment }
      )
      _updateLocal(result)
      return result
    } catch (e) {
      logger.error('Failed to reject:', e)
      error.value = (e as Error).message
      return null
    }
  }

  async function requestRevision(
    id: string,
    comment?: string
  ): Promise<Approval | null> {
    try {
      const result = await apiPost<Approval>(
        `/api/approval-gates/${id}/request-revision`,
        { comment }
      )
      _updateLocal(result)
      return result
    } catch (e) {
      logger.error('Failed to request revision:', e)
      error.value = (e as Error).message
      return null
    }
  }

  async function resubmit(
    id: string,
    description?: string,
    context?: Record<string, unknown>
  ): Promise<Approval | null> {
    try {
      const result = await apiPost<Approval>(
        `/api/approval-gates/${id}/resubmit`,
        { description, context }
      )
      _updateLocal(result)
      return result
    } catch (e) {
      logger.error('Failed to resubmit:', e)
      error.value = (e as Error).message
      return null
    }
  }

  // -- Comments & tasks -----------------------------------------------

  async function addComment(
    approvalId: string,
    body: string,
    authorType = 'human'
  ): Promise<ApprovalComment | null> {
    try {
      return await apiPost<ApprovalComment>(
        `/api/approval-gates/${approvalId}/comments`,
        { body, author_type: authorType }
      )
    } catch (e) {
      logger.error('Failed to add comment:', e)
      return null
    }
  }

  async function linkTask(
    approvalId: string,
    taskId: string,
    taskType = 'github_issue'
  ): Promise<TaskApprovalLink | null> {
    try {
      return await apiPost<TaskApprovalLink>(
        `/api/approval-gates/${approvalId}/tasks`,
        { task_id: taskId, task_type: taskType }
      )
    } catch (e) {
      logger.error('Failed to link task:', e)
      return null
    }
  }

  async function unlinkTask(
    approvalId: string,
    taskId: string
  ): Promise<boolean> {
    try {
      await apiDelete(
        `/api/approval-gates/${approvalId}/tasks/${taskId}`
      )
      return true
    } catch (e) {
      logger.error('Failed to unlink task:', e)
      return false
    }
  }

  // -- Internal -------------------------------------------------------

  function _updateLocal(updated: Approval): void {
    const idx = approvals.value.findIndex((a) => a.id === updated.id)
    if (idx >= 0) {
      approvals.value[idx] = updated
    }
  }

  return {
    // State
    approvals,
    loading,
    error,
    pendingApprovals,
    pendingCount,

    // CRUD
    fetchApprovals,
    getApproval,
    createApproval,

    // Transitions
    approve,
    reject,
    requestRevision,
    resubmit,

    // Comments & tasks
    addComment,
    linkTask,
    unlinkTask,
  }
}
