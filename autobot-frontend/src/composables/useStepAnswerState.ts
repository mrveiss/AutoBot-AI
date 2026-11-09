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
/** Steps whose unconfirmed answer was released while still waiting: the first request may yet execute, so a refusal on the retry is not a plain refusal. */
const retryAfterTimeout = reactive(new Set<string>());
/** Per workflow, the sequence of the newest status response applied: an older response must not overwrite it. */
const appliedSeq = new Map<string, number>();
let refreshSeq = 0;

const keyOf = (workflowId: string, stepId: string) => `${workflowId}\u0000${stepId}`;

/** What sending an answer came to: accepted, refused outright by the server (4xx), or unconfirmed (network or 5xx). */
export type StepSendResult = boolean | 'unconfirmed';

/** Classify a control response: accepted, refused outright (a 4xx other than 408), or unconfirmed (the outcome is unknown). */
export const stepSendResult = (r: { success: boolean; httpStatus?: number }): StepSendResult => {
  if (r.success) return true;
  const status = r.httpStatus ?? 0;
  return status >= 400 && status < 500 && status !== 408 ? false : 'unconfirmed'; // 408 may follow a request the server processed
};

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
        if (sent === false && !retryAfterTimeout.has(key)) return false; // refused: the step is still waiting and may be answered again
        // A refusal of the retry after a timeout (a 409 while the first answer executes) is settled by the status, not taken as plain.
        decided.set(key, { unconfirmed: sent === 'unconfirmed', after: refreshSeq }); // a status refresh decides it
        retryAfterTimeout.delete(key);
        if (!(await refresh()) && decided.has(key)) showToast(i18n.global.t('workflow.builder.stepStatusRefreshFailed') as string, 'warning');
        return sent === true;
      } finally {
        inFlight.delete(key);
      }
    },
    /** True while an answer is being sent or the accepted answer awaits a successful status refresh. */
    isStepLocked: (workflowId: string, stepId: string) =>
      inFlight.has(keyOf(workflowId, stepId)) || decided.has(keyOf(workflowId, stepId)),
    /**
     * Run one status refresh through the lock state: its sequence number is taken before the request goes out, a
     * missing step list says nothing and releases nothing, and a not-found workflow is gone (its entries are dropped).
     */
    async fetchStatus<R extends StatusResponse>(workflowId: string, request: () => Promise<R>): Promise<R> {
      const issued = ++refreshSeq;
      const r = await request();
      if (issued < (appliedSeq.get(workflowId) ?? 0)) return { ...r, success: false }; // a newer response already owns the state
      const steps = r.data?.workflow?.steps;
      if (r.success) appliedSeq.set(workflowId, issued);
      if (r.httpStatus === 404) dropWorkflow(workflowId);
      else if (r.success && Array.isArray(steps)) clearDecided(workflowId, steps, issued);
      return r;
    },
    /** Forget the entries of every workflow in `previous` that is not in `next`: it left the builder. */
    forgetRemoved: (previous: ReadonlyArray<{ workflow_id: string }>, next: ReadonlyArray<{ workflow_id: string }>) => {
      const kept = new Set(next.map((w) => w.workflow_id));
      for (const w of previous) if (!kept.has(w.workflow_id)) dropWorkflow(w.workflow_id);
    },
    dropWorkflow,
    clearDecided,
  };
}

/** Forget the decided entries of one workflow (in-flight entries clear themselves in the send's finally). */
function dropWorkflow(workflowId: string): void {
  for (const key of decided.keys()) if (key.startsWith(`${workflowId}\u0000`)) decided.delete(key);
  for (const key of retryAfterTimeout) if (key.startsWith(`${workflowId}\u0000`)) retryAfterTimeout.delete(key);
  appliedSeq.delete(workflowId);
}

type StepInfo = { step_id: string; status: string };
type StatusResponse = { success: boolean; data?: { workflow?: { steps?: unknown } }; httpStatus?: number };

/**
 * Release each decided step of *workflowId* that the refresh's *steps* no longer show as waiting approval (a stale
 * response that still says waiting leaves an accepted step locked). An unconfirmed step is also released by the
 * first refresh issued after its send settled (`issued`), even if it still shows waiting: the server did not take
 * that answer, and a repeat is safe (the server refuses repeats).
 */
function clearDecided(workflowId: string, steps: ReadonlyArray<StepInfo>, issued: number): void {
  const waiting = new Set(steps.filter((s) => s.status === 'waiting_approval').map((s) => keyOf(workflowId, s.step_id)));
  for (const [key, entry] of decided) {
    if (!key.startsWith(`${workflowId}\u0000`)) continue;
    if (!waiting.has(key)) {
      decided.delete(key);
      retryAfterTimeout.delete(key);
    } else if (entry.unconfirmed && issued > entry.after) {
      decided.delete(key);
      retryAfterTimeout.add(key); // released while still waiting: a retry's refusal must be reconciled
    }
  }
}
