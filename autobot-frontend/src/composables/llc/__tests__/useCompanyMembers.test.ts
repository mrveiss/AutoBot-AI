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
// The response: rows, and the viewer's standing once beside them (#21096).
const reply = (rows: unknown[], can = false, grantable: string[] = []) => ({
  members: rows,
  viewer_role: null,
  viewer_can_manage: can,
  viewer_grantable_roles: grantable,
})

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
    const first = deferred<unknown>()
    const second = deferred<unknown>()
    const get = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const api = setup(get as unknown as MembersApi['get'])
    const a = api.load()
    const b = api.load()
    second.resolve(reply([row('new')]))
    await b
    first.resolve(reply([row('old')]))
    await a
    expect(api.members.value.map((m) => m.user_id)).toEqual(['new'])
    expect(api.isLoading.value).toBe(false)
  })

  it('does not show the loading state when rows are already there', async () => {
    const get = vi.fn().mockResolvedValueOnce(reply([row('x')])).mockReturnValueOnce(new Promise(() => undefined))
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

describe('useCompanyMembers viewerCanManage (#20542, #21096)', () => {
  it.each([[true, true], [false, false]])('reads the server flag %s as %s', async (flag, expected) => {
    const api = setup(vi.fn().mockResolvedValue(reply([row('a')], flag)) as unknown as MembersApi['get'])
    await api.load()
    expect(api.viewerCanManage.value).toBe(expected)
  })

  it('is true for a platform admin on a company with no member rows', async () => {
    const api = setup(vi.fn().mockResolvedValue(reply([], true, ['owner', 'admin'])) as unknown as MembersApi['get'])
    await api.load()
    expect(api.members.value).toEqual([])
    expect(api.viewerCanManage.value).toBe(true)
    expect(api.standingKnown.value).toBe(true)
    expect(api.grantableRoles.value).toEqual(['owner', 'admin'])
  })

  it('is false, and the standing unknown, before any load and after a failed one', async () => {
    const api = setup(vi.fn().mockRejectedValue(new Error('HTTP 503')) as unknown as MembersApi['get'])
    expect(api.viewerCanManage.value).toBe(false)
    expect(api.standingKnown.value).toBe(false)
    await api.load()
    expect(api.viewerCanManage.value).toBe(false)
    expect(api.standingKnown.value).toBe(false)
  })
})
