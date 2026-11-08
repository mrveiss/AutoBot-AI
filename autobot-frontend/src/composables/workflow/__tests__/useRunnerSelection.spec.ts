// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Select and start decisions of the runner (#21043): server status on select, newest select wins,
// a start whose refresh failed is reported as unconfirmed.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useRunnerSelection } from '../useRunnerSelection'
import type { ActiveWorkflow } from '@/composables/useWorkflowBuilder'

const wf = (id: string, started_at?: string) => ({ workflow_id: id, started_at }) as unknown as ActiveWorkflow
const showToast = vi.fn()
const getWorkflowStatus = vi.fn()
const startWorkflow = vi.fn()
const activeWorkflows = ref<ActiveWorkflow[]>([])
const currentWorkflow = ref<ActiveWorkflow | null>(null)
const executingWorkflow = ref(false)

function setup() {
  return useRunnerSelection({
    t: (k) => k, showToast, navigateToRunner: vi.fn(), activeWorkflows, currentWorkflow, executingWorkflow,
    startWorkflow, getWorkflowStatus,
  })
}
const errors = () => showToast.mock.calls.filter((c) => c[1] === 'error').map((c) => c[0])

beforeEach(() => {
  vi.clearAllMocks()
  activeWorkflows.value = []
  currentWorkflow.value = null
  executingWorkflow.value = false
})

describe('selectWorkflow', () => {
  it('fetches the status of a listed workflow and shows the server answer', async () => {
    activeWorkflows.value = [wf('a')]
    getWorkflowStatus.mockImplementation(async () => { currentWorkflow.value = wf('a', 'now'); return currentWorkflow.value })
    expect(await setup().selectWorkflow('a')).toBe(true)
    expect(getWorkflowStatus).toHaveBeenCalledWith('a')
    expect(currentWorkflow.value?.started_at).toBe('now')
  })

  it('keeps the listed entry and toasts when its status fetch returns null', async () => {
    const listed = wf('a')
    activeWorkflows.value = [listed]
    getWorkflowStatus.mockResolvedValue(null)
    expect(await setup().selectWorkflow('a')).toBe(false)
    expect(currentWorkflow.value?.workflow_id).toBe(listed.workflow_id)
    expect(errors()).toEqual(['workflow.builder.selectFailed'])
  })

  it('toasts select-failed when the status fetch rejects', async () => {
    getWorkflowStatus.mockRejectedValue(new Error('null step'))
    expect(await setup().selectWorkflow('a')).toBe(false)
    expect(errors()).toEqual(['workflow.builder.selectFailed'])
  })

  it('a slow remote lookup does not overwrite a later local select', async () => {
    const b = wf('b')
    activeWorkflows.value = [b]
    const slowA = wf('a')
    let finishA: () => void = () => {}
    getWorkflowStatus.mockImplementation((id: string) => (id === 'a'
      ? new Promise((r) => { finishA = () => { currentWorkflow.value = slowA; r(slowA) } })
      : Promise.resolve(b)))
    const sel = setup()
    const first = sel.selectWorkflow('a')
    await sel.selectWorkflow('b')
    finishA()
    await first
    expect(currentWorkflow.value?.workflow_id).toBe(b.workflow_id)
  })
})

describe('handleStartWorkflow', () => {
  it('toasts success when the refreshed workflow shows started', async () => {
    startWorkflow.mockImplementation(async () => { currentWorkflow.value = wf('a', 'now'); return true })
    await setup().handleStartWorkflow('a')
    expect(showToast).toHaveBeenCalledWith('workflow.builder.started', 'success')
  })

  it('reports an unconfirmed start when the refresh left the workflow not started', async () => {
    currentWorkflow.value = wf('a')
    startWorkflow.mockResolvedValue(true)
    await setup().handleStartWorkflow('a')
    expect(showToast.mock.calls).toEqual([['workflow.builder.startUnconfirmed', 'warning']])
  })

  it('ignores a second start while one is in flight', async () => {
    executingWorkflow.value = true
    await setup().handleStartWorkflow('a')
    expect(startWorkflow).not.toHaveBeenCalled()
  })
})
