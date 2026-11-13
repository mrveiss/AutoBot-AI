// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21469: the org chart's people sources, off the view — a switched company's late answer, and a throw.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useOrgPeopleSources, type PeopleSourcesApi } from '../useOrgPeopleSources'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

const get = vi.fn()
let current = 'c1'
const contact = { id: 'p1', full_name: 'Ada', role_title: null, email: null, phone: null }

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function setup(companyId: () => string = () => current) {
  return useOrgPeopleSources({
    api: { get } as unknown as PeopleSourcesApi,
    resolveCompanyId: () => Promise.resolve(current),
    companyId,
  })
}

function answer(url: string) {
  if (url.endsWith('/involved')) return { with_role: [contact], unassigned: [] }
  return { teams: [{ id: 't1', name: 'Core', member_user_ids: [] }] }
}

beforeEach(() => {
  get.mockReset()
  current = 'c1'
})

describe('useOrgPeopleSources (#21469)', () => {
  it('reads both sources of the company through the declared paths', async () => {
    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    const s = setup()
    await s.load()

    expect(get).toHaveBeenCalledWith('/api/llc/contacts/c1/involved')
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/teams')
    expect(s.contacts.value).toEqual([contact])
    expect(s.teams.value).toHaveLength(1)
  })

  it('drops the answer of a company the view has switched away from, and loads the new one on the next call', async () => {
    const held = [deferred<unknown>(), deferred<unknown>()]
    get.mockImplementationOnce(() => held[0].promise).mockImplementationOnce(() => held[1].promise)
    const s = setup()
    const first = s.load()
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)

    current = 'c2'
    held[0].resolve(answer('/involved'))
    held[1].resolve(answer('/teams'))
    await first

    expect(s.contacts.value).toEqual([])
    expect(s.teams.value).toEqual([])
    expect(s.teamsAttempted.value).toBe(false)
    expect(s.contactsFailed.value).toBe(false)
    expect(s.teamsFailed.value).toBe(false)
    expect(s.loading.value).toBe(false)

    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    await s.load()

    expect(get).toHaveBeenCalledWith('/api/llc/contacts/c2/involved')
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c2/teams')
    expect(s.contacts.value).toEqual([contact])
    expect(s.teamsAttempted.value).toBe(true)
  })

  it('ends in the failed state, with the guard released, when the api throws synchronously', async () => {
    get.mockImplementation(() => {
      throw new Error('boom')
    })
    const s = setup()
    await s.load()

    expect(s.contactsFailed.value).toBe(true)
    expect(s.teamsFailed.value).toBe(true)
    expect(s.contacts.value).toEqual([])
    expect(s.loading.value).toBe(false)

    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    await s.load()
    expect(s.contactsFailed.value).toBe(false)
    expect(s.contacts.value).toEqual([contact])
  })

  it('ends in the same failed state, not an unhandled rejection, when the apply step throws', async () => {
    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    let calls = 0
    const s = setup(() => {
      calls += 1
      if (calls > 1) throw new Error('view gone')
      return current
    })
    await expect(s.load()).resolves.toBeUndefined()

    expect(s.contactsFailed.value).toBe(true)
    expect(s.teamsFailed.value).toBe(true)
    expect(s.teamsAttempted.value).toBe(true)
    expect(s.loading.value).toBe(false)
  })
})
