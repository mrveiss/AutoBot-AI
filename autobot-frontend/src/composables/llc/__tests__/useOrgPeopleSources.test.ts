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

  it('issues both requests, and a completed load is not repeated', async () => {
    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    const s = setup()
    void s.load()
    await flushPromises()

    expect(get.mock.calls.map(([url]) => url).sort()).toEqual([
      '/api/llc/companies/c1/teams',
      '/api/llc/contacts/c1/involved',
    ])
    get.mockClear()
    await s.load()
    expect(get).not.toHaveBeenCalled()
  })

  it('keeps a completed load when a later call cannot resolve the company, and asks for nothing', async () => {
    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    let mode: 'ok' | 'reject' | 'empty' = 'ok'
    const s = useOrgPeopleSources({
      api: { get } as unknown as PeopleSourcesApi,
      resolveCompanyId: () => (mode === 'reject' ? Promise.reject(new Error('store down')) : Promise.resolve(mode === 'empty' ? '' : current)),
      companyId: () => current,
    })
    await s.load()
    expect(s.contacts.value).toEqual([contact])
    get.mockClear()

    mode = 'reject'
    await s.load()
    expect(s.contacts.value).toEqual([contact])
    expect(s.teams.value).toHaveLength(1)
    expect(s.contactsFailed.value).toBe(false)
    expect(s.teamsFailed.value).toBe(false)
    expect(s.loading.value).toBe(false)
    expect(get).not.toHaveBeenCalled()

    mode = 'empty'
    await s.load()
    expect(s.contacts.value).toEqual([contact])
    expect(s.teams.value).toHaveLength(1)
    expect(s.contactsFailed.value).toBe(false)
    expect(s.loading.value).toBe(false)
    expect(get).not.toHaveBeenCalled()
  })

  it('ends in the failed state, retryably, when the company resolution rejects', async () => {
    get.mockImplementation((url: string) => Promise.resolve(answer(url)))
    let fail = true
    const s = useOrgPeopleSources({
      api: { get } as unknown as PeopleSourcesApi,
      resolveCompanyId: () => (fail ? Promise.reject(new Error('store down')) : Promise.resolve(current)),
      companyId: () => current,
    })
    await s.load()
    expect(get).not.toHaveBeenCalled()
    expect(s.contactsFailed.value).toBe(true)
    expect(s.teamsFailed.value).toBe(true)
    expect(s.teamsAttempted.value).toBe(true)
    expect(s.loading.value).toBe(false)

    fail = false
    await s.load()
    expect(s.contacts.value).toEqual([contact])
    expect(s.contactsFailed.value).toBe(false)
  })

  describe('the cache belongs to one company', () => {
    const contactB = { id: 'p2', full_name: 'Bob', role_title: null, email: null, phone: null }
    const answerB = (url: string) =>
      url.endsWith('/involved')
        ? { with_role: [contactB], unassigned: [] }
        : { teams: [{ id: 't2', name: 'Other', member_user_ids: [] }] }

    async function loadedForC1() {
      get.mockImplementation((url: string) => Promise.resolve(answer(url)))
      const s = setup()
      await s.load()
      get.mockClear()
      return s
    }

    it('loads the new company after a switch and never shows the previous company people meanwhile', async () => {
      const s = await loadedForC1()
      expect(s.contacts.value).toEqual([contact])

      current = 'c2'
      const held = [deferred<unknown>(), deferred<unknown>()]
      get.mockImplementationOnce(() => held[0].promise).mockImplementationOnce(() => held[1].promise)
      const second = s.load()
      await flushPromises()

      expect(get).toHaveBeenCalledTimes(2)
      expect(get).toHaveBeenCalledWith('/api/llc/contacts/c2/involved')
      expect(get).toHaveBeenCalledWith('/api/llc/companies/c2/teams')
      expect(s.contacts.value).toEqual([])
      expect(s.teams.value).toEqual([])
      expect(s.teamsAttempted.value).toBe(false)

      held[0].resolve(answerB('/involved'))
      held[1].resolve(answerB('/teams'))
      await second
      expect(s.contacts.value).toEqual([contactB])
      expect(s.teams.value).toEqual([{ id: 't2', name: 'Other', member_user_ids: [] }])
    })

    it('still issues nothing for a second load of the same company', async () => {
      const s = await loadedForC1()
      await s.load()
      expect(get).not.toHaveBeenCalled()
      expect(s.contacts.value).toEqual([contact])
    })

    it('shows nothing of the previous company when the new one fails, and retries', async () => {
      const s = await loadedForC1()
      current = 'c2'
      get.mockImplementation(() => Promise.reject(new Error('down')))
      await s.load()

      expect(s.contacts.value).toEqual([])
      expect(s.teams.value).toEqual([])
      expect(s.contactsFailed.value).toBe(true)
      expect(s.teamsFailed.value).toBe(true)

      get.mockImplementation((url: string) => Promise.resolve(answerB(url)))
      await s.load()
      expect(s.contacts.value).toEqual([contactB])
      expect(s.contactsFailed.value).toBe(false)
    })
  })
})
