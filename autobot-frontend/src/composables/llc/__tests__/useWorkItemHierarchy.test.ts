// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #20936: the hierarchy composable reads the two GETs by their full /api path and hides the report from a non-admin.

import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { HttpError } from '@autobot/ui'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useWorkItemHierarchy } from '../useWorkItemHierarchy'

const RULES = { rules: [{ type: 'task', allowed_parent_types: ['pbi'], project_required: true }] }
const ROW = {
  id: 'w1',
  identifier: 'WI-1',
  code: 'project_required',
  reason: 'a task has no project_id',
  type: 'task',
  parent_type: null,
}
const FOUND = { violations: [ROW], count: 1, truncated: false }

function refused(status: number): Error {
  return new HttpError(status, 'refused')
}

describe('useWorkItemHierarchy', () => {
  it('calls the full /api paths with the company id and stores what they answer', async () => {
    get.mockReset().mockResolvedValueOnce(RULES).mockResolvedValueOnce(FOUND)
    const h = useWorkItemHierarchy(ref('co 1'))
    await h.loadRules()
    await h.loadViolations()

    expect(get.mock.calls.map(c => c[0])).toEqual([
      '/api/llc/work-items/hierarchy-rules?company_id=co+1',
      '/api/llc/work-items/hierarchy-violations?company_id=co+1',
    ])
    expect(h.rules.value).toEqual(RULES.rules)
    expect(h.violations.value).toEqual(FOUND.violations)
    expect(h.canSeeViolations.value).toBe(true)
  })

  it('keeps the report hidden until the server has answered', async () => {
    get.mockReset().mockReturnValue(new Promise(() => {}))
    const h = useWorkItemHierarchy(ref('co1'))
    void h.loadViolations()
    await nextTick()
    expect(h.canSeeViolations.value).toBe(false)
  })

  it('hides the report on a 403, without an error state', async () => {
    get.mockReset().mockRejectedValueOnce(refused(403))
    const h = useWorkItemHierarchy(ref('co1'))
    await h.loadViolations()
    expect(h.canSeeViolations.value).toBe(false)
    expect(h.violationsFailed.value).toBe(false)
  })

  it('does not read a 401 (expired session) as "not an admin": the section stays, as a retryable failure', async () => {
    get.mockReset().mockRejectedValueOnce(refused(401))
    const h = useWorkItemHierarchy(ref('co1'))
    await h.loadViolations()
    expect(h.canSeeViolations.value).toBe(true)
    expect(h.violationsFailed.value).toBe(true)
  })

  it('clears the old company before the next fetch, and ignores a late answer for it', async () => {
    let lateRules!: (v: unknown) => void
    const company = ref('co1')
    get.mockReset().mockResolvedValueOnce(RULES).mockResolvedValueOnce(FOUND)
    const h = useWorkItemHierarchy(company)
    await h.loadRules()
    await h.loadViolations()

    get.mockReset().mockReturnValueOnce(new Promise(r => (lateRules = r))).mockResolvedValueOnce(FOUND)
    void h.loadRules()
    h.reset()
    expect(h.rules.value).toEqual([])
    expect(h.violations.value).toEqual([])
    expect(h.canSeeViolations.value).toBe(false)

    lateRules(RULES)
    await nextTick()
    expect(h.rules.value).toEqual([])
  })

  it('keeps the truncated flag from the answer', async () => {
    get.mockReset().mockResolvedValueOnce({ ...FOUND, truncated: true })
    const h = useWorkItemHierarchy(ref('co1'))
    await h.loadViolations()
    expect(h.truncated.value).toBe(true)
  })

  it('shows any other failure as a failure the admin can retry', async () => {
    get.mockReset().mockRejectedValueOnce(refused(500)).mockResolvedValueOnce(FOUND)
    const h = useWorkItemHierarchy(ref('co1'))
    await h.loadViolations()
    expect(h.canSeeViolations.value).toBe(true)
    expect(h.violationsFailed.value).toBe(true)

    await h.loadViolations()
    expect(h.violationsFailed.value).toBe(false)
    expect(h.violations.value).toHaveLength(1)
  })

  it('flags a rules failure and clears it on a retry', async () => {
    get.mockReset().mockRejectedValueOnce(refused(500)).mockResolvedValueOnce(RULES)
    const h = useWorkItemHierarchy(ref('co1'))
    await h.loadRules()
    expect(h.rulesFailed.value).toBe(true)
    await h.loadRules()
    expect(h.rulesFailed.value).toBe(false)
    expect(h.rules.value).toHaveLength(1)
  })
})
