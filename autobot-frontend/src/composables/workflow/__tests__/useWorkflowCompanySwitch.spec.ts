// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The workflow builder keeps its instance on a company switch (#21502), so on a switch it must
// drop the unsaved draft, reload in place and say so only when a draft was dropped (#21520).

import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { discardWorkflowDraft, useWorkflowCompanySwitch } from '../useWorkflowCompanySwitch'

function draft() {
  return {
    naturalLanguageInput: ref(''),
    selectedStrategy: ref(''),
    workflowPlan: ref<unknown | null>(null),
    pendingApproval: ref<unknown | null>(null),
    currentWorkflow: ref<unknown | null>(null),
    workflowNodes: ref<unknown[]>([]),
    selectedNodeId: ref<string | null>(null),
  }
}

function setup(initialCompany = 'c1', onSwitch?: () => void) {
  const companyId = ref(initialCompany)
  const d = draft()
  const reload = vi.fn(async () => {})
  const onDraftDiscarded = vi.fn()
  useWorkflowCompanySwitch({ companyId: () => companyId.value, draft: d, reload, onDraftDiscarded, onSwitch })
  return { companyId, d, reload, onDraftDiscarded }
}

async function flush() {
  await nextTick()
  await Promise.resolve()
  await Promise.resolve()
}

describe('discardWorkflowDraft', () => {
  it('reports no draft for an untouched builder', () => {
    expect(discardWorkflowDraft(draft())).toBe(false)
  })

  it('clears every draft ref and reports one', () => {
    const d = draft()
    d.naturalLanguageInput.value = 'send the report'
    d.workflowNodes.value = [{ id: 'n1' }]
    d.selectedNodeId.value = 'n1'
    d.workflowPlan.value = { id: 'p' }
    expect(discardWorkflowDraft(d)).toBe(true)
    expect(d.naturalLanguageInput.value).toBe('')
    expect(d.workflowNodes.value).toEqual([])
    expect(d.selectedNodeId.value).toBeNull()
    expect(d.workflowPlan.value).toBeNull()
  })

  it('treats whitespace alone as no draft', () => {
    const d = draft()
    d.naturalLanguageInput.value = '   '
    expect(discardWorkflowDraft(d)).toBe(false)
  })
})

describe('useWorkflowCompanySwitch', () => {
  it('drops the draft, reloads in place and notifies on a switch with a draft', async () => {
    const { companyId, d, reload, onDraftDiscarded } = setup()
    d.naturalLanguageInput.value = 'goal for company one'
    d.pendingApproval.value = { id: 'a' }
    companyId.value = 'c2'
    await flush()
    expect(d.naturalLanguageInput.value).toBe('')
    expect(d.pendingApproval.value).toBeNull()
    expect(reload).toHaveBeenCalledTimes(1)
    expect(onDraftDiscarded).toHaveBeenCalledTimes(1)
  })

  it('reloads without a notice when there was no draft', async () => {
    const { companyId, reload, onDraftDiscarded } = setup()
    companyId.value = 'c2'
    await flush()
    expect(reload).toHaveBeenCalledTimes(1)
    expect(onDraftDiscarded).not.toHaveBeenCalled()
  })

  it('does nothing when the company id first resolves (that is a load, not a switch)', async () => {
    const { companyId, d, reload, onDraftDiscarded } = setup('')
    d.naturalLanguageInput.value = 'typed before the id resolved'
    companyId.value = 'c1'
    await flush()
    expect(d.naturalLanguageInput.value).toBe('typed before the id resolved')
    expect(reload).not.toHaveBeenCalled()
    expect(onDraftDiscarded).not.toHaveBeenCalled()
  })

  it('still reports the dropped draft when the reload fails', async () => {
    const { companyId, d, reload, onDraftDiscarded } = setup()
    reload.mockRejectedValueOnce(new Error('network'))
    d.selectedStrategy.value = 'parallel'
    companyId.value = 'c2'
    await flush()
    expect(onDraftDiscarded).toHaveBeenCalledTimes(1)
  })

  it('runs onSwitch on a switch but not on the first resolution', async () => {
    const onSwitch = vi.fn()
    const { companyId } = setup('c1', onSwitch)
    companyId.value = 'c2'
    await flush()
    expect(onSwitch).toHaveBeenCalledTimes(1)
    const again = setup('', onSwitch)
    again.companyId.value = 'c1'
    await flush()
    expect(onSwitch).toHaveBeenCalledTimes(1)
  })

  it('re-fetches when a reload finishes after a newer switch, and only the newest notifies', async () => {
    const companyId = ref('A')
    const d = draft()
    d.selectedStrategy.value = 'parallel'
    const releases: Array<() => void> = []
    const reload = vi.fn(() => new Promise<void>((res) => { releases.push(res) }))
    const onDraftDiscarded = vi.fn()
    useWorkflowCompanySwitch({ companyId: () => companyId.value, draft: d, reload, onDraftDiscarded })
    companyId.value = 'B'
    await flush()
    d.selectedStrategy.value = 'seq'
    companyId.value = 'C'
    await flush()
    expect(reload).toHaveBeenCalledTimes(2)
    releases[1]() // C's reload finishes first
    await flush()
    releases[0]() // B's late reload finishes after C began
    await flush()
    expect(reload).toHaveBeenCalledTimes(3) // stale B re-fetches so C's lists are not left overwritten
    releases[2]()
    await flush()
    expect(onDraftDiscarded).toHaveBeenCalledTimes(1) // only C's switch notifies
  })
})
