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

import { HttpError } from '@autobot/ui';
import { useStepAnswerState } from './useStepAnswerState';
import { useWorkflowBuilder } from './useWorkflowBuilder';

const send = (msg: Record<string, unknown>) => sock.onMessage!(JSON.stringify(msg));
const flush = () => new Promise((r) => setTimeout(r, 0));
const getUrls = () => http.get.mock.calls.map((c) => String(c[0])).join(' ');

describe('useWorkflowBuilder workflow socket notices (#17677)', () => {
  beforeEach(() => {
    http.get.mockReset().mockResolvedValue({ workflows: [], workflow: { workflow_id: 'wf-1', steps: [] } });
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
      const waiting = (id: string) => ({ step_id: id, status: 'waiting_approval' });
      composable.currentWorkflow.value = { workflow_id: 'wf-1', steps: [waiting('s1')] } as never;
      http.get.mockResolvedValue({ workflow: { workflow_id: 'wf-1', steps: [waiting('s2')] } }); // the server's next waiting step
      await expect(composable[fn]('wf-1', 's1')).resolves.toBe(true);
      expect(composable.stepsAwaitingApproval.value.map((s) => s.step_id)).toEqual(['s2']); // replaces the answered one
      expect(http.post).toHaveBeenCalledTimes(1);
      expect(http.post.mock.calls[0][0]).toContain('control_workflow');
      expect(http.post.mock.calls[0][1]).toMatchObject({ workflow_id: 'wf-1', action, step_id: 's1' });
      expect(getUrls()).toContain('workflow_status/wf-1');
    },
  );

  it('a control request the server refused (4xx) resolves false and does not re-read the status', async () => {
    http.post.mockRejectedValue(new HttpError(409, 'refused'));
    const { approveStep } = useWorkflowBuilder();
    await expect(approveStep('wf-1', 's1')).resolves.toBe(false);
    expect(http.get).not.toHaveBeenCalled();
  });

  it('a failed status refresh still resolves the decision, tells the user and keeps the step locked', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockRejectedValue(new Error('offline'));
    const { approveStep } = useWorkflowBuilder();
    const { isStepLocked, dropWorkflow } = useStepAnswerState();
    await expect(approveStep('wf-9', 's1')).resolves.toBe(true);
    expect(toast).toHaveBeenCalledWith('workflow.builder.stepStatusRefreshFailed|', 'warning');
    expect(isStepLocked('wf-9', 's1')).toBe(true);
    await expect(approveStep('wf-9', 's1')).resolves.toBe(false); // a second click does not re-send
    expect(http.post).toHaveBeenCalledTimes(1);
    dropWorkflow('wf-9');
  });

  it('the in-flight answer is shared per workflow and step, and a refresh that succeeds unlocks it', async () => {
    let release!: (v: unknown) => void;
    http.post.mockImplementation(() => new Promise((r) => { release = r; }));
    const { approveStep, skipStep, getWorkflowStatus } = useWorkflowBuilder();
    const other = useStepAnswerState(); // what a second card for the same step reads
    const first = approveStep('wf-8', 's1');
    expect(other.isStepLocked('wf-8', 's1')).toBe(true);
    expect(other.isStepLocked('wf-8', 's2')).toBe(false);
    await expect(skipStep('wf-8', 's1')).resolves.toBe(false);
    http.get.mockResolvedValue({ workflow: { workflow_id: 'wf-8', steps: [] } });
    release({ success: true });
    await first;
    expect(other.isStepLocked('wf-8', 's1')).toBe(false); // refresh succeeded: server status is authoritative
    expect(http.post).toHaveBeenCalledTimes(1);
    await getWorkflowStatus('wf-8');
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

  it('a slow answer refresh for workflow A cannot replace the displayed workflow B (#21033)', async () => {
    let release!: (v: unknown) => void;
    http.post.mockResolvedValue({ success: true });
    http.get.mockImplementation(() => new Promise((r) => { release = r; }));
    const { currentWorkflow, approveStep } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-A', steps: [] } as never;
    const answered = approveStep('wf-A', 's1');
    await flush();
    currentWorkflow.value = { workflow_id: 'wf-B', steps: [] } as never;
    release({ workflow: { workflow_id: 'wf-A', steps: [{ step_id: 's9', status: 'waiting_approval' }] } });
    await expect(answered).resolves.toBe(true);
    expect(currentWorkflow.value?.workflow_id).toBe('wf-B');
  });

  it('an answer for a workflow that is not displayed still reads its status but does not display it (#21033)', async () => {
    http.post.mockResolvedValue({ success: true });
    http.get.mockResolvedValue({ workflow: { workflow_id: 'wf-C', steps: [] } });
    const { currentWorkflow, approveStep } = useWorkflowBuilder();
    currentWorkflow.value = { workflow_id: 'wf-B', steps: [] } as never;
    await approveStep('wf-C', 's1');
    expect(getUrls()).toContain('workflow_status/wf-C');
    expect(currentWorkflow.value?.workflow_id).toBe('wf-B');
  });

  describe('restoring approval cards after a reload with nothing selected (#21033)', () => {
    const list = [
      { workflow_id: 'wf-run', steps: [{ step_id: 'a', status: 'executing' }] },
      { workflow_id: 'wf-wait', steps: [{ step_id: 'b', status: 'waiting_approval' }] },
    ];
    const mockServer = () =>
      http.get.mockImplementation((url: string) =>
        Promise.resolve(String(url).includes('workflow_status/')
          ? { workflow: { ...list[1], full: true } }
          : { workflows: list }),
      );

    it('displays the first active workflow that has a waiting step, so its card renders', async () => {
      mockServer();
      const { loadActiveWorkflows, currentWorkflow, stepsAwaitingApproval } = useWorkflowBuilder();
      await loadActiveWorkflows();
      expect(currentWorkflow.value?.workflow_id).toBe('wf-wait');
      expect(stepsAwaitingApproval.value.map((s) => s.step_id)).toEqual(['b']);
    });

    it('never replaces a workflow that is already displayed', async () => {
      mockServer();
      const { loadActiveWorkflows, currentWorkflow } = useWorkflowBuilder();
      currentWorkflow.value = { workflow_id: 'wf-run', steps: [] } as never;
      await loadActiveWorkflows();
      expect(currentWorkflow.value?.workflow_id).toBe('wf-run');
      expect(getUrls()).not.toContain('workflow_status');
    });

    it('selects nothing when no active workflow waits, or when one is chosen while the status is in flight', async () => {
      http.get.mockResolvedValue({ workflows: [list[0]] });
      const first = useWorkflowBuilder();
      await first.loadActiveWorkflows();
      expect(first.currentWorkflow.value).toBeNull();

      let release!: (v: unknown) => void;
      http.get.mockImplementation((url: string) =>
        String(url).includes('workflow_status/') ? new Promise((r) => { release = r; }) : Promise.resolve({ workflows: list }),
      );
      const second = useWorkflowBuilder();
      const loading = second.loadActiveWorkflows();
      await flush();
      second.currentWorkflow.value = { workflow_id: 'wf-chosen', steps: [] } as never;
      release({ workflow: { ...list[1] } });
      await loading;
      expect(second.currentWorkflow.value?.workflow_id).toBe('wf-chosen');
    });
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
