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
  /** Make *workflowId* the runner's current workflow; tell the user when it cannot be loaded. */
  async function selectWorkflow(workflowId: string): Promise<boolean> {
    const local = deps.activeWorkflows.value.find((wf) => wf.workflow_id === workflowId);
    if (local) {
      deps.currentWorkflow.value = local;
      return true;
    }
    if (await deps.getWorkflowStatus(workflowId)) return true;
    deps.showToast(deps.t('workflow.builder.selectFailed'), 'error');
    return false;
  }

  /** Open the runner on *workflowId* (the runner shows first, the load follows, #1367). */
  async function handleViewWorkflow(workflowId: string): Promise<boolean> {
    deps.navigateToRunner();
    return selectWorkflow(workflowId);
  }

  async function handleStartWorkflow(workflowId: string): Promise<void> {
    if (deps.executingWorkflow.value) return;
    const started = await deps.startWorkflow(workflowId);
    if (started) deps.showToast(deps.t('workflow.builder.started'), 'success');
    else deps.showToast(deps.t('workflow.builder.startFailed'), 'error');
  }

  return { selectWorkflow, handleViewWorkflow, handleStartWorkflow };
}
