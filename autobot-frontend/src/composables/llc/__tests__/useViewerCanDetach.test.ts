// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20682: the card's detach buttons show only to whom the server allows (owner/admin of THIS company).
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { mayDetach, useViewerCanDetach } from '../useViewerCanDetach'

const apiWith = (rows: unknown) => ({ get: vi.fn().mockResolvedValue(rows) })

describe('mayDetach', () => {
  it.each([
    ['owner', true],
    ['admin', true],
    ['member', false],
    ['guest', false],
    ['lead', false],
    [null, false],
    [undefined, false],
  ])('%s -> %s', (role, expected) => {
    expect(mayDetach(role as string | null | undefined)).toBe(expected)
  })
})

describe('useViewerCanDetach', () => {
  it('an admin of the company can detach', async () => {
    const api = apiWith([{ viewer_role: 'admin' }])
    const { canDetach } = useViewerCanDetach(api, ref('c1'))
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/api/llc/companies/c1/members')
    expect(canDetach.value).toBe(true)
  })

  it('a plain member, a non-member and an empty list cannot', async () => {
    for (const rows of [[{ viewer_role: 'member' }], [{ viewer_role: null }], []]) {
      const { canDetach } = useViewerCanDetach(apiWith(rows), ref('c1'))
      await flushPromises()
      expect(canDetach.value).toBe(false)
    }
  })

  it('a failed read hides the buttons', async () => {
    const { canDetach } = useViewerCanDetach({ get: vi.fn().mockRejectedValue(new Error('x')) }, ref('c1'))
    await flushPromises()
    expect(canDetach.value).toBe(false)
  })

  it('moving to another company drops the earlier standing', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce([{ viewer_role: 'owner' }])
      .mockResolvedValueOnce([{ viewer_role: 'member' }])
    const id = ref('c1')
    const { canDetach } = useViewerCanDetach({ get }, id)
    await flushPromises()
    expect(canDetach.value).toBe(true)
    id.value = 'c2'
    await flushPromises()
    expect(canDetach.value).toBe(false)
  })
})
