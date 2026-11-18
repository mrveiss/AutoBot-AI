// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Company-scoped workflow list reads for the builder (#21520).
 *
 * The builder survives a company switch, so a read started for the previous company can resolve
 * after the current company's read. Each read claims ownership (useLatestRequest, #21159) and only
 * the owner may write its list; `invalidate()` revokes every in-flight read on a company switch.
 * A read that was superseded is not a failure; one that hit an HTTP error or threw is (returns false).
 */
import type { Ref } from 'vue'
import type { ApiResponse } from '@/types/api'
import { createLogger } from '@/utils/debugUtils'
import { useLatestRequest } from '@/composables/useLatestRequest'

const logger = createLogger('useWorkflowListLoaders')

type WorkflowList<W> = ApiResponse<{ workflows: W[] }>

export interface WorkflowListLoadersOptions<W extends { workflow_id: string }> {
  activeWorkflows: Ref<W[]>
  completedWorkflows: Ref<W[]>
  fetchActive: () => Promise<WorkflowList<W>>
  fetchCompleted: () => Promise<WorkflowList<W>>
  /** Runs the read under the builder's loading flag. */
  wrap: <T>(fn: () => Promise<T>) => Promise<T>
  forgetRemoved: (previous: ReadonlyArray<W>, next: ReadonlyArray<W>) => void
  /** Re-opens a waiting approval after an active-list reload (#21033). */
  restoreWaiting: () => Promise<unknown>
}

export function useWorkflowListLoaders<W extends { workflow_id: string }>(o: WorkflowListLoadersOptions<W>) {
  const active = useLatestRequest()
  const completed = useLatestRequest()

  /** Returns false when the list could not be loaded (HTTP error or throw). */
  async function loadActive(): Promise<boolean> {
    const token = active.begin()
    const ok = await o.wrap(async () => {
      const response = await o.fetchActive()
      if (!active.isCurrent(token)) return true // superseded: a newer read owns the list
      if (response.success && response.data) {
        o.forgetRemoved(o.activeWorkflows.value, response.data.workflows)
        o.activeWorkflows.value = response.data.workflows
        return true
      }
      logger.warn('Active workflows unavailable:', response.error)
      return false
    })
    if (active.isCurrent(token)) await o.restoreWaiting()
    return ok
  }

  async function loadCompleted(): Promise<boolean> {
    const token = completed.begin()
    const response = await o.fetchCompleted()
    if (!completed.isCurrent(token)) return true
    if (response.success && response.data) {
      o.completedWorkflows.value = response.data.workflows
      return true
    }
    logger.warn('Completed workflows unavailable:', response.error)
    return false
  }

  /** Revoke every in-flight read: a company switch makes their rows foreign. */
  function invalidate(): void {
    active.invalidate()
    completed.invalidate()
  }

  return { loadActive, loadCompleted, invalidate }
}
