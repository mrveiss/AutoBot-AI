// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #13942: the executor rollup panel counts work items by executor class
// (person / AI agent / unassigned) and by status. These tests pin the exact
// counts a rendered rollup must show — never "some number > 0" — and prove a
// mis-typed `executor_class` from the API never lands in a normal-looking
// bucket, only in `unassigned`.

import { describe, it, expect, vi } from 'vitest'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import {
  buildExecutorRollupMatrix,
  executorClassTotal,
  executorClassTotals,
  rollupTotal,
  statusesPresent,
  EXECUTOR_CLASSES,
} from '../executorRollup'
import type { ExecutorRollupCell } from '../executorRollup'

const STATUS_ORDER = ['backlog', 'ready', 'in_progress', 'in_review', 'done', 'blocked', 'cancelled'] as const

describe('buildExecutorRollupMatrix (#13942)', () => {
  it('places each cell in its declared (class, status) slot', () => {
    const cells: ExecutorRollupCell[] = [
      { executor_class: 'user', status: 'backlog', count: 2 },
      { executor_class: 'agent', status: 'in_progress', count: 3 },
      { executor_class: 'unassigned', status: 'backlog', count: 5 },
    ]
    const matrix = buildExecutorRollupMatrix(cells)

    expect(matrix.user.backlog).toBe(2)
    expect(matrix.agent.in_progress).toBe(3)
    expect(matrix.unassigned.backlog).toBe(5)
    // No cross-contamination between classes.
    expect(matrix.user.in_progress).toBeUndefined()
    expect(matrix.agent.backlog).toBeUndefined()
  })

  it('sums two cells of the same (class, status) rather than overwriting', () => {
    const cells: ExecutorRollupCell[] = [
      { executor_class: 'user', status: 'done', count: 2 },
      { executor_class: 'user', status: 'done', count: 3 },
    ]
    expect(buildExecutorRollupMatrix(cells).user.done).toBe(5)
  })

  it('folds an unrecognised executor_class into unassigned rather than dropping it', () => {
    const cells: ExecutorRollupCell[] = [{ executor_class: 'contact', status: 'backlog', count: 4 }]
    const matrix = buildExecutorRollupMatrix(cells)

    expect(matrix.unassigned.backlog).toBe(4)
    expect(rollupTotal(matrix)).toBe(4)
  })

  it('never lets a mis-typed discriminator inflate the person or agent bucket', () => {
    const cells: ExecutorRollupCell[] = [
      { executor_class: 'bogus', status: 'backlog', count: 7 },
      { executor_class: 'user', status: 'backlog', count: 1 },
    ]
    const matrix = buildExecutorRollupMatrix(cells)

    expect(matrix.user.backlog).toBe(1)
    expect(matrix.agent).toEqual({})
    expect(matrix.unassigned.backlog).toBe(7)
  })

  it('skips a non-positive count instead of showing a negative bucket', () => {
    const cells: ExecutorRollupCell[] = [{ executor_class: 'user', status: 'backlog', count: 0 }]
    expect(buildExecutorRollupMatrix(cells).user.backlog).toBeUndefined()
  })

  it('returns an empty-but-defined matrix for zero cells — never undefined buckets', () => {
    const matrix = buildExecutorRollupMatrix([])
    for (const executorClass of EXECUTOR_CLASSES) {
      expect(matrix[executorClass]).toEqual({})
    }
  })
})

describe('executorClassTotal / executorClassTotals / rollupTotal (#13942)', () => {
  const matrix = buildExecutorRollupMatrix([
    { executor_class: 'user', status: 'backlog', count: 2 },
    { executor_class: 'user', status: 'done', count: 1 },
    { executor_class: 'agent', status: 'in_progress', count: 4 },
    { executor_class: 'unassigned', status: 'backlog', count: 3 },
  ])

  it('sums across statuses for one class', () => {
    expect(executorClassTotal(matrix, 'user')).toBe(3)
    expect(executorClassTotal(matrix, 'agent')).toBe(4)
    expect(executorClassTotal(matrix, 'unassigned')).toBe(3)
  })

  it('reports a total per class in EXECUTOR_CLASSES order', () => {
    expect(executorClassTotals(matrix)).toEqual({ user: 3, agent: 4, unassigned: 3 })
  })

  it('the grand total is the sum of every class total, including unassigned', () => {
    expect(rollupTotal(matrix)).toBe(10)
  })

  it('the unassigned bucket is asserted directly, not derived as a remainder', () => {
    // A rollup with an unassigned cell absent must report 0, not "whatever is left".
    const withoutUnassigned = buildExecutorRollupMatrix([
      { executor_class: 'user', status: 'backlog', count: 2 },
    ])
    expect(executorClassTotal(withoutUnassigned, 'unassigned')).toBe(0)
  })
})

describe('statusesPresent (#13942)', () => {
  it('lists only statuses with a non-zero count, in declared order', () => {
    const matrix = buildExecutorRollupMatrix([
      { executor_class: 'agent', status: 'done', count: 1 },
      { executor_class: 'user', status: 'backlog', count: 2 },
    ])
    expect(statusesPresent(matrix, STATUS_ORDER)).toEqual(['backlog', 'done'])
  })

  it('is empty for an empty matrix', () => {
    expect(statusesPresent(buildExecutorRollupMatrix([]), STATUS_ORDER)).toEqual([])
  })
})
