// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 2) — proves the SSO composable routes every method
 * through the canonical `slmApiClient`, serialises list filters as a query
 * string, and preserves the historic "logout on 401" behavior for the
 * `/auth/sso/**` login-flow endpoints (which the client intentionally excludes
 * from its own session-clearing handler). The non-auth provider-CRUD endpoints
 * rely on the client's central 401 handling and do NOT re-trigger logout here.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()
const mockLogout = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ logout: mockLogout }),
}))

import { useSsoApi } from './useSsoApi'

describe('useSsoApi — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockPatch.mockReset()
    mockDelete.mockReset()
    mockLogout.mockReset()
  })

  it('listProviders GETs /sso-providers with no query when unfiltered', async () => {
    mockGet.mockResolvedValue({ providers: [], total: 0 })

    await useSsoApi().listProviders()

    expect(mockGet).toHaveBeenCalledWith('/sso-providers')
  })

  it('listProviders serialises org_id + active_only into the query string', async () => {
    mockGet.mockResolvedValue({ providers: [], total: 0 })

    await useSsoApi().listProviders('org-1', true)

    expect(mockGet).toHaveBeenCalledWith(
      '/sso-providers?org_id=org-1&active_only=true'
    )
  })

  it('createProvider POSTs the payload to /sso-providers', async () => {
    const payload = {
      provider_type: 'oauth2',
      name: 'g',
      config: {},
      is_active: true,
      is_social: false,
      allow_user_creation: true,
      default_role: 'user',
    }
    mockPost.mockResolvedValue({ id: '1' })

    await useSsoApi().createProvider(payload)

    expect(mockPost).toHaveBeenCalledWith('/sso-providers', payload)
  })

  it('getProvider GETs /sso-providers/:id', async () => {
    mockGet.mockResolvedValue({ id: '1' })

    await useSsoApi().getProvider('1')

    expect(mockGet).toHaveBeenCalledWith('/sso-providers/1')
  })

  it('updateProvider PATCHes /sso-providers/:id', async () => {
    mockPatch.mockResolvedValue({ id: '1' })

    await useSsoApi().updateProvider('1', { name: 'new' })

    expect(mockPatch).toHaveBeenCalledWith('/sso-providers/1', { name: 'new' })
  })

  it('deleteProvider DELETEs /sso-providers/:id', async () => {
    mockDelete.mockResolvedValue({})

    await useSsoApi().deleteProvider('1')

    expect(mockDelete).toHaveBeenCalledWith('/sso-providers/1')
  })

  it('testProvider GETs /sso-providers/:id/test', async () => {
    mockGet.mockResolvedValue({ success: true, message: 'ok' })

    await useSsoApi().testProvider('1')

    expect(mockGet).toHaveBeenCalledWith('/sso-providers/1/test')
  })

  it('getProvidersHealth GETs /sso-providers/health', async () => {
    mockGet.mockResolvedValue([])

    await useSsoApi().getProvidersHealth()

    expect(mockGet).toHaveBeenCalledWith('/sso-providers/health')
  })

  it('getActiveProviders GETs /auth/sso/providers', async () => {
    mockGet.mockResolvedValue([])

    await useSsoApi().getActiveProviders()

    expect(mockGet).toHaveBeenCalledWith('/auth/sso/providers')
  })

  it('initiateSSOLogin GETs /auth/sso/:id/login', async () => {
    mockGet.mockResolvedValue({ provider_id: '1', redirect_url: 'x' })

    await useSsoApi().initiateSSOLogin('1')

    expect(mockGet).toHaveBeenCalledWith('/auth/sso/1/login')
  })

  it('loginWithLDAP POSTs credentials to /auth/sso/ldap/login', async () => {
    mockPost.mockResolvedValue({ access_token: 't', token_type: 'bearer', expires_in: 3600 })

    await useSsoApi().loginWithLDAP('1', 'user', 'pw')

    expect(mockPost).toHaveBeenCalledWith('/auth/sso/ldap/login', {
      provider_id: '1',
      username: 'user',
      password: 'pw',
    })
  })

  it('logs out and re-throws on a 401 from an /auth/** login-flow endpoint', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 401: Unauthorized'))

    await expect(useSsoApi().getActiveProviders()).rejects.toThrow('HTTP 401')
    expect(mockLogout).toHaveBeenCalledTimes(1)
  })

  it('does NOT double-logout on a 401 from a non-auth provider-CRUD endpoint (client handles it)', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 401: Unauthorized'))

    await expect(useSsoApi().getProvider('1')).rejects.toThrow('HTTP 401')
    expect(mockLogout).not.toHaveBeenCalled()
  })

  it('does NOT log out on a non-401 error from an /auth/** endpoint', async () => {
    mockPost.mockRejectedValue(new Error('HTTP 400: Bad credentials'))

    await expect(useSsoApi().loginWithLDAP('1', 'user', 'bad')).rejects.toThrow('HTTP 400')
    expect(mockLogout).not.toHaveBeenCalled()
  })
})
