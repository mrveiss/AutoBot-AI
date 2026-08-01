// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useTLSCredentials tests (#12614)
 *
 * Verifies the composable routes SLM TLS calls through the canonical SLM bridge
 * (a SlmClient instance) — not raw getSLMUrl()+fetch — and that the bridge is
 * wired with the composable's in-memory SLM token (read live). Also covers the
 * JSON, token-less authenticate() path (POST /api/auth/login, #1922) and
 * graceful-error / MFA-challenge behaviour.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

// The composable `new`s a SlmClient at module-import time, so the mock methods
// and the captured token getter must be hoisted (initialised before that runs).
const h = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  patchMock: vi.fn(),
  deleteMock: vi.fn(),
  rawMock: vi.fn(),
  // Token getter passed to the SlmClient constructor — asserts the SLM token is
  // sourced live from the composable's authToken.
  capturedTokenGetter: undefined as (() => string | null) | undefined,
}))

vi.mock('@/utils/slmClient', () => ({
  // Constructable mock — SlmClient is instantiated with `new` in the composable.
  SlmClient: vi.fn(function (this: Record<string, unknown>, getToken: () => string | null) {
    h.capturedTokenGetter = getToken
    this.get = h.getMock
    this.post = h.postMock
    this.patch = h.patchMock
    this.delete = h.deleteMock
    this.rawRequest = h.rawMock
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/cacheManagement', () => ({
  showSubtleErrorNotification: vi.fn(),
}))

import { useTLSCredentials } from '../useTLSCredentials'

describe('useTLSCredentials', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('constructs the SLM bridge with a live token getter backed by authToken', () => {
    const { setAuthToken } = useTLSCredentials()
    expect(typeof h.capturedTokenGetter).toBe('function')

    setAuthToken('slm-jwt')
    expect(h.capturedTokenGetter!()).toBe('slm-jwt')
  })

  it('fetchNodes GETs /api/nodes via the bridge and stores nodes', async () => {
    h.getMock.mockResolvedValue({ nodes: [{ node_id: 'n1' }] })
    const { fetchNodes, nodes } = useTLSCredentials()

    const result = await fetchNodes()

    expect(h.getMock).toHaveBeenCalledWith('/api/nodes')
    expect(nodes.value).toEqual([{ node_id: 'n1' }])
    expect(result).toEqual([{ node_id: 'n1' }])
  })

  it('createCredential POSTs the payload to the node tls-credentials endpoint', async () => {
    h.postMock.mockResolvedValue({ credential_id: 'c1', is_active: true })
    const { createCredential } = useTLSCredentials()

    const created = await createCredential('n1', {
      ca_cert: 'ca',
      server_cert: 'sc',
      server_key: 'sk',
    })

    expect(h.postMock).toHaveBeenCalledWith('/api/nodes/n1/tls-credentials', {
      ca_cert: 'ca',
      server_cert: 'sc',
      server_key: 'sk',
    })
    expect(created).toMatchObject({ credential_id: 'c1' })
  })

  it('updateCredential PATCHes the credential endpoint', async () => {
    h.patchMock.mockResolvedValue({ credential_id: 'c1', is_active: false })
    const { updateCredential } = useTLSCredentials()

    await updateCredential('c1', { is_active: false })

    expect(h.patchMock).toHaveBeenCalledWith('/api/tls/credentials/c1', { is_active: false })
  })

  it('deleteCredential DELETEs the credential endpoint and returns true', async () => {
    h.deleteMock.mockResolvedValue({})
    const { deleteCredential } = useTLSCredentials()

    const ok = await deleteCredential('c1')

    expect(h.deleteMock).toHaveBeenCalledWith('/api/tls/credentials/c1')
    expect(ok).toBe(true)
  })

  it('authenticate POSTs JSON credentials to /api/auth/login with skipAuth and stores the token', async () => {
    h.rawMock.mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ access_token: 'new-token' }),
    })
    const { authenticate, isAuthenticated } = useTLSCredentials()

    const ok = await authenticate('admin', 'pw')

    expect(ok).toBe(true)
    const [path, options] = h.rawMock.mock.calls[0]
    expect(path).toBe('/api/auth/login')
    expect(options.method).toBe('POST')
    expect(options.skipAuth).toBe(true)
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({ username: 'admin', password: 'pw' })
    expect(isAuthenticated()).toBe(true)
  })

  it('authenticate returns false when the bridge reports a non-OK response', async () => {
    h.rawMock.mockResolvedValue({ ok: false, json: vi.fn() })
    const { authenticate } = useTLSCredentials()

    await expect(authenticate('admin', 'bad')).resolves.toBe(false)
  })

  it('authenticate returns false (no crash) on an MFA-challenge response', async () => {
    h.rawMock.mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ requires_mfa: true, temp_token: 'tmp' }),
    })
    const { authenticate } = useTLSCredentials()

    // Returns false without throwing; the MFA temp_token is never stored as a
    // bearer (module-scoped authToken makes isAuthenticated() unreliable here).
    await expect(authenticate('admin', 'pw')).resolves.toBe(false)
  })

  it('fetchNodes returns [] and records the error message on rejection', async () => {
    h.getMock.mockRejectedValue(new Error('boom'))
    const { fetchNodes, error } = useTLSCredentials()

    const result = await fetchNodes()

    expect(result).toEqual([])
    expect(error.value).toBe('boom')
  })
})
