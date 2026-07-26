// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 4) — proves the code-source composable routes every
 * method through the canonical `slmApiClient` with endpoints relative to the
 * API base (base URL + bearer token injected by the client) and returns parsed
 * JSON directly (no axios `.data`). Also asserts the graceful error semantics
 * survive the switch to the throw-on-error client: `error.value` is populated
 * from the thrown message and the methods keep their `null`/`false` returns.
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

import { useCodeSource } from './useCodeSource'

describe('useCodeSource — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
  })

  it('fetchCodeSource GETs /code-source and stores the parsed body', async () => {
    const body = { node_id: 'n1', is_active: true }
    mockGet.mockResolvedValue(body)

    const cs = useCodeSource()
    await cs.fetchCodeSource()

    expect(mockGet).toHaveBeenCalledWith('/code-source')
    expect(cs.codeSource.value).toEqual(body)
    expect(cs.error.value).toBeNull()
    expect(cs.isLoading.value).toBe(false)
  })

  it('fetchCodeSource populates error.value from the thrown message', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 500: boom'))

    const cs = useCodeSource()
    await cs.fetchCodeSource()

    expect(cs.error.value).toBe('HTTP 500: boom')
    expect(cs.isLoading.value).toBe(false)
  })

  it('assignCodeSource POSTs to /code-source/assign and returns the body', async () => {
    const body = { node_id: 'n1', is_active: true }
    mockPost.mockResolvedValue(body)

    const cs = useCodeSource()
    const result = await cs.assignCodeSource('n1', '/repo', 'main')

    expect(mockPost).toHaveBeenCalledWith('/code-source/assign', {
      node_id: 'n1',
      repo_path: '/repo',
      branch: 'main',
    })
    expect(result).toEqual(body)
    expect(cs.codeSource.value).toEqual(body)
  })

  it('assignCodeSource uses the documented defaults for repoPath/branch', async () => {
    mockPost.mockResolvedValue({ node_id: 'n1' })

    await useCodeSource().assignCodeSource('n1')

    expect(mockPost).toHaveBeenCalledWith('/code-source/assign', {
      node_id: 'n1',
      repo_path: '/opt/autobot/code_source',
      branch: 'Dev_new_gui',
    })
  })

  it('assignCodeSource returns null and sets error.value on failure', async () => {
    mockPost.mockRejectedValue(new Error('HTTP 400: bad node'))

    const cs = useCodeSource()
    const result = await cs.assignCodeSource('n1')

    expect(result).toBeNull()
    expect(cs.error.value).toBe('HTTP 400: bad node')
  })

  it('removeCodeSource DELETEs /code-source/assign and clears the state', async () => {
    mockDelete.mockResolvedValue({})

    const cs = useCodeSource()
    cs.codeSource.value = { node_id: 'n1' } as never
    const ok = await cs.removeCodeSource()

    expect(mockDelete).toHaveBeenCalledWith('/code-source/assign')
    expect(ok).toBe(true)
    expect(cs.codeSource.value).toBeNull()
  })

  it('removeCodeSource returns false and sets error.value on failure', async () => {
    mockDelete.mockRejectedValue(new Error('HTTP 409: conflict'))

    const cs = useCodeSource()
    const ok = await cs.removeCodeSource()

    expect(ok).toBe(false)
    expect(cs.error.value).toBe('HTTP 409: conflict')
  })

  it('clearError resets error.value', () => {
    const cs = useCodeSource()
    cs.error.value = 'x'
    cs.clearError()
    expect(cs.error.value).toBeNull()
  })
})
