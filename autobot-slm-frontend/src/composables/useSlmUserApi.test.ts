// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 2) — proves the SLM user-management composable routes
 * every method through the canonical `slmApiClient`, serialises pagination as a
 * query string on the endpoint (the client takes a relative path, not an axios
 * `params` object), and returns parsed JSON directly. Non-auth endpoints → 401
 * session handling is the client's concern.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { useSlmUserApi } from './useSlmUserApi'

describe('useSlmUserApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
  })

  it('getSlmUsers GETs /slm-users with skip/limit query params and returns the body', async () => {
    const body = { users: [], total: 0, limit: 100, offset: 0 }
    mockGet.mockResolvedValue(body)

    const result = await useSlmUserApi().getSlmUsers()

    expect(mockGet).toHaveBeenCalledWith('/slm-users?skip=0&limit=100')
    expect(result).toEqual(body)
  })

  it('getSlmUsers honours custom skip/limit', async () => {
    mockGet.mockResolvedValue({ users: [] })

    await useSlmUserApi().getSlmUsers(20, 50)

    expect(mockGet).toHaveBeenCalledWith('/slm-users?skip=20&limit=50')
  })

  it('getAutobotUsers GETs /autobot-users with query params', async () => {
    mockGet.mockResolvedValue({ users: [] })

    await useSlmUserApi().getAutobotUsers()

    expect(mockGet).toHaveBeenCalledWith('/autobot-users?skip=0&limit=100')
  })

  it('getTeams GETs /autobot-teams with query params', async () => {
    mockGet.mockResolvedValue({ teams: [] })

    await useSlmUserApi().getTeams()

    expect(mockGet).toHaveBeenCalledWith('/autobot-teams?skip=0&limit=100')
  })

  it('createSlmUser POSTs the payload to /slm-users', async () => {
    const payload = { email: 'a@b.c', username: 'a', password: 'p' }
    mockPost.mockResolvedValue({ id: '1' })

    await useSlmUserApi().createSlmUser(payload)

    expect(mockPost).toHaveBeenCalledWith('/slm-users', payload)
  })

  it('createAutobotUser POSTs the payload to /autobot-users', async () => {
    const payload = { email: 'a@b.c', username: 'a', password: 'p' }
    mockPost.mockResolvedValue({ id: '1' })

    await useSlmUserApi().createAutobotUser(payload)

    expect(mockPost).toHaveBeenCalledWith('/autobot-users', payload)
  })

  it('deleteSlmUser DELETEs /slm-users/:id', async () => {
    mockDelete.mockResolvedValue({})

    await useSlmUserApi().deleteSlmUser('u1')

    expect(mockDelete).toHaveBeenCalledWith('/slm-users/u1')
  })

  it('deleteAutobotUser DELETEs /autobot-users/:id', async () => {
    mockDelete.mockResolvedValue({})

    await useSlmUserApi().deleteAutobotUser('u1')

    expect(mockDelete).toHaveBeenCalledWith('/autobot-users/u1')
  })

  it('changeSlmUserPassword POSTs new_password to the change-password path', async () => {
    mockPost.mockResolvedValue({})

    await useSlmUserApi().changeSlmUserPassword('u1', 'newpw')

    expect(mockPost).toHaveBeenCalledWith('/slm-users/u1/change-password', {
      new_password: 'newpw',
    })
  })

  it('changeAutobotUserPassword POSTs new_password to the change-password path', async () => {
    mockPost.mockResolvedValue({})

    await useSlmUserApi().changeAutobotUserPassword('u1', 'newpw')

    expect(mockPost).toHaveBeenCalledWith('/autobot-users/u1/change-password', {
      new_password: 'newpw',
    })
  })

  it('createTeam POSTs the payload to /autobot-teams', async () => {
    mockPost.mockResolvedValue({ id: 't1' })

    await useSlmUserApi().createTeam({ name: 'team' })

    expect(mockPost).toHaveBeenCalledWith('/autobot-teams', { name: 'team' })
  })

  it('deleteTeam DELETEs /autobot-teams/:id', async () => {
    mockDelete.mockResolvedValue({})

    await useSlmUserApi().deleteTeam('t1')

    expect(mockDelete).toHaveBeenCalledWith('/autobot-teams/t1')
  })

  it('addTeamMember POSTs user_id + role to the members path', async () => {
    mockPost.mockResolvedValue({})

    await useSlmUserApi().addTeamMember('t1', 'u1', 'admin')

    expect(mockPost).toHaveBeenCalledWith('/autobot-teams/t1/members', {
      user_id: 'u1',
      role: 'admin',
    })
  })

  it('addTeamMember defaults role to member', async () => {
    mockPost.mockResolvedValue({})

    await useSlmUserApi().addTeamMember('t1', 'u1')

    expect(mockPost).toHaveBeenCalledWith('/autobot-teams/t1/members', {
      user_id: 'u1',
      role: 'member',
    })
  })

  it('removeTeamMember DELETEs the member path', async () => {
    mockDelete.mockResolvedValue({})

    await useSlmUserApi().removeTeamMember('t1', 'u1')

    expect(mockDelete).toHaveBeenCalledWith('/autobot-teams/t1/members/u1')
  })
})
