// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useCollaborationInvites reads the org-scoped user search route (#15738).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCollaborationInvites } from '../useCollaborationInvites'

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getServiceUrl: vi.fn(async () => 'http://backend'),
  },
}))

import { fetchWithAuth } from '@/utils/fetchWithAuth'
const mockFetch = fetchWithAuth as unknown as ReturnType<typeof vi.fn>

const ok = (body: unknown) => ({
  ok: true,
  status: 200,
  json: async () => body,
  text: async () => JSON.stringify(body),
})

describe('useCollaborationInvites', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('calls the scoped search route, not the admin user list', async () => {
    mockFetch.mockResolvedValue(ok({ users: [], available: true }))
    await useCollaborationInvites().fetchUsers('failed')
    const url = String(mockFetch.mock.calls[0][0])
    expect(url).toContain('/api/user-management/users/search')
    expect(url).toContain('limit=50')
    expect(url).not.toContain('include_inactive')
  })

  it('maps search results to invite users', async () => {
    mockFetch.mockResolvedValue(
      ok({ users: [{ id: 'u1', name: 'Ada Lovelace', type: 'user' }], available: true })
    )
    const { users, fetchUsers } = useCollaborationInvites()
    await fetchUsers('failed')
    expect(users.value).toEqual([
      { id: 'u1', username: 'Ada Lovelace', email: '', avatar: null, display_name: 'Ada Lovelace' },
    ])
  })
})
