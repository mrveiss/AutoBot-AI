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
})
