// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Which workflow steps have an answer in flight or already decided, shared per (workflow, step).
 *
 * Module-level on purpose: every approval card for the same step (the runner's inline card and the
 * canvas card) reads this one state, so answering in one disables the other. A step stays "decided"
 * after the server accepted the answer until a status refresh succeeds, so a failed refresh cannot
 * leave a live Approve button that re-sends the decision.
 */
import { reactive } from 'vue';
import { useNotificationBus } from '@/composables/useNotificationBus';
import i18n from '@/i18n';

const inFlight = reactive(new Set<string>());
const decided = reactive(new Set<string>());

const keyOf = (workflowId: string, stepId: string) => `${workflowId}\u0000${stepId}`;

export function useStepAnswerState() {
  const { showToast } = useNotificationBus();
  return {
    /**
     * Send one answer. Resolves with the DECISION result only; a status refresh that fails afterwards is
     * reported apart (a toast) and leaves the step decided locally, its cards disabled, until a refresh succeeds.
     */
    async answer(workflowId: string, stepId: string, send: () => Promise<boolean>, refresh: () => Promise<unknown>): Promise<boolean> {
      const key = keyOf(workflowId, stepId);
      if (inFlight.has(key) || decided.has(key)) return false; // already answered or being answered
      inFlight.add(key);
      try {
        if (!(await send())) return false;
        decided.add(key);
        if (!(await refresh())) showToast(i18n.global.t('workflow.builder.stepStatusRefreshFailed') as string, 'warning');
        return true;
      } finally {
        inFlight.delete(key);
      }
    },
    /** True while an answer is being sent or the accepted answer awaits a successful status refresh. */
    isStepLocked: (workflowId: string, stepId: string) =>
      inFlight.has(keyOf(workflowId, stepId)) || decided.has(keyOf(workflowId, stepId)),
    /** A status refresh succeeded: the server's step status is authoritative again for this workflow. */
    clearDecided: (workflowId: string) => {
      for (const key of [...decided]) if (key.startsWith(`${workflowId}\u0000`)) decided.delete(key);
    },
  };
}
