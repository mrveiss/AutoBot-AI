// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * What the workflow builder does when the company changes under it (#21520).
 *
 * The builder opts out of the layout's remount (`meta.keepOnCompanySwitch`, #21502), so its
 * instance survives a switch. Left alone it would keep showing the previous company's lists while
 * ApiClient sends the NEW company header on the next Save or Start. On a switch this therefore
 * (1) drops the unsaved draft, because it was composed for the previous company, (2) reloads the
 * builder's data in place, and (3) tells the user when a draft was dropped.
 *
 * The draft is discarded rather than re-bound: the natural-language goal, plan, pending approval
 * and canvas nodes were written against one company's context, and carrying them over would let
 * a Save or Start land under a company the user never composed them for.
 */
import { watch, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useWorkflowCompanySwitch')

/** The refs that make up the unsaved draft; the builder owns them, this only reads and clears them. */
export interface WorkflowDraftRefs {
  naturalLanguageInput: Ref<string>
  selectedStrategy: Ref<string>
  workflowPlan: Ref<unknown | null>
  pendingApproval: Ref<unknown | null>
  currentWorkflow: Ref<unknown | null>
  workflowNodes: Ref<unknown[]>
  selectedNodeId: Ref<string | null>
}

/** Clears the draft; returns true when there was anything to clear. */
export function discardWorkflowDraft(d: WorkflowDraftRefs): boolean {
  const hadDraft =
    d.naturalLanguageInput.value.trim() !== '' ||
    d.selectedStrategy.value !== '' ||
    d.workflowPlan.value !== null ||
    d.pendingApproval.value !== null ||
    d.currentWorkflow.value !== null ||
    d.workflowNodes.value.length > 0
  d.naturalLanguageInput.value = ''
  d.selectedStrategy.value = ''
  d.workflowPlan.value = null
  d.pendingApproval.value = null
  d.currentWorkflow.value = null
  d.workflowNodes.value = []
  d.selectedNodeId.value = null
  return hadDraft
}

export interface WorkflowCompanySwitchOptions {
  /** The company the route names ('' when none). */
  companyId: () => string
  draft: WorkflowDraftRefs
  /** Reloads the builder's company data in place. */
  reload: () => Promise<void>
  /** Called after a non-empty draft was dropped, to tell the user. */
  onDraftDiscarded: () => void
}

export function useWorkflowCompanySwitch(opts: WorkflowCompanySwitchOptions) {
  return watch(opts.companyId, async (next, previous) => {
    // First resolution of the id (previous '') is a load, not a switch: onMounted handles it.
    if (!previous || !next || next === previous) return
    const hadDraft = discardWorkflowDraft(opts.draft)
    try {
      await opts.reload()
    } catch (err) {
      logger.error('Reloading the workflow builder after a company switch failed', err)
    }
    if (hadDraft) opts.onDraftDiscarded()
  })
}
