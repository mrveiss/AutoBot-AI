// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Status refreshes for the Workflow Builder that must not replace the wrong workflow (#21033).
 *
 * - `refreshAfterAnswer`: the re-read after a step answer. It goes through `refreshIfDisplayed`, so a
 *   slow reply for workflow A never replaces the displayed workflow B. The request still runs for a
 *   workflow that is not displayed, because it is what releases that step's answer lock.
 * - `restoreWaitingWorkflow`: after a reload with no `workflow` query nothing is displayed, so no
 *   approval card renders. The first active workflow (list order) with a `waiting_approval` step is
 *   displayed, but only while nothing has been displayed by the time its status arrives.
 */
import type { Ref } from 'vue';
import { refreshIfDisplayed } from '@/composables/useWorkflowSocketNotices';

type Status<W> = { success: boolean; data?: { workflow: W } | null };
interface Listed { workflow_id: string; steps?: Array<{ status: string }> }

export interface StatusRefreshDeps<W extends Listed> {
  currentWorkflow: Ref<W | null>;
  activeWorkflows: Ref<W[]>;
  /** One status request, through the answer-lock bookkeeping. */
  fetchStatus: (workflowId: string) => Promise<Status<W>>;
}

export function useWorkflowStatusRefresh<W extends Listed>(deps: StatusRefreshDeps<W>) {
  const { currentWorkflow, activeWorkflows, fetchStatus } = deps;

  /** Resolves true when the status was read (the refresh succeeded), whether or not it was displayed. */
  async function refreshAfterAnswer(workflowId: string): Promise<boolean> {
    let read = false;
    const tracked = async (id: string) => {
      const response = await fetchStatus(id);
      read = response.success && !!response.data;
      return response;
    };
    if (currentWorkflow.value?.workflow_id === workflowId) await refreshIfDisplayed(currentWorkflow, workflowId, tracked);
    else await tracked(workflowId);
    return read;
  }

  /** Read one workflow's status and display it; null when the read failed. */
  async function readStatus(workflowId: string): Promise<W | null> {
    const response = await fetchStatus(workflowId);
    if (!response.success || !response.data) return null;
    currentWorkflow.value = response.data.workflow;
    return response.data.workflow;
  }

  async function restoreWaitingWorkflow(): Promise<void> {
    if (currentWorkflow.value) return;
    const waiting = activeWorkflows.value.find((wf) => wf.steps?.some((s) => s.status === 'waiting_approval'));
    if (!waiting) return;
    const response = await fetchStatus(waiting.workflow_id);
    if (!response.success || !response.data || currentWorkflow.value) return;
    currentWorkflow.value = response.data.workflow;
  }

  return { readStatus, refreshAfterAnswer, restoreWaitingWorkflow };
}
