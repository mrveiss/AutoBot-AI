// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// usePlanDecision (#20853): in-flight guard, `deciding` reset, and error toasts.

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { usePlanDecision } from '../usePlanDecision'

function setup(approve = vi.fn().mockResolvedValue(true), reject = vi.fn().mockResolvedValue(true)) {
  const notify = vi.fn()
  const onApproved = vi.fn()
  const api = usePlanDecision({
    pendingApproval: ref({ workflow_id: 'wf-1' }),
    approvePlan: approve,
    rejectPlan: reject,
    notify,
    onApproved,
  })
  return { ...api, approve, reject, notify, onApproved }
}

describe('usePlanDecision', () => {
  it('does not send a second decision while one is in flight', async () => {
    let release!: (v: boolean) => void
    const approve = vi.fn(() => new Promise<boolean>((r) => (release = r)))
    const { handleApprovePlan, handleRejectPlan, deciding, reject } = setup(approve)
    const first = handleApprovePlan()
    expect(deciding.value).toBe(true)
    await handleApprovePlan()
    await handleRejectPlan()
    expect(approve).toHaveBeenCalledTimes(1)
    expect(reject).not.toHaveBeenCalled()
    release(true)
    await first
  })

  it('resets deciding after success and after failure', async () => {
    const ok = setup()
    await ok.handleApprovePlan()
    expect(ok.deciding.value).toBe(false)
    const bad = setup(vi.fn().mockRejectedValue(new Error('boom')))
    await bad.handleApprovePlan()
    expect(bad.deciding.value).toBe(false)
  })

  it('toasts an error when a request throws', async () => {
    const { handleApprovePlan, notify, onApproved } = setup(vi.fn().mockRejectedValue(new Error('x')))
    await handleApprovePlan()
    expect(notify).toHaveBeenCalledWith('workflow.builder.planApproveFailed', 'error')
    expect(onApproved).not.toHaveBeenCalled()
  })

  it('toasts an error when reject returns false or throws', async () => {
    const a = setup(undefined, vi.fn().mockResolvedValue(false))
    await a.handleRejectPlan()
    expect(a.notify).toHaveBeenCalledWith('workflow.builder.planRejectFailed', 'error')
    const b = setup(undefined, vi.fn().mockRejectedValue(new Error('x')))
    await b.handleRejectPlan()
    expect(b.notify).toHaveBeenCalledWith('workflow.builder.planRejectFailed', 'error')
  })

  it('notifies success on approve and reject', async () => {
    const s = setup()
    await s.handleApprovePlan()
    await s.handleRejectPlan()
    expect(s.notify).toHaveBeenCalledWith('workflow.builder.planApproved', 'success')
    expect(s.notify).toHaveBeenCalledWith('workflow.builder.planRejected', 'info')
  })
})
