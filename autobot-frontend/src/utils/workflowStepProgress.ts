// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Display step index and total for a workflow (#21106).
 *
 * The workflow-automation API serialises `current_step` as the 1-based step
 * being run (`current_step_index + 1`), so before the first step runs it is 1
 * and after the last step completes it is `total_steps + 1`. The display value
 * is that number as-is, clamped to the total; the legacy workflow endpoint
 * reports a 0-based index (and has no `started_at`), which callers declare
 * with `indexBase: 0`.
 * Screens must call this instead of adding or subtracting an offset.
 *
 * Only a successful completion is "done" (current === total, 100%). The executor's
 * `cancel_workflow` also stamps `completed_at`, so `is_cancelled` (or a
 * `cancelled` status) wins over it; a failed run (`status: 'failed'` or any step
 * with status `failed`) and a paused run (`is_paused` / `status: 'paused'`) show
 * the step reached with percent below 100.
 */

export interface WorkflowStepProgressInput {
  current_step: number
  total_steps: number
  started_at?: string | null
  completed_at?: string | null
  status?: string | null
  is_cancelled?: boolean | null
  is_paused?: boolean | null
  steps?: ReadonlyArray<{ status?: string | null }> | null
}

export interface WorkflowStepDisplay {
  /** Step shown to the user: 0 before start, 1..total while running, total once completed. */
  current: number
  total: number
  /** Whole-number percent; 100 only once the workflow has completed successfully. */
  percent: number
}

function isSuccessfulCompletion(wf: WorkflowStepProgressInput): boolean {
  if (wf.is_cancelled || wf.status === 'cancelled' || wf.status === 'failed') return false
  if (wf.steps?.some((s) => s.status === 'failed')) return false
  return Boolean(wf.completed_at) || wf.status === 'completed'
}

export function getWorkflowStepDisplay(
  wf: WorkflowStepProgressInput,
  options: { indexBase?: 0 | 1 } = {},
): WorkflowStepDisplay {
  const total = Number.isFinite(wf.total_steps) ? Math.max(0, wf.total_steps) : 0
  if (total === 0) return { current: 0, total, percent: 0 }
  if (isSuccessfulCompletion(wf)) return { current: total, total, percent: 100 }
  const started = options.indexBase === 0 || Boolean(wf.started_at)
  if (!started) return { current: 0, total, percent: 0 }
  const step = Number.isFinite(wf.current_step) ? wf.current_step : 0
  const oneBased = step + (options.indexBase === 0 ? 1 : 0)
  const current = Math.min(Math.max(oneBased, 1), total)
  return { current, total, percent: Math.floor(((current - 1) / total) * 100) }
}
