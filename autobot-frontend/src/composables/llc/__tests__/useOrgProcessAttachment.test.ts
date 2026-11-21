// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21242: the org canvas attach / detach, through the company workflows service.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import type { ProcessNodeSource } from '@/composables/llc/orgCanvasGraph'
import { useOrgProcessAttachment } from '../useOrgProcessAttachment'

const attach = vi.fn()
const detach = vi.fn()
const reload = vi.fn()

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

const company = ref('c1')
const nodes = ref<ProcessNodeSource[]>([])

function setup() {
  return useOrgProcessAttachment({
    companyId: () => company.value,
    workflows: { attach, detach },
    processNodes: nodes,
    reload,
    describe: (err, key) => (err instanceof Error && err.message ? err.message : key),
  })
}

beforeEach(() => {
  attach.mockReset().mockResolvedValue(undefined)
  detach.mockReset().mockResolvedValue(undefined)
  reload.mockReset().mockResolvedValue(undefined)
  company.value = 'c1'
  nodes.value = [{ role_id: 'r1', role_name: 'Sales', workflow_id: 'wf-a' }]
})

describe('useOrgProcessAttachment (#21242)', () => {
  it('lists the workflows already on the chosen role', () => {
    const p = setup()
    p.roleId.value = 'r1'

    expect(p.attachedIds.value).toEqual(['wf-a'])
    p.roleId.value = 'r2'
    expect(p.attachedIds.value).toEqual([])
  })

  it('attaches the chosen workflow, clears the choice and reloads the canvas', async () => {
    const p = setup()
    p.roleId.value = 'r1'
    p.workflowId.value = 'wf-b'
    await p.attach()

    expect(attach).toHaveBeenCalledWith('r1', 'wf-b')
    expect(p.workflowId.value).toBe('')
    expect(reload).toHaveBeenCalledTimes(1)
    expect(p.error.value).toBeNull()
    expect(p.inFlight.value).toBe(false)
  })

  it('does nothing without a role and a workflow', async () => {
    const p = setup()
    p.roleId.value = 'r1'
    await p.attach()

    expect(attach).not.toHaveBeenCalled()
  })

  it('reports a refused attach, keeps the choice and leaves the canvas alone', async () => {
    attach.mockRejectedValueOnce(new Error('HTTP 403: not an admin'))
    const p = setup()
    p.roleId.value = 'r1'
    p.workflowId.value = 'wf-b'
    await p.attach()

    expect(p.error.value).toBe('HTTP 403: not an admin')
    expect(p.workflowId.value).toBe('wf-b')
    expect(reload).not.toHaveBeenCalled()
    expect(p.inFlight.value).toBe(false)
  })

  it('detaches and reloads, and reports a refusal under its own key', async () => {
    const p = setup()
    await p.detach('r1', 'wf-a')
    expect(detach).toHaveBeenCalledWith('r1', 'wf-a')
    expect(reload).toHaveBeenCalledTimes(1)

    detach.mockRejectedValueOnce(new Error(''))
    await p.detach('r1', 'wf-a')
    expect(p.error.value).toBe('llc.orgChart.detachError')
  })

  it('allows one mutation at a time', async () => {
    const gate = deferred<void>()
    attach.mockReturnValueOnce(gate.promise)
    const p = setup()
    p.roleId.value = 'r1'
    p.workflowId.value = 'wf-b'
    const first = p.attach()
    await p.detach('r1', 'wf-a')

    expect(detach).not.toHaveBeenCalled()
    gate.resolve()
    await first
  })

  it('writes nothing into a company that replaced the one the attach was sent for', async () => {
    const gate = deferred<void>()
    attach.mockReturnValueOnce(gate.promise)
    const p = setup()
    p.roleId.value = 'r1'
    p.workflowId.value = 'wf-b'
    const pending = p.attach()
    company.value = 'c2'
    gate.resolve()
    await pending

    expect(reload).not.toHaveBeenCalled()
    expect(p.workflowId.value).toBe('wf-b')
    expect(p.error.value).toBeNull()
  })

  it('does not show another company the error of a failed attach', async () => {
    const gate = deferred<void>()
    attach.mockReturnValueOnce(gate.promise.then(() => Promise.reject(new Error('HTTP 500: late'))))
    const p = setup()
    p.roleId.value = 'r1'
    p.workflowId.value = 'wf-b'
    const pending = p.attach()
    company.value = 'c2'
    gate.resolve()
    await pending

    expect(p.error.value).toBeNull()
  })
})
