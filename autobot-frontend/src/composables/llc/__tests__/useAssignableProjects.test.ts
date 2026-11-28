// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #18978: overlapping project loads land newest-first; a late older response is dropped.

import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useAssignableProjects } from '../useAssignableProjects'

const project = (id: string, lifecycle_state = 'active') => ({ id, name: id, lifecycle_state })

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useAssignableProjects load ordering', () => {
  it('keeps the newer result when the older response arrives last', async () => {
    const first = deferred<unknown[]>()
    const second = deferred<unknown[]>()
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { projects, isLoadingProjects, loadProjects } = useAssignableProjects(ref('co1'))

    const a = loadProjects()
    const b = loadProjects()
    second.resolve([project('new')])
    await b
    first.resolve([project('old')])
    await a

    expect(projects.value.map(p => p.id)).toEqual(['new'])
    expect(isLoadingProjects.value).toBe(false)
  })

  it('does not let a late older failure flag the newer load as failed', async () => {
    const first = deferred<unknown[]>()
    const second = deferred<unknown[]>()
    get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { projects, projectsFailed, loadProjects } = useAssignableProjects(ref('co1'))

    const a = loadProjects()
    const b = loadProjects()
    second.resolve([project('new'), project('gone', 'archived')])
    await b
    first.reject(new Error('boom'))
    await a

    expect(projectsFailed.value).toBe(false)
    expect(projects.value.map(p => p.id)).toEqual(['new'])
  })
})

describe('useAssignableProjects company change (#20930)', () => {
  it('clears the old list, ignores a load still in flight, and loads the new company', async () => {
    const stale = deferred<unknown[]>()
    get.mockReset()
    get.mockReturnValueOnce(stale.promise).mockResolvedValueOnce([project('fresh')])
    const company = ref('co1')
    const { projects, isLoadingProjects, loadProjects } = useAssignableProjects(company)

    const inFlight = loadProjects()
    company.value = 'co2'
    await nextTick()
    stale.resolve([project('old-company')])
    await inFlight
    await new Promise(resolve => setTimeout(resolve))

    expect(get).toHaveBeenLastCalledWith('/api/llc/companies/co2/projects')
    expect(projects.value.map(p => p.id)).toEqual(['fresh'])
    expect(isLoadingProjects.value).toBe(false)
  })
})
