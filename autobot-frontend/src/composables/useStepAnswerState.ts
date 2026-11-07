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
/** A decided step: `after` is the refresh sequence when its send settled; `unconfirmed` means the server's receipt is unknown. */
const decided = reactive(new Map<string, { unconfirmed: boolean; after: number }>());
let refreshSeq = 0;

const keyOf = (workflowId: string, stepId: string) => `${workflowId}\u0000${stepId}`;

/** What sending an answer came to: accepted, refused outright by the server (4xx), or unconfirmed (network or 5xx). */
export type StepSendResult = boolean | 'unconfirmed';

/** Classify a control response: accepted, refused outright (`refused`, a 4xx), or unconfirmed (the outcome is unknown). */
export const stepSendResult = (r: { success: boolean; refused?: boolean }): StepSendResult => r.success || (r.refused ? false : 'unconfirmed');

export function useStepAnswerState() {
  const { showToast } = useNotificationBus();
  return {
    /**
     * Send one answer. Resolves with the DECISION result only; a status refresh that fails afterwards is
     * reported apart (a toast) and leaves the step decided locally, its cards disabled, until a refresh succeeds.
     */
    async answer(workflowId: string, stepId: string, send: () => Promise<StepSendResult>, refresh: () => Promise<unknown>): Promise<boolean> {
      const key = keyOf(workflowId, stepId);
      if (inFlight.has(key) || decided.has(key)) return false; // already answered or being answered
      inFlight.add(key);
      try {
        const sent = await send();
        if (sent === false) return false; // refused: the step is still waiting and may be answered again
        decided.set(key, { unconfirmed: sent === 'unconfirmed', after: refreshSeq }); // a status refresh decides it
        if (!(await refresh())) showToast(i18n.global.t('workflow.builder.stepStatusRefreshFailed') as string, 'warning');
        return sent === true;
      } finally {
        inFlight.delete(key);
      }
    },
    /** True while an answer is being sent or the accepted answer awaits a successful status refresh. */
    isStepLocked: (workflowId: string, stepId: string) =>
      inFlight.has(keyOf(workflowId, stepId)) || decided.has(keyOf(workflowId, stepId)),
    /** Take the sequence number of a status refresh about to be issued; pass it to `clearDecided` with its response. */
    nextRefresh: () => ++refreshSeq,
    /**
     * A status refresh succeeded: release each decided step of this workflow that the returned *steps* no longer
     * show as waiting approval (a stale response that still says waiting leaves an accepted step locked). An
     * unconfirmed step is also released by the first refresh *issued* after its send settled (`issued`), even if
     * it still shows waiting: the server did not take that answer, and a repeat is safe (the server refuses repeats).
     */
    clearDecided: (workflowId: string, steps: ReadonlyArray<{ step_id: string; status: string }> = [], issued = 0) => {
      const waiting = new Set(steps.filter((s) => s.status === 'waiting_approval').map((s) => keyOf(workflowId, s.step_id)));
      for (const [key, entry] of decided) {
        if (!key.startsWith(`${workflowId}\u0000`)) continue;
        if (!waiting.has(key) || (entry.unconfirmed && issued > entry.after)) decided.delete(key);
      }
    },
  };
}
