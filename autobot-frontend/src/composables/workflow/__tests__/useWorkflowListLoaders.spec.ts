// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// A read for the previous company must not write its rows over the current company's lists, and a
// failed read must stay distinguishable from an empty one (#21520).

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useWorkflowListLoaders } from '../useWorkflowListLoaders'

interface W { workflow_id: string }
type Resp = { success: boolean; data?: { workflows: W[] }; error?: string }

function deferred() {
  let resolve!: (r: Resp) => void
  const promise = new Promise<Resp>((res) => { resolve = res })
  return { promise, resolve }
}
const rows = (...ids: string[]): Resp => ({ success: true, data: { workflows: ids.map((workflow_id) => ({ workflow_id })) } })

function setup(fetchActive = vi.fn(async () => rows()), fetchCompleted = vi.fn(async () => rows())) {
  const activeWorkflows = ref<W[]>([])
  const completedWorkflows = ref<W[]>([])
  const restoreWaiting = vi.fn(async () => {})
  const loaders = useWorkflowListLoaders<W>({
    activeWorkflows, completedWorkflows, fetchActive, fetchCompleted, restoreWaiting,
    wrap: (fn) => fn(), forgetRemoved: () => {},
  })
  return { ...loaders, activeWorkflows, completedWorkflows, restoreWaiting }
}

describe('useWorkflowListLoaders', () => {
  it('writes the rows and reports success', async () => {
    const { loadActive, loadCompleted, activeWorkflows, completedWorkflows } = setup(
      vi.fn(async () => rows('a')), vi.fn(async () => rows('c')),
    )
    expect(await loadActive()).toBe(true)
    expect(await loadCompleted()).toBe(true)
    expect(activeWorkflows.value).toEqual([{ workflow_id: 'a' }])
    expect(completedWorkflows.value).toEqual([{ workflow_id: 'c' }])
  })

  it('reports an HTTP failure as false and leaves the list untouched', async () => {
    const { loadActive, loadCompleted, activeWorkflows } = setup(
      vi.fn(async () => ({ success: false, error: 'boom' })), vi.fn(async () => ({ success: false })),
    )
    activeWorkflows.value = [{ workflow_id: 'kept' }]
    expect(await loadActive()).toBe(false)
    expect(await loadCompleted()).toBe(false)
    expect(activeWorkflows.value).toEqual([{ workflow_id: 'kept' }])
  })

  it('lets a throwing fetcher propagate and leaves the lists untouched (#21807)', async () => {
    const { loadActive, loadCompleted, activeWorkflows, completedWorkflows, restoreWaiting } = setup(
      vi.fn(async () => { throw new Error('network') }), vi.fn(async () => { throw new Error('network') }),
    )
    activeWorkflows.value = [{ workflow_id: 'kept' }]
    await expect(loadActive()).rejects.toThrow('network')
    await expect(loadCompleted()).rejects.toThrow('network')
    expect(activeWorkflows.value).toEqual([{ workflow_id: 'kept' }])
    expect(completedWorkflows.value).toEqual([])
    expect(restoreWaiting).not.toHaveBeenCalled()
  })

  it('drops a superseded read so a late older reply cannot overwrite the newer rows', async () => {
    const first = deferred()
    const second = deferred()
    const fetchCompleted = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { loadCompleted, completedWorkflows } = setup(undefined, fetchCompleted)
    const older = loadCompleted()
    const newer = loadCompleted()
    second.resolve(rows('X', 'Y'))
    await newer
    first.resolve(rows('X'))
    expect(await older).toBe(true) // superseded is not a failure
    expect(completedWorkflows.value.map((w) => w.workflow_id)).toEqual(['X', 'Y'])
  })

  it('invalidate() revokes in-flight reads for both lists and skips the waiting-approval restore', async () => {
    const a = deferred()
    const c = deferred()
    const { loadActive, loadCompleted, invalidate, activeWorkflows, completedWorkflows, restoreWaiting } = setup(
      vi.fn(() => a.promise), vi.fn(() => c.promise),
    )
    const pendingActive = loadActive()
    const pendingCompleted = loadCompleted()
    invalidate() // company switch
    a.resolve(rows('from-previous-company'))
    c.resolve(rows('from-previous-company'))
    await Promise.all([pendingActive, pendingCompleted])
    expect(activeWorkflows.value).toEqual([])
    expect(completedWorkflows.value).toEqual([])
    expect(restoreWaiting).not.toHaveBeenCalled()
  })
})
