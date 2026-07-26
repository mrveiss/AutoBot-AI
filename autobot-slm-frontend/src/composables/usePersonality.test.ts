// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 3) — proves the personality composable is migrated onto
 * the canonical `slmApiClient`: every method routes through the shared client
 * with endpoints relative to the SLM API base under the `/personality` prefix
 * (base URL + SLM bearer token injected by the client) and works off parsed
 * JSON directly (no axios `.data`). Also asserts the `error`/`loading`/null
 * contract of the internal `_call` wrapper is preserved on failure.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { usePersonality } from './usePersonality'

describe('usePersonality — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockPut.mockReset()
    mockDelete.mockReset()
  })

  it('fetchProfiles GETs /personality/profiles + /personality/status', async () => {
    mockGet.mockImplementation((endpoint: string) => {
      if (endpoint === '/personality/profiles') {
        return Promise.resolve([{ id: '1', name: 'P', is_system: false, active: true }])
      }
      return Promise.resolve({ enabled: false, active_id: '1' })
    })

    const p = usePersonality()
    await p.fetchProfiles()

    expect(mockGet).toHaveBeenCalledWith('/personality/profiles')
    expect(mockGet).toHaveBeenCalledWith('/personality/status')
    expect(p.profiles.value).toHaveLength(1)
    expect(p.enabled.value).toBe(false)
    expect(p.loading.value).toBe(false)
  })

  it('fetchProfile GETs /personality/profiles/:id and returns the parsed body', async () => {
    mockGet.mockResolvedValue({ id: 'abc', name: 'X' })

    const result = await usePersonality().fetchProfile('abc')

    expect(mockGet).toHaveBeenCalledWith('/personality/profiles/abc')
    expect(result).toEqual({ id: 'abc', name: 'X' })
  })

  it('createProfile POSTs /personality/profiles then refreshes the list', async () => {
    mockPost.mockResolvedValue({ id: 'new', name: 'New' })
    mockGet.mockImplementation((endpoint: string) =>
      endpoint === '/personality/profiles'
        ? Promise.resolve([])
        : Promise.resolve({ enabled: true, active_id: null })
    )

    const result = await usePersonality().createProfile({ name: 'New' })

    expect(mockPost).toHaveBeenCalledWith('/personality/profiles', { name: 'New' })
    expect(result).toEqual({ id: 'new', name: 'New' })
  })

  it('updateProfile PUTs /personality/profiles/:id', async () => {
    mockPut.mockResolvedValue({ id: 'abc', name: 'Renamed' })

    await usePersonality().updateProfile('abc', { name: 'Renamed' })

    expect(mockPut).toHaveBeenCalledWith('/personality/profiles/abc', { name: 'Renamed' })
  })

  it('deleteProfile DELETEs /personality/profiles/:id and prunes local state', async () => {
    mockDelete.mockResolvedValue({})

    const ok = await usePersonality().deleteProfile('abc')

    expect(mockDelete).toHaveBeenCalledWith('/personality/profiles/abc')
    expect(ok).toBe(true)
  })

  it('activateProfile POSTs /personality/profiles/:id/activate then fetches active', async () => {
    mockPost.mockResolvedValue({})
    mockGet.mockResolvedValue({ id: 'abc' })

    const ok = await usePersonality().activateProfile('abc')

    expect(mockPost).toHaveBeenCalledWith('/personality/profiles/abc/activate')
    expect(mockGet).toHaveBeenCalledWith('/personality/active')
    expect(ok).toBe(true)
  })

  it('resetProfile POSTs /personality/profiles/:id/reset', async () => {
    mockPost.mockResolvedValue({ id: 'abc', name: 'Default' })

    const result = await usePersonality().resetProfile('abc')

    expect(mockPost).toHaveBeenCalledWith('/personality/profiles/abc/reset')
    expect(result).toEqual({ id: 'abc', name: 'Default' })
  })

  it('toggleEnabled POSTs /personality/toggle with the flag', async () => {
    mockPost.mockResolvedValue({})

    const ok = await usePersonality().toggleEnabled(false)

    expect(mockPost).toHaveBeenCalledWith('/personality/toggle', { enabled: false })
    expect(ok).toBe(true)
  })

  it('surfaces errors via `error` and returns null (null-on-error contract)', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 500: boom'))

    const p = usePersonality()
    const result = await p.fetchProfile('abc')

    expect(result).toBeNull()
    expect(p.error.value).toBe('HTTP 500: boom')
    expect(p.loading.value).toBe(false)
  })
})
