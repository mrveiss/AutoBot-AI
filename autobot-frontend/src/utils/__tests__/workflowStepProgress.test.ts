// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { getWorkflowStepDisplay } from '../workflowStepProgress'

const STARTED = '2026-11-08T10:00:00Z'

describe('getWorkflowStepDisplay (#21106)', () => {
  it('shows a defined not-started state before the run begins', () => {
    expect(getWorkflowStepDisplay({ current_step: 1, total_steps: 2 })).toEqual({ current: 0, total: 2, percent: 0 })
  })

  it('shows the 1-based backend step as-is while running', () => {
    expect(getWorkflowStepDisplay({ current_step: 1, total_steps: 2, started_at: STARTED }).current).toBe(1)
    expect(getWorkflowStepDisplay({ current_step: 2, total_steps: 2, started_at: STARTED })).toEqual({ current: 2, total: 2, percent: 50 })
  })

  it('shows M / M and 100% at completion although the backend sends total + 1', () => {
    const done = getWorkflowStepDisplay({ current_step: 3, total_steps: 2, started_at: STARTED, completed_at: STARTED })
    expect(done).toEqual({ current: 2, total: 2, percent: 100 })
  })

  it('never exceeds the total even without a completed marker', () => {
    expect(getWorkflowStepDisplay({ current_step: 3, total_steps: 2, started_at: STARTED }).current).toBe(2)
  })

  it('reaches 100% only on completion', () => {
    expect(getWorkflowStepDisplay({ current_step: 2, total_steps: 2, started_at: STARTED }).percent).toBeLessThan(100)
  })

  it('handles an empty workflow', () => {
    expect(getWorkflowStepDisplay({ current_step: 1, total_steps: 0 })).toEqual({ current: 0, total: 0, percent: 0 })
  })

  it('converts the legacy 0-based index when the caller declares it', () => {
    expect(getWorkflowStepDisplay({ current_step: 0, total_steps: 2 }, { indexBase: 0 }).current).toBe(1)
    expect(getWorkflowStepDisplay({ current_step: 1, total_steps: 2, status: 'completed' }, { indexBase: 0 }).current).toBe(2)
  })

  describe.each([
    ['1-based', 1 as const, 2, { current: 2, total: 5, percent: 20 }],
    ['0-based', 0 as const, 1, { current: 2, total: 5, percent: 20 }],
  ])('a run that did not complete (%s index)', (_name, indexBase, step, reached) => {
    const run = { current_step: step, total_steps: 5, started_at: STARTED }

    it('cancelled (executor stamps completed_at too) shows the step reached, not 5 / 5', () => {
      expect(getWorkflowStepDisplay({ ...run, is_cancelled: true, completed_at: STARTED }, { indexBase })).toEqual(reached)
      expect(getWorkflowStepDisplay({ ...run, status: 'cancelled', completed_at: STARTED }, { indexBase })).toEqual(reached)
    })

    it('failed (status or a failed step) shows the step reached, below 100%', () => {
      expect(getWorkflowStepDisplay({ ...run, status: 'failed' }, { indexBase })).toEqual(reached)
      expect(getWorkflowStepDisplay({ ...run, steps: [{ status: 'completed' }, { status: 'failed' }] }, { indexBase })).toEqual(reached)
      expect(getWorkflowStepDisplay({ ...run, steps: [{ status: 'failed' }], completed_at: STARTED }, { indexBase }).percent).toBeLessThan(100)
    })

    it('paused shows the step reached, below 100%', () => {
      expect(getWorkflowStepDisplay({ ...run, is_paused: true }, { indexBase })).toEqual(reached)
      expect(getWorkflowStepDisplay({ ...run, status: 'paused' }, { indexBase })).toEqual(reached)
    })

    it('a successful completion still reads total / total, 100%', () => {
      expect(getWorkflowStepDisplay({ ...run, completed_at: STARTED, steps: [{ status: 'completed' }] }, { indexBase })).toEqual({ current: 5, total: 5, percent: 100 })
    })

    it('treats NaN, undefined and 0 totals as an empty workflow', () => {
      for (const total_steps of [Number.NaN, undefined as unknown as number, 0]) {
        expect(getWorkflowStepDisplay({ current_step: step, total_steps, started_at: STARTED }, { indexBase })).toEqual({ current: 0, total: 0, percent: 0 })
      }
    })

    it('treats a NaN or undefined step as the first step', () => {
      for (const current_step of [Number.NaN, undefined as unknown as number]) {
        expect(getWorkflowStepDisplay({ current_step, total_steps: 5, started_at: STARTED }, { indexBase }).current).toBe(1)
      }
    })
  })
})
