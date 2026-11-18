// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useCollaborationInvite reads the org-scoped user search route (#15738).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCollaborationInvite } from '../useCollaborationInvite'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn() },
}))

import apiClient from '@/utils/ApiClient'
const mockGet = apiClient.get as unknown as ReturnType<typeof vi.fn>

describe('useCollaborationInvite', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('calls the scoped search route, not the admin user list', async () => {
    mockGet.mockResolvedValue({ users: [], available: true })
    await useCollaborationInvite().fetchUsers('failed')
    const url = mockGet.mock.calls[0][0] as string
    expect(url).toContain('/user-management/users/search')
    expect(url).toContain('limit=50')
    expect(url).not.toMatch(/user-management\/users\?/)
  })

  it('maps search results to invite users', async () => {
    mockGet.mockResolvedValue({
      users: [{ id: 'u1', name: 'Ada Lovelace', type: 'user' }],
      available: true,
    })
    const { users, errorMessage, fetchUsers } = useCollaborationInvite()
    await fetchUsers('failed')
    expect(errorMessage.value).toBeNull()
    expect(users.value).toEqual([
      { id: 'u1', username: 'Ada Lovelace', email: '', avatar: null, display_name: 'Ada Lovelace' },
    ])
  })

  it('reports the failure message when search is unavailable', async () => {
    mockGet.mockResolvedValue({ users: [], available: false })
    const { users, errorMessage, fetchUsers } = useCollaborationInvite()
    await fetchUsers('failed')
    expect(users.value).toEqual([])
    expect(errorMessage.value).toBe('failed')
  })
})
