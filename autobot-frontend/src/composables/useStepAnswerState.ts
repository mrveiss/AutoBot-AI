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
import { getEnvPositiveInt } from '@autobot/ui';

const inFlight = reactive(new Set<string>());
type DecidedEntry = { unconfirmed: boolean; after: number; reads?: number };
/** A decided step: `after` is the refresh sequence when its send settled; `unconfirmed` means the server's receipt is unknown. */
const decided = reactive(new Map<string, DecidedEntry>());
/** Status reads that may show a retry-refused step still waiting before its lock is released (env-backed, never unbounded). */
const RECONCILE_READS = getEnvPositiveInt(import.meta.env, 'VITE_STEP_ANSWER_RECONCILE_READS', 3);
/** `reads` is set only for a retry the server refused: it counts reads that still show the step waiting, bounding the lock. */
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
  const warn = (k: string) => showToast(i18n.global.t(k) as string, 'warning');
  /** Refresh after a decision; tell the user when it failed (unless a newer read was applied) or a refused retry still shows waiting. */
  const reconcile = async (workflowId: string, key: string, refresh: () => Promise<unknown>): Promise<void> => {
    const before = refreshSeq;
    const ok = await refresh();
    if (!decided.has(key)) return;
    if (!ok && (appliedSeq.get(workflowId) ?? 0) <= before) warn('workflow.builder.stepStatusRefreshFailed'); // a stale response is not a failure
    else if (ok && decided.get(key)?.reads !== undefined) warn('workflow.builder.stepRetryStillWaiting');
  };
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
        const refused = sent === false; // only reachable as a post-timeout retry
        decided.set(key, { unconfirmed: sent === 'unconfirmed', after: refreshSeq, ...(refused ? { reads: 0 } : {}) }); // a status refresh decides it
        retryAfterTimeout.delete(key);
        await reconcile(workflowId, key, refresh);
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
      if (r.httpStatus === 404) {
        dropWorkflow(workflowId);
        appliedSeq.set(workflowId, issued); // tombstone: an older in-flight success must not be applied after the workflow is gone
      } else if (r.success && Array.isArray(steps) && clearDecided(workflowId, steps, issued) > 0) warn('workflow.builder.stepLockReleased');
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
 * that answer, and a repeat is safe (the server refuses repeats). A retry the server refused is released after
 * RECONCILE_READS reads that still show it waiting; the count of such releases is returned so the caller can say so.
 * A post-timeout retry flag is cleared once its step is no longer waiting.
 */
function clearDecided(workflowId: string, steps: ReadonlyArray<StepInfo>, issued: number): number {
  const waiting = new Set(steps.filter((s) => s.status === 'waiting_approval').map((s) => keyOf(workflowId, s.step_id)));
  let expired = 0;
  for (const [key, entry] of decided) {
    if (!key.startsWith(`${workflowId}\u0000`)) continue;
    if (!waiting.has(key)) decided.delete(key);
    else if (entry.unconfirmed && issued > entry.after) {
      decided.delete(key);
      retryAfterTimeout.add(key); // released while still waiting: a retry's refusal must be reconciled
    } else if (entry.reads !== undefined && ++entry.reads >= RECONCILE_READS) {
      decided.delete(key);
      expired++;
    }
  }
  for (const key of retryAfterTimeout) if (key.startsWith(`${workflowId}\u0000`) && !waiting.has(key)) retryAfterTimeout.delete(key);
  return expired;
}
