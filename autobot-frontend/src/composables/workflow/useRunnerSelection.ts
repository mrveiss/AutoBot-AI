// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Select and start handlers for the Workflow Builder runner (#21043).
 *
 * A failed start or a failed select is reported through the notification bus, never silent, and a
 * second Start while one is in flight is ignored. The calls themselves stay in `useWorkflowBuilder`;
 * this only decides what the user is told.
 */
import type { Ref } from 'vue';
import type { ActiveWorkflow } from '@/composables/useWorkflowBuilder';

type Toast = (message: string, type: 'success' | 'error' | 'warning' | 'info') => unknown;

export interface RunnerSelectionDeps {
  t: (key: string) => string;
  showToast: Toast;
  navigateToRunner: () => void;
  activeWorkflows: Ref<ActiveWorkflow[]>;
  currentWorkflow: Ref<ActiveWorkflow | null>;
  executingWorkflow: Ref<boolean>;
  startWorkflow: (workflowId: string) => Promise<boolean>;
  getWorkflowStatus: (workflowId: string) => Promise<ActiveWorkflow | null>;
}

export function useRunnerSelection(deps: RunnerSelectionDeps) {
  let selectSeq = 0;
  let committed: ActiveWorkflow | null = null;
  let inFlight = 0;

  function selectionFailed(): false {
    deps.showToast(deps.t('workflow.builder.selectFailed'), 'error');
    return false;
  }

  /** Fetch the server status; a rejected lookup counts as a failed one. */
  async function fetchStatus(workflowId: string): Promise<ActiveWorkflow | null> {
    inFlight++;
    try {
      return await deps.getWorkflowStatus(workflowId);
    } catch {
      return null;
    } finally {
      inFlight--;
    }
  }

  /**
   * Make *workflowId* the runner's current workflow. A listed entry is shown at once, then the
   * server status replaces it (a listed not-started entry can be stale); the entry stays only when
   * the fetch fails. A lookup that finishes after a newer select never overwrites it.
   */
  async function selectWorkflow(workflowId: string): Promise<boolean> {
    const mine = ++selectSeq;
    if (inFlight === 0) committed = deps.currentWorkflow.value;
    const local = deps.activeWorkflows.value.find((wf) => wf.workflow_id === workflowId);
    if (local) deps.currentWorkflow.value = committed = local;
    const fetched = await fetchStatus(workflowId);
    if (mine !== selectSeq) {
      deps.currentWorkflow.value = committed;
      return false;
    }
    if (!fetched) return selectionFailed();
    committed = fetched;
    return true;
  }

  /** Open the runner on *workflowId* (the runner shows first, the load follows, #1367). */
  async function handleViewWorkflow(workflowId: string): Promise<boolean> {
    deps.navigateToRunner();
    return selectWorkflow(workflowId);
  }

  /** The start answered; the refreshed workflow must show it started, else the user is told. */
  function startConfirmed(workflowId: string): boolean {
    const current = deps.currentWorkflow.value;
    return current?.workflow_id !== workflowId || Boolean(current.started_at);
  }

  async function handleStartWorkflow(workflowId: string): Promise<void> {
    if (deps.executingWorkflow.value) return;
    const started = await deps.startWorkflow(workflowId);
    if (!started) deps.showToast(deps.t('workflow.builder.startFailed'), 'error');
    else if (!startConfirmed(workflowId)) deps.showToast(deps.t('workflow.builder.startUnconfirmed'), 'warning');
    else deps.showToast(deps.t('workflow.builder.started'), 'success');
  }

  return { selectWorkflow, handleViewWorkflow, handleStartWorkflow };
}
