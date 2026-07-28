// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 1) — proves the MFA composable is migrated onto the
 * canonical `slmApiClient`: every method routes through the shared client with
 * endpoints relative to the API base (base URL + bearer token are injected by
 * the client), returns the parsed JSON body directly (no axios `.data`), and
 * preserves the historic "logout on 401" behavior even though the client itself
 * opts out of session-clearing for /mfa/ (auth) endpoints.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockLogout = vi.fn()

// The migrated composable must talk to the canonical client, not axios.
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ logout: mockLogout }),
}))

import { useMfaApi } from './useMfaApi'

describe('useMfaApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockLogout.mockReset()
  })

  it('getMFAStatus GETs /mfa/status via slmApiClient and returns the parsed body directly', async () => {
    const status = {
      enabled: true,
      method: 'totp',
      backup_codes_remaining: 8,
      last_verified_at: null,
    }
    mockGet.mockResolvedValue(status)

    const result = await useMfaApi().getMFAStatus()

    expect(mockGet).toHaveBeenCalledWith('/mfa/status')
    expect(result).toEqual(status)
  })

  it('setupMFA POSTs /mfa/setup (no body) and returns the parsed body', async () => {
    const setup = { secret: 's', otpauth_uri: 'otpauth://x', backup_codes: ['a'] }
    mockPost.mockResolvedValue(setup)

    const result = await useMfaApi().setupMFA()

    expect(mockPost).toHaveBeenCalledWith('/mfa/setup')
    expect(result).toEqual(setup)
  })

  it('verifySetup POSTs the code to /mfa/verify-setup', async () => {
    mockPost.mockResolvedValue({ success: true, message: 'ok' })

    const result = await useMfaApi().verifySetup('123456')

    expect(mockPost).toHaveBeenCalledWith('/mfa/verify-setup', { code: '123456' })
    expect(result).toEqual({ success: true, message: 'ok' })
  })

  it('verifyLogin POSTs code + temp_token to /mfa/verify-login', async () => {
    mockPost.mockResolvedValue({ success: true, message: 'ok', access_token: 't' })

    const result = await useMfaApi().verifyLogin('123456', 'temp-abc')

    expect(mockPost).toHaveBeenCalledWith('/mfa/verify-login', {
      code: '123456',
      temp_token: 'temp-abc',
    })
    expect(result.access_token).toBe('t')
  })

  it('disableMFA POSTs the password to /mfa/disable', async () => {
    mockPost.mockResolvedValue({})

    await useMfaApi().disableMFA('pw')

    expect(mockPost).toHaveBeenCalledWith('/mfa/disable', { password: 'pw' })
  })

  it('regenerateBackupCodes POSTs the password to /mfa/backup-codes', async () => {
    mockPost.mockResolvedValue({ backup_codes: ['x', 'y'] })

    const result = await useMfaApi().regenerateBackupCodes('pw')

    expect(mockPost).toHaveBeenCalledWith('/mfa/backup-codes', { password: 'pw' })
    expect(result.backup_codes).toEqual(['x', 'y'])
  })

  it('logs out and re-throws on a 401 (client opts out for /mfa/, composable preserves it)', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 401: Unauthorized'))

    await expect(useMfaApi().getMFAStatus()).rejects.toThrow('HTTP 401')
    expect(mockLogout).toHaveBeenCalledTimes(1)
  })

  it('does NOT log out on a non-401 error (e.g. wrong code → 400)', async () => {
    mockPost.mockRejectedValue(new Error('HTTP 400: Invalid code'))

    await expect(useMfaApi().verifySetup('000000')).rejects.toThrow('HTTP 400')
    expect(mockLogout).not.toHaveBeenCalled()
  })
})
