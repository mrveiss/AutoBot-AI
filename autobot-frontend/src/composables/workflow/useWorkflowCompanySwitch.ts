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
 * (1) drops the unsaved draft, because it was composed for the previous company, (2) tells the user
 * at once when a draft was dropped (independent of the reload, so a quick second switch cannot
 * swallow the notice), and (3) reloads the builder's data in place, reporting a failed reload
 * separately from the discard.
 *
 * The draft is discarded rather than re-bound: the natural-language goal, plan, pending approval
 * and canvas nodes were written against one company's context, and carrying them over would let
 * a Save or Start land under a company the user never composed them for.
 */
import { watch, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useLatestRequest } from '@/composables/useLatestRequest'
import { getSelectedCompanyId } from '@/utils/orgContext'

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
  // currentWorkflow is the runner's selection of a SAVED workflow, not an edit: cleared, never counted.
  const hadDraft =
    d.naturalLanguageInput.value.trim() !== '' ||
    d.selectedStrategy.value !== '' ||
    d.workflowPlan.value !== null ||
    d.pendingApproval.value !== null ||
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

/**
 * False while the sidebar has changed the selected company but the route has not followed yet: a request
 * sent in that window carries the NEW company's X-Organization-Id for a goal composed for the OLD one.
 * Either side unset is not a conflict (no header is sent without a selection).
 */
export function companyContextAgrees(routeCompanyId: string): boolean {
  const selected = getSelectedCompanyId()
  return !routeCompanyId || !selected || routeCompanyId === selected
}

/**
 * Wraps a builder action so it runs only while `agrees()` holds (#21520); otherwise it is skipped and
 * resolves undefined (the wrapper stays a Promise-returning function, so it still satisfies callers
 * that await the action). `agrees` is where the user is told, so every gated handler shares one refusal.
 */
export function gateOnCompany<A extends unknown[], R>(agrees: () => boolean, fn: (...args: A) => Promise<R>): (...args: A) => Promise<R | undefined> {
  return (...args) => (agrees() ? fn(...args) : Promise.resolve(undefined))
}

export interface WorkflowCompanySwitchOptions {
  /** The company the route names ('' when none). */
  companyId: () => string
  draft: WorkflowDraftRefs
  /** Reloads the builder's company data in place; resolves false when a load reported failure. */
  reload: () => Promise<void | boolean>
  /** Called as soon as a non-empty draft was dropped, to tell the user. */
  onDraftDiscarded: () => void
  /** Called when the reload for the company now shown failed (rejected, or resolved false). */
  onReloadFailed?: () => void
  /**
   * Synchronous reset of everything else company-scoped, run on every switch before the reload:
   * revoke in-flight create/plan requests, rotate the session id, re-key the workflow socket, clear
   * fetched lists. Anything company-independent (e.g. a UI preference) is deliberately left alone.
   */
  onSwitch?: () => void
}

export function useWorkflowCompanySwitch(opts: WorkflowCompanySwitchOptions) {
  // Latest switch owns the lists (#21159 pattern, useLatestRequest).
  const switches = useLatestRequest()
  /** True when the reload completed without a failure. */
  async function safeReload(): Promise<boolean> {
    try {
      return (await opts.reload()) !== false
    } catch (err) {
      logger.error('Reloading the workflow builder after a company switch failed', err)
      return false
    }
  }
  return watch(opts.companyId, async (next, previous) => {
    // First resolution of the id (previous '') is a load, not a switch: onMounted handles it.
    if (!previous || !next || next === previous) return
    const token = switches.begin()
    const hadDraft = discardWorkflowDraft(opts.draft)
    opts.onSwitch?.()
    if (hadDraft) opts.onDraftDiscarded() // now, not after the reload: a newer switch may preempt it
    const ok = await safeReload()
    if (!switches.isCurrent(token)) {
      // A newer switch began while this reload was in flight. Lists are ownership-guarded, but the
      // other loaders are not, so fetch once more for the company now shown; the newer switch reports.
      if (!(await safeReload())) opts.onReloadFailed?.()
      return
    }
    if (!ok) opts.onReloadFailed?.()
  })
}
