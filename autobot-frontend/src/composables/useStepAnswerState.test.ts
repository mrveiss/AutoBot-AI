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
    useStepAnswerState().clearDecided('wf-1');
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
    const older = state.nextRefresh();
    await state.answer('wf-1', 's1', async () => 'unconfirmed', async () => null); // its own refresh failed
    const waiting = [{ step_id: 's1', status: 'waiting_approval' }];
    state.clearDecided('wf-1', waiting, older); // a response to the older, still in-flight request
    expect(state.isStepLocked('wf-1', 's1')).toBe(true);
    state.clearDecided('wf-1', waiting, state.nextRefresh());
    expect(state.isStepLocked('wf-1', 's1')).toBe(false);
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
