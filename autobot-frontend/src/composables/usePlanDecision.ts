// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Approve / reject handlers for the plan-approval envelope (#20853).
 *
 * `deciding` is true from the first click until the request settles; a decision made while
 * one is in flight is not sent. A thrown request counts as a failed decision (error toast).
 */
import { ref, type Ref } from 'vue'

interface PendingPlan {
  workflow_id: string
}

export interface PlanDecisionDeps {
  pendingApproval: Ref<PendingPlan | null | undefined>
  approvePlan: (workflowId: string) => Promise<boolean>
  rejectPlan: (workflowId: string, reason: string) => Promise<boolean>
  notify: (key: string, kind: 'success' | 'info' | 'error') => void
  onApproved: () => void
}

export function usePlanDecision(deps: PlanDecisionDeps) {
  const deciding = ref(false)

  async function decide(send: (workflowId: string) => Promise<boolean>): Promise<boolean | null> {
    const plan = deps.pendingApproval.value
    if (!plan || deciding.value) return null
    deciding.value = true
    try {
      return await send(plan.workflow_id)
    } catch {
      return false
    } finally {
      deciding.value = false
    }
  }

  async function handleApprovePlan(): Promise<void> {
    const success = await decide((id) => deps.approvePlan(id))
    if (success === null) return
    if (!success) return deps.notify('workflow.builder.planApproveFailed', 'error')
    deps.notify('workflow.builder.planApproved', 'success')
    deps.onApproved()
  }

  async function handleRejectPlan(): Promise<void> {
    const success = await decide((id) => deps.rejectPlan(id, 'User rejected'))
    if (success === null) return
    if (!success) return deps.notify('workflow.builder.planRejectFailed', 'error')
    deps.notify('workflow.builder.planRejected', 'info')
  }

  return { deciding, handleApprovePlan, handleRejectPlan }
}
