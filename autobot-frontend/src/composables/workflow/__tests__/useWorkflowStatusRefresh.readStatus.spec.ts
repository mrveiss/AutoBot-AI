// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// readStatus never replaces a workflow selected while its read was in flight (#21306).

import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useWorkflowStatusRefresh } from '../useWorkflowStatusRefresh'

interface W { workflow_id: string; steps?: Array<{ status: string }>; tag?: string }
type Reply = { success: boolean; data?: { workflow: W } | null }

const wf = (id: string, tag = 'read'): W => ({ workflow_id: id, tag })

function harness(shown: W | null = null) {
  const currentWorkflow = ref<W | null>(shown)
  const pending = new Map<string, (r: Reply) => void>()
  const fetchStatus = (id: string) => new Promise<Reply>((resolve) => pending.set(id, resolve))
  const refresh = useWorkflowStatusRefresh<W>({ currentWorkflow, activeWorkflows: ref<W[]>([]), fetchStatus })
  return { currentWorkflow, pending, ...refresh }
}

describe('readStatus (#21306)', () => {
  it('displays the workflow it read when the display did not change meanwhile', async () => {
    const h = harness(wf('wf-b', 'old'))
    const read = h.readStatus('wf-a')
    h.pending.get('wf-a')!({ success: true, data: { workflow: wf('wf-a') } })
    expect((await read)?.workflow_id).toBe('wf-a')
    expect(h.currentWorkflow.value?.workflow_id).toBe('wf-a')
  })

  it('displays the read when nothing was shown before it', async () => {
    const h = harness(null)
    const read = h.readStatus('wf-a')
    h.pending.get('wf-a')!({ success: true, data: { workflow: wf('wf-a') } })
    await read
    expect(h.currentWorkflow.value?.workflow_id).toBe('wf-a')
  })

  it('a slow read for A does not overwrite workflow B selected while it was in flight', async () => {
    const h = harness(null)
    const read = h.readStatus('wf-a')
    h.currentWorkflow.value = wf('wf-b', 'selected') // the user selects B while A is still being read
    h.pending.get('wf-a')!({ success: true, data: { workflow: wf('wf-a') } })
    expect((await read)?.workflow_id).toBe('wf-a') // the caller still gets what it read
    expect(h.currentWorkflow.value).toEqual(wf('wf-b', 'selected'))
  })

  it('refreshes the workflow that became displayed while the read was in flight', async () => {
    const h = harness(wf('wf-b'))
    const read = h.readStatus('wf-a')
    h.currentWorkflow.value = wf('wf-a', 'selected')
    h.pending.get('wf-a')!({ success: true, data: { workflow: wf('wf-a', 'fresh') } })
    await read
    expect(h.currentWorkflow.value?.tag).toBe('fresh')
  })

  it('a failed read leaves the display untouched and resolves null', async () => {
    const h = harness(wf('wf-b', 'kept'))
    const read = h.readStatus('wf-a')
    h.pending.get('wf-a')!({ success: false })
    expect(await read).toBeNull()
    expect(h.currentWorkflow.value?.tag).toBe('kept')
  })
})
