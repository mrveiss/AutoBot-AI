// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

const client = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
vi.mock('@/plugins/api', () => ({ useApiClient: () => client }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useCompanyWorkflows, WorkflowWriteError } from '../useCompanyWorkflows'

const wf = (id: string, kind = 'workflow') => ({ workflow_id: id, name: id.toUpperCase(), kind })

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

beforeEach(() => {
  client.get.mockReset()
  client.post.mockReset()
  client.delete.mockReset()
})

describe('useCompanyWorkflows', () => {
  it('load hits the path-scoped list route and keeps only kind=workflow', async () => {
    client.get.mockResolvedValue([wf('a'), wf('skill', 'meta_skill')])
    const w = useCompanyWorkflows(() => 'co1')
    await w.load()
    expect(client.get).toHaveBeenCalledWith('/api/llc/workflows/co1')
    expect(w.workflows.value.map((x) => x.workflow_id)).toEqual(['a'])
    expect(w.state.value).toBe('ready')
    expect(w.isEmpty.value).toBe(false)
  })

  it('an empty list is ready and empty, not failed', async () => {
    client.get.mockResolvedValue([])
    const w = useCompanyWorkflows(() => 'co1')
    await w.load()
    expect(w.state.value).toBe('ready')
    expect(w.isEmpty.value).toBe(true)
  })

  it('a thrown load is failed, never an empty ready list', async () => {
    client.get.mockRejectedValue(new Error('HTTP 500: boom'))
    const w = useCompanyWorkflows(() => 'co1')
    await w.load()
    expect(w.state.value).toBe('failed')
    expect(w.isEmpty.value).toBe(false)
    expect(w.errorMessage.value).toBe('HTTP 500: boom')
  })

  it('create posts the body to the path route and reloads', async () => {
    client.post.mockResolvedValue(wf('n'))
    client.get.mockResolvedValue([wf('n')])
    const w = useCompanyWorkflows(() => 'co1')
    const body = { workflow_id: 'n', status: 'planned', kind: 'workflow', owner_role_id: 'r1' } as never
    await w.create(body)
    expect(client.post).toHaveBeenCalledWith('/api/llc/workflows/co1', body)
    expect(w.workflows.value).toHaveLength(1)
    expect(w.pending.value).toBe(false)
  })

  it('create surfaces a 403 as a typed forbidden error', async () => {
    client.post.mockRejectedValue(new Error('HTTP 403: admin only'))
    const w = useCompanyWorkflows(() => 'co1')
    const err = await w.create({} as never).catch((e) => e)
    expect(err).toBeInstanceOf(WorkflowWriteError)
    expect(err.forbidden).toBe(true)
    expect(w.errorMessage.value).toBe('HTTP 403: admin only')
    expect(w.pending.value).toBe(false)
  })

  it('attach and detach hit the role routes with encoded ids', async () => {
    client.post.mockResolvedValue({})
    client.delete.mockResolvedValue({})
    const w = useCompanyWorkflows(() => 'co1')
    await w.attach('r 1', 'wf/a')
    expect(client.post).toHaveBeenCalledWith('/api/llc/roles/co1/r%201/workflows', { workflow_id: 'wf/a' })
    await w.detach('r 1', 'wf/a')
    expect(client.delete).toHaveBeenCalledWith('/api/llc/roles/co1/r%201/workflows/wf%2Fa')
  })

  it('attachable disables the ids already attached', async () => {
    client.get.mockResolvedValue([wf('a'), wf('b')])
    const w = useCompanyWorkflows(() => 'co1')
    await w.load()
    expect(w.attachable(['a'])).toEqual([
      { id: 'a', label: 'A', disabled: true },
      { id: 'b', label: 'B', disabled: false },
    ])
  })

  it('discards the response of a company no longer shown', async () => {
    const first = deferred<unknown[]>()
    client.get.mockReturnValueOnce(first.promise).mockResolvedValueOnce([wf('two')])
    const company = ref('co1')
    const w = useCompanyWorkflows(() => company.value)
    const a = w.load()
    company.value = 'co2'
    await nextTick()
    first.resolve([wf('one')])
    await a
    await vi.waitFor(() => expect(w.workflows.value.map((x) => x.workflow_id)).toEqual(['two']))
    expect(client.get).toHaveBeenLastCalledWith('/api/llc/workflows/co2')
  })
})
