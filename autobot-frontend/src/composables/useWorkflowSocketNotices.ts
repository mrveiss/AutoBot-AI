// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * User-facing notices for the workflow socket's waits and refusals (#17677).
 *
 * `step_confirmation_required` is a wait: the executor parks the step in
 * `waiting_approval` and resumes only on `approve_step`. This module never
 * answers it -- it tells the user, and the runner's own Approve / Skip buttons
 * (the existing step-approval path) are where the answer is given.
 */
import { useNotificationBus } from '@/composables/useNotificationBus';
import i18n from '@/i18n';
import type { Ref } from 'vue';

export const WORKFLOW_NOTICE_TYPES = [
  'step_confirmation_required',
  'step_rejected_by_judge',
  'automation_control_refused',
] as const;

export type WorkflowNoticeType = (typeof WORKFLOW_NOTICE_TYPES)[number];

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

export function useWorkflowSocketNotices() {
  const { showToast } = useNotificationBus();
  const t = (key: string, params?: Record<string, string>): string =>
    i18n.global.t(key, params ?? {}) as string;

  /** Show the notice for one socket message; returns its workflow id. */
  function showWorkflowNotice(data: Record<string, unknown>): string {
    const step = (data.step_data ?? {}) as Record<string, unknown>;
    if (data.type === 'step_confirmation_required') {
      const label = text(step.description) || text(data.step_id);
      showToast(t('workflow.builder.stepAwaitingApproval', { step: label }), 'warning');
    } else if (data.type === 'step_rejected_by_judge') {
      showToast(t('workflow.builder.stepRejectedByJudge', { reason: text(data.reason) }), 'error');
    } else {
      showToast(t('workflow.builder.controlRefused'), 'error');
    }
    return text(data.workflow_id);
  }

  return { showWorkflowNotice };
}

interface Displayed {
  workflow_id: string;
}

/**
 * Refresh the displayed workflow from a notice, only while it is still the one
 * the notice names -- checked on arrival and again on the response, so a notice
 * for another workflow, or a reply after a switch, never replaces it. A failed
 * response leaves the display unchanged.
 */
export async function refreshIfDisplayed<W extends Displayed>(
  displayed: Ref<W | null>,
  workflowId: string,
  fetchStatus: (id: string) => Promise<{ success: boolean; data?: { workflow: W } | null }>,
): Promise<void> {
  if (displayed.value?.workflow_id !== workflowId) return;
  const response = await fetchStatus(workflowId);
  if (!response.success || !response.data) return;
  if (displayed.value?.workflow_id !== workflowId) return;
  displayed.value = response.data.workflow;
}
