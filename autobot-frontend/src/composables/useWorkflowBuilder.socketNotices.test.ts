// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The four workflow socket messages that used to fall into `default:` (#17677).
 * A confirmation the executor waits on must reach the user and must NOT be
 * answered by the client.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const sock = vi.hoisted(() => ({ onMessage: null as null | ((d: unknown) => void) }));
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const toast = vi.hoisted(() => vi.fn());

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: (_url: unknown, opts: { onMessage: (d: unknown) => void }) => {
    sock.onMessage = opts.onMessage;
    return { connect: vi.fn(), disconnect: vi.fn(), isConnected: { value: false } };
  },
}));
vi.mock('@/utils/ApiClient', () => ({ default: http }));
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: toast }) }));
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string, p: Record<string, string> = {}) => `${key}|${Object.values(p).join(',')}` } },
}));

import { useWorkflowBuilder } from './useWorkflowBuilder';

const send = (msg: Record<string, unknown>) => sock.onMessage!(JSON.stringify(msg));
const flush = () => new Promise((r) => setTimeout(r, 0));
const getUrls = () => http.get.mock.calls.map((c) => String(c[0])).join(' ');

describe('useWorkflowBuilder workflow socket notices (#17677)', () => {
  beforeEach(() => {
    http.get.mockReset().mockResolvedValue({ workflows: [], workflow: { workflow_id: 'wf-1' } });
    http.post.mockReset();
    toast.mockReset();
  });

  it('step_confirmation_required toasts the wait, refreshes the workflow and answers nothing', async () => {
    const { currentWorkflow } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-1' } as never;
    send({
      type: 'step_confirmation_required',
      workflow_id: 'wf-1',
      step_id: 's1',
      step_data: { description: 'Restart service' },
    });
    await flush();
    expect(toast).toHaveBeenCalledWith('workflow.builder.stepAwaitingApproval|Restart service', 'warning');
    expect(getUrls()).toContain('workflow_status/wf-1');
    expect(http.post).not.toHaveBeenCalled();
  });

  it('stepsAwaitingApproval follows the server status, not the toast', () => {
    const { currentWorkflow, stepsAwaitingApproval } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-1', steps: [{ step_id: 'a', status: 'waiting_approval' }, { step_id: 'b', status: 'pending' }] } as never;
    expect(stepsAwaitingApproval.value.map((s) => s.step_id)).toEqual(['a']);
    currentWorkflow.value = { workflow_id: 'wf-1', steps: [{ step_id: 'a', status: 'executing' }] } as never;
    expect(stepsAwaitingApproval.value).toEqual([]);
  });

  it.each([['approveStep', 'approve_step'], ['skipStep', 'skip_step']] as const)(
    '%s makes exactly one control call, then re-reads the status',
    async (fn, action) => {
      http.post.mockResolvedValue({ success: true });
      const composable = useWorkflowBuilder();
      await expect(composable[fn]('wf-1', 's1')).resolves.toBe(true);
      expect(http.post).toHaveBeenCalledTimes(1);
      expect(http.post.mock.calls[0][0]).toContain('control_workflow');
      expect(http.post.mock.calls[0][1]).toMatchObject({ workflow_id: 'wf-1', action, step_id: 's1' });
      expect(getUrls()).toContain('workflow_status/wf-1');
    },
  );

  it('a failed control request resolves false and does not re-read the status', async () => {
    http.post.mockRejectedValue(new Error('refused'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(http.get).not.toHaveBeenCalled();
  });

  it('a notice for another workflow does not fetch or replace the displayed one', async () => {
    const { currentWorkflow } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-1' } as never;
    send({ type: 'step_rejected_by_judge', workflow_id: 'wf-2', step_id: 's', reason: 'x' });
    await flush();
    expect(getUrls()).not.toContain('workflow_status');
    expect(currentWorkflow.value?.workflow_id).toBe('wf-1');
  });

  it('a response arriving after the user switched workflows is dropped', async () => {
    let release!: (v: unknown) => void;
    http.get.mockImplementation((url: string) =>
      String(url).includes('workflow_status')
        ? new Promise((r) => { release = r; })
        : Promise.resolve({ workflows: [] }),
    );
    const { currentWorkflow } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-1' } as never;
    send({ type: 'step_rejected_by_judge', workflow_id: 'wf-1', step_id: 's', reason: 'x' });
    await flush();
    currentWorkflow.value = { workflow_id: 'wf-2' } as never;
    release({ workflow: { workflow_id: 'wf-1', stale: true } });
    await flush();
    expect(currentWorkflow.value?.workflow_id).toBe('wf-2');
  });

  it('step_rejected_by_judge toasts the reason', () => {
    useWorkflowBuilder();
    send({ type: 'step_rejected_by_judge', workflow_id: 'wf-1', step_id: 's2', reason: 'destructive' });
    expect(toast).toHaveBeenCalledWith('workflow.builder.stepRejectedByJudge|destructive', 'error');
  });

  it('automation_control_refused toasts a refusal without refetching', async () => {
    useWorkflowBuilder();
    send({ type: 'automation_control_refused', workflow_id: 'wf-1', reason: 'not_admin_or_owner' });
    await flush();
    expect(toast).toHaveBeenCalledWith('workflow.builder.controlRefused|', 'error');
    expect(http.get).not.toHaveBeenCalled();
  });

  it('a notice with no workflow id toasts but does not fetch a status for an empty id', async () => {
    useWorkflowBuilder();
    send({ type: 'step_rejected_by_judge', step_id: 's2', reason: 'destructive' });
    await flush();
    expect(toast).toHaveBeenCalled();
    expect(getUrls()).not.toContain('workflow_status');
  });

  it('start_workflow refreshes the active list and raises no notice', async () => {
    useWorkflowBuilder();
    send({ type: 'start_workflow', workflow: { id: 'wf-1' } });
    await flush();
    expect(getUrls()).toContain('active_workflows');
    expect(toast).not.toHaveBeenCalled();
  });
});
