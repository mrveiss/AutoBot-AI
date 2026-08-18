// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13956: the assignee / reviewer / handoff pickers all read this composable,
// so it is the one place that decides who can be given work.

import { describe, it, expect, beforeEach, vi } from 'vitest'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useCompanyPeople } from '../useCompanyPeople'

function respond(members: unknown[]): void {
  // String(url): the mock is also called once with no argument between tests,
  // after mockReset clears the implementation.
  get.mockImplementation((url?: string) => {
    if (String(url).includes('/members')) return Promise.resolve(members)
    return Promise.resolve({ nodes: [] })
  })
}

describe('useCompanyPeople and inactive members (#13956)', () => {
  beforeEach(() => get.mockReset())

  it('does not offer a deactivated member as an assignee', async () => {
    respond([
      { user_id: 'u1', display_name: 'Ada', role: 'lead', is_active: true },
      { user_id: 'u2', display_name: 'Grace', role: 'member', is_active: false },
    ])
    const { humans, inactiveHumans, load } = useCompanyPeople('c1')
    await load()

    expect(humans.value.map((h) => h.name)).toEqual(['Ada'])
    // Reported, not silently dropped: a shorter list with no explanation reads
    // as "those people are gone from the company", a different claim.
    expect(inactiveHumans.value.map((h) => h.name)).toEqual(['Grace'])
  })

  it('offers everyone when the server omits the field entirely', async () => {
    // A backend that predates this field sends no `is_active`. Treating absent
    // as inactive would empty every picker during a rolling update.
    respond([
      { user_id: 'u1', display_name: 'Ada', role: 'lead' },
      { user_id: 'u2', display_name: 'Grace', role: 'member' },
    ])
    const { humans, inactiveHumans, load } = useCompanyPeople('c1')
    await load()

    expect(humans.value).toHaveLength(2)
    expect(inactiveHumans.value).toHaveLength(0)
  })
})
