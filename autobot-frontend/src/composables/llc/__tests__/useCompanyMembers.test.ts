// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #19960: overlapping reloads in one company land newest-first, and a reload keeps the rows.

import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { useCompanyMembers, rolesToOffer, type MembersApi } from '../useCompanyMembers'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const row = (name: string) => ({ user_id: name, display_name: name, role: 'member' })

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function setup(get: MembersApi['get']) {
  let api!: ReturnType<typeof useCompanyMembers>
  const api0 = { get, patch: vi.fn(), delete: vi.fn() } as unknown as MembersApi
  mount(
    defineComponent({
      setup() {
        api = useCompanyMembers(api0, () => 'co1')
        return () => h('div')
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return api
}

describe('useCompanyMembers load ordering', () => {
  it('lets only the newest of two overlapping loads land', async () => {
    const first = deferred<unknown[]>()
    const second = deferred<unknown[]>()
    const get = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const api = setup(get as unknown as MembersApi['get'])
    const a = api.load()
    const b = api.load()
    second.resolve([row('new')])
    await b
    first.resolve([row('old')])
    await a
    expect(api.members.value.map((m) => m.user_id)).toEqual(['new'])
    expect(api.isLoading.value).toBe(false)
  })

  it('does not show the loading state when rows are already there', async () => {
    const get = vi.fn().mockResolvedValueOnce([row('x')]).mockReturnValueOnce(new Promise(() => undefined))
    const api = setup(get as unknown as MembersApi['get'])
    await api.load()
    void api.load()
    expect(api.isLoading.value).toBe(false)
    expect(api.members.value).toHaveLength(1)
  })
})

describe('rolesToOffer', () => {
  it('offers the grantable roles, and every role when no standing is known', () => {
    expect(rolesToOffer(['owner', 'admin'], ['admin'], true)).toEqual(['admin'])
    expect(rolesToOffer(['owner', 'admin'], [], true)).toEqual([])
    expect(rolesToOffer(['owner', 'admin'], [], false)).toEqual(['owner', 'admin'])
  })
})
