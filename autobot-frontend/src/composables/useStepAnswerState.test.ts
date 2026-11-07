// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A step stays locked once the server may have accepted its answer, and a status refresh releases it only
 * when the returned workflow no longer shows the step waiting approval.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({ connect: vi.fn(), disconnect: vi.fn(), isConnected: { value: false } }),
}));
vi.mock('@/utils/ApiClient', () => ({ default: http }));
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }));
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }));

import { HttpError } from '@autobot/ui';
import { useStepAnswerState } from './useStepAnswerState';
import { useWorkflowBuilder } from './useWorkflowBuilder';

const wf = (status: string) => ({ workflow: { workflow_id: 'wf-1', steps: [{ step_id: 's1', status }] } });

describe('step answer lock', () => {
  beforeEach(() => {
    http.get.mockReset();
    http.post.mockReset();
    for (const id of ['wf-1', 'wf-2']) useStepAnswerState().dropWorkflow(id);
  });

  it('an unconfirmed answer is decided by the first refresh issued after it: still waiting means the server never took it', async () => {
    http.post.mockRejectedValue(new Error('network down'));
    http.get.mockResolvedValue(wf('waiting_approval'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false); // the step may be answered again
    expect(http.get).toHaveBeenCalledTimes(1);
  });

  it('an unconfirmed answer the server did take is released as accepted when the refresh shows it decided', async () => {
    http.post.mockRejectedValue(new Error('network down'));
    http.get.mockResolvedValue(wf('approved'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });

  it('a refresh issued before the unconfirmed send settled cannot decide it', async () => {
    const state = useStepAnswerState();
    const waiting = { success: true, data: { workflow: { steps: [{ step_id: 's1', status: 'waiting_approval' }] } } };
    let finishOlder!: (v: typeof waiting) => void;
    const older = state.fetchStatus('wf-1', () => new Promise<typeof waiting>((r) => { finishOlder = r; }));
    await state.answer('wf-1', 's1', async () => 'unconfirmed', async () => null); // its own refresh failed
    finishOlder(waiting); // the older, still in-flight response arrives late
    await older;
    expect(state.isStepLocked('wf-1', 's1')).toBe(true);
    await state.fetchStatus('wf-1', async () => waiting); // issued after the send settled
    expect(state.isStepLocked('wf-1', 's1')).toBe(false);
  });

  it.each([500, 503, 408])('a %i send stays unconfirmed: locked until a refresh issued afterwards decides it', async (status) => {
    http.post.mockRejectedValue(new HttpError(status, 'no answer'));
    http.get.mockRejectedValue(new Error('offline'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(true);
    http.get.mockResolvedValue(wf('waiting_approval'));
    await useWorkflowBuilder().getWorkflowStatus('wf-1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });

  it('a 429 is refused outright: the step unlocks at once', async () => {
    http.post.mockRejectedValue(new HttpError(429, 'slow down'));
    await useWorkflowBuilder().approveStep('wf-1', 's1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });

  it('a response with no step list releases nothing', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue({ workflow: { workflow_id: 'wf-1' } });
    const { approveStep, getWorkflowStatus } = useWorkflowBuilder();
    await approveStep('wf-1', 's1');
    await getWorkflowStatus('wf-1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(true);
  });

  it('another workflow\'s entries are untouched by a status refresh', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue(wf('waiting_approval'));
    const { approveStep, getWorkflowStatus } = useWorkflowBuilder();
    await approveStep('wf-1', 's1');
    await approveStep('wf-2', 's1');
    http.get.mockResolvedValue(wf('approved')); // wf-1 shows decided
    await getWorkflowStatus('wf-1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
    expect(useStepAnswerState().isStepLocked('wf-2', 's1')).toBe(true);
  });

  it('a not-found status drops that workflow\'s entries', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue(wf('waiting_approval'));
    const { approveStep, getWorkflowStatus } = useWorkflowBuilder();
    await approveStep('wf-1', 's1');
    http.get.mockRejectedValue(new HttpError(404, 'gone'));
    await getWorkflowStatus('wf-1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });

  it('a workflow that leaves the active list drops its entries', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue(wf('waiting_approval'));
    const { approveStep, loadActiveWorkflows, activeWorkflows } = useWorkflowBuilder();
    activeWorkflows.value = [{ workflow_id: 'wf-1' }] as never;
    await approveStep('wf-1', 's1');
    http.get.mockResolvedValue({ workflows: [] });
    await loadActiveWorkflows();
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });

  it('a 4xx refusal unlocks the step at once and does not refresh', async () => {
    http.post.mockRejectedValue(new HttpError(409, 'not awaiting approval'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
    expect(http.get).not.toHaveBeenCalled();
  });

  it('a stale status that still says waiting_approval does not release an accepted answer; a decided one does', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue(wf('waiting_approval'));
    const { approveStep, getWorkflowStatus } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(true);
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(true);
    await getWorkflowStatus('wf-1'); // a later refresh still stale: accepted stays locked
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(true);
    http.get.mockResolvedValue(wf('approved'));
    await getWorkflowStatus('wf-1');
    expect(useStepAnswerState().isStepLocked('wf-1', 's1')).toBe(false);
  });
});
