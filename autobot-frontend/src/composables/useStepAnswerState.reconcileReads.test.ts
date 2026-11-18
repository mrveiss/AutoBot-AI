// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The bound on a refused retry's reads is always finite: a non-finite env value falls back to the default (#21341).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const toast = vi.hoisted(() => vi.fn());
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: toast }) }));
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }));

const waiting = { success: true, data: { workflow: { steps: [{ step_id: 's1', status: 'waiting_approval' }] } } };

/** A retry the server refused while the first answer still shows waiting; resolves with the reads it took to release the lock. */
async function readsUntilReleased(): Promise<number> {
  const { useStepAnswerState } = await import('./useStepAnswerState');
  const state = useStepAnswerState();
  state.dropWorkflow('wf-1');
  await state.answer('wf-1', 's1', async () => 'unconfirmed', async () => null);
  await state.fetchStatus('wf-1', async () => waiting); // released as unconfirmed while still waiting
  await state.answer('wf-1', 's1', async () => false, () => state.fetchStatus('wf-1', async () => waiting)); // refused retry: read 1
  let reads = 1;
  while (state.isStepLocked('wf-1', 's1') && reads < 50) {
    await state.fetchStatus('wf-1', async () => waiting);
    reads++;
  }
  return reads;
}

describe('RECONCILE_READS from the environment (#21341)', () => {
  beforeEach(() => {
    vi.resetModules();
    toast.mockReset();
  });
  afterEach(() => vi.unstubAllEnvs());

  it('defaults to 3 reads when unset', async () => {
    expect(await readsUntilReleased()).toBe(3);
  });

  it.each(['Infinity', '-Infinity', 'NaN', '0', '-2', ''])('falls back to the default for %j, never an unbounded lock', async (value) => {
    vi.stubEnv('VITE_STEP_ANSWER_RECONCILE_READS', value);
    expect(await readsUntilReleased()).toBe(3);
  });

  it('honours a finite positive integer', async () => {
    vi.stubEnv('VITE_STEP_ANSWER_RECONCILE_READS', '5');
    expect(await readsUntilReleased()).toBe(5);
  });
});
