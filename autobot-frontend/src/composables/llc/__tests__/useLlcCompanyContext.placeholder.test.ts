// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21511: a route param that is the 'undefined'/'null' text of a link built from an unset id is no
// company: the context falls through to the next source and never writes the placeholder into the store.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { useLlcCompanyContext } from '../useLlcCompanyContext'

const route = vi.hoisted(() => ({ params: {} as Record<string, unknown>, query: {} as Record<string, unknown> }))
const get = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

function setup() {
  setActivePinia(createPinia())
  const store = useLlcCompanyStore()
  store.selectCompany('c1')
  const select = vi.spyOn(store, 'selectCompany')
  return { store, select, context: useLlcCompanyContext() }
}

describe('useLlcCompanyContext route company (#21511)', () => {
  beforeEach(() => {
    route.params = {}
    route.query = {}
    get.mockResolvedValue([])
  })

  it.each(['undefined', 'null'])('falls through a %s param to the store selection', async (placeholder) => {
    route.params = { companyId: placeholder }
    const { context, select } = setup()

    expect(await context.resolveCompanyId()).toBe('c1')
    expect(context.companyId.value).toBe('c1')
    expect(select).not.toHaveBeenCalledWith(placeholder)
  })

  it('still resolves a real param and writes it to the store', async () => {
    route.params = { companyId: 'c2' }
    const { context, select, store } = setup()

    expect(await context.resolveCompanyId()).toBe('c2')
    expect(select).toHaveBeenCalledWith('c2')
    expect(store.selectedCompanyId).toBe('c2')
  })

  it('reads the first element of a repeated param', async () => {
    route.params = { companyId: ['c3', 'c4'] }
    const { context } = setup()

    expect(await context.resolveCompanyId()).toBe('c3')
  })

  it('tolerates a route with no params object', async () => {
    route.params = undefined as unknown as Record<string, unknown>
    route.query = { company: 'c5' }
    const { context } = setup()

    expect(await context.resolveCompanyId()).toBe('c5')
  })
})
