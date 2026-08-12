// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The executor rollup — work items counted by executor class and status (#13942).
 *
 * ## Data source and where the count happens
 *
 * `GET /api/llc/companies/{id}/work-items/executor-rollup` (backend, #13942)
 * returns `(executor_class, status, count)` cells computed by a single SQL
 * `GROUP BY` over every work item of the company. Counting happens
 * server-side, not by paginating `GET /work-items` (capped at 500 rows) into
 * this module and counting client-side: a client-side count over one page
 * would silently under-report any company past the cap, which is exactly the
 * "confident wrong count" class of bug this panel exists to avoid.
 *
 * This is *not* the same derivation `composables/llc/orgPeople.ts` does.
 * `orgPeople.ts`'s `PersonKind` is read from provenance (which endpoint a row
 * came from) plus `is_human`, because no backend field states it directly —
 * that derivation genuinely can only happen in the frontend today (its own
 * module docstring explains why). A work item's executor class has no such
 * gap: `assignee_type` is already a backend-typed value (`AssigneeType`,
 * #13937), so there is nothing this module needs to re-derive — it only
 * shapes the already-computed cells for the panel.
 *
 * ## Vocabulary
 *
 * `ExecutorClass` extends `WorkItem['assignee_type']` (`workItemTypes.ts`)
 * with the one case that type cannot express — no assignee at all — rather
 * than declaring a fresh bare union. This is the same lesson #13938's
 * `PersonKind` review left for this issue (#13942's constraint 2): forking a
 * parallel vocabulary next to an existing one is cheap to write and awkward
 * to reconcile once a second reader depends on member names that happen to
 * differ from the SSOT's for no reason.
 *
 * ## Why the person/agent split, not person/automation/AI agent
 *
 * The pattern being adopted (per the parent umbrella's own decision) is
 * "count by executor class, with an honest unassigned bucket" — not the
 * literal three human/automation/AI-agent labels of the external product
 * being compared against. Our own `AssigneeType` SSOT has exactly two
 * non-null members (`user`, `agent`); there is no backend field that
 * distinguishes a scripted/non-AI automation from an LLM-backed agent hire
 * among `assignee_agent_id` values today (every currently *registered* LLC
 * adapter — `claude_code*`, `copilot_*`, `codex_subscription` — is itself an
 * AI coding agent). Inventing that split here would mean classifying by
 * `adapter_type` substrings never backed by an enum: exactly the "confident
 * wrong count" this issue exists to prevent, and a second fork of the
 * human/agent axis on top of the one #13970 already tracks. The `agent`
 * bucket is labelled "AI Agent" in the UI (`llc.orgChart.aiAgent`, already
 * used for the same fact on the org-chart drawer) because that is what our
 * agent hires *are*, without asserting a distinction the data doesn't carry.
 *
 * ## Defence against an unrecognised cell
 *
 * `buildExecutorRollupMatrix` routes any cell whose `executor_class` is not
 * one of the three known values into `unassigned` rather than dropping it —
 * a dropped cell would silently under-count the total, which is worse than a
 * cell landing in the bucket that already means "nobody's claim on this is
 * known good". `status` needs no equivalent guard: unlike `assignee_type`
 * (an unconstrained `String(16)` column), `WorkItemStatus` is a DB-level
 * `sa.Enum`, so the backend cannot emit a status value outside the closed
 * set `workItemTypes.ts` already declares.
 */

import type { WorkItem, WorkItemStatus } from '@/views/llc/workItemTypes'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ExecutorRollup')

/**
 * The executor class of a work item's assignee. Extends
 * `WorkItem['assignee_type']` (`'user' | 'agent' | null | undefined`) with
 * the one case that union cannot express on its own — see the module
 * docstring's "Vocabulary" section.
 */
export type ExecutorClass = NonNullable<WorkItem['assignee_type']> | 'unassigned'

/** Stable render order — a class never moves between renders. */
export const EXECUTOR_CLASSES: readonly ExecutorClass[] = ['user', 'agent', 'unassigned'] as const

/** One (executor_class, status) cell as the backend rollup endpoint sends it. */
export interface ExecutorRollupCell {
  executor_class: string
  status: string
  count: number
}

export interface ExecutorRollupResponse {
  cells: ExecutorRollupCell[]
}

/** Dense matrix: every known executor class, keyed to whatever statuses it has counts for. */
export type ExecutorRollupMatrix = Record<ExecutorClass, Partial<Record<WorkItemStatus, number>>>

function emptyMatrix(): ExecutorRollupMatrix {
  return { user: {}, agent: {}, unassigned: {} }
}

function isKnownExecutorClass(value: string): value is ExecutorClass {
  return (EXECUTOR_CLASSES as readonly string[]).includes(value)
}

/**
 * Build the dense matrix from the API's sparse cell list.
 *
 * A cell whose `executor_class` isn't one of the three known values is
 * folded into `unassigned` (logged, never dropped) — see the module
 * docstring's "Defence against an unrecognised cell". A cell with a
 * non-positive count is skipped: the backend's `GROUP BY` never emits one,
 * but a matrix built from untrusted input should not display a bucket that
 * claims a negative number of work items.
 */
export function buildExecutorRollupMatrix(cells: readonly ExecutorRollupCell[]): ExecutorRollupMatrix {
  const matrix = emptyMatrix()
  for (const cell of cells) {
    if (cell.count <= 0) continue
    const status = cell.status as WorkItemStatus
    let executorClass: ExecutorClass
    if (isKnownExecutorClass(cell.executor_class)) {
      executorClass = cell.executor_class
    } else {
      logger.warn(
        `Unrecognised executor_class "${cell.executor_class}" — counting ${cell.count} item(s) as unassigned rather than dropping them.`,
      )
      executorClass = 'unassigned'
    }
    const bucket = matrix[executorClass]
    bucket[status] = (bucket[status] ?? 0) + cell.count
  }
  return matrix
}

/** Total items in one executor class, across every status. */
export function executorClassTotal(matrix: ExecutorRollupMatrix, executorClass: ExecutorClass): number {
  return Object.values(matrix[executorClass]).reduce((sum, count) => sum + (count ?? 0), 0)
}

/** Every executor class's total, in `EXECUTOR_CLASSES` order. */
export function executorClassTotals(matrix: ExecutorRollupMatrix): Record<ExecutorClass, number> {
  const totals = {} as Record<ExecutorClass, number>
  for (const executorClass of EXECUTOR_CLASSES) {
    totals[executorClass] = executorClassTotal(matrix, executorClass)
  }
  return totals
}

/** Grand total across every class and status — the panel's "N work items" header. */
export function rollupTotal(matrix: ExecutorRollupMatrix): number {
  return EXECUTOR_CLASSES.reduce((sum, executorClass) => sum + executorClassTotal(matrix, executorClass), 0)
}

/** Every status that has a non-zero count somewhere in the matrix, in `WorkItemStatus` order. */
export function statusesPresent(matrix: ExecutorRollupMatrix, statusOrder: readonly WorkItemStatus[]): WorkItemStatus[] {
  const present = new Set<WorkItemStatus>()
  for (const executorClass of EXECUTOR_CLASSES) {
    for (const status of Object.keys(matrix[executorClass]) as WorkItemStatus[]) {
      if ((matrix[executorClass][status] ?? 0) > 0) present.add(status)
    }
  }
  return statusOrder.filter((status) => present.has(status))
}
