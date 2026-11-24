// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22191: a host's VNC password is created on first set and REPLACED on edit, so an existing host
 * can get one without being re-created.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const createSecret = vi.fn(async (..._a: unknown[]) => ({}))
const updateSecret = vi.fn(async (..._a: unknown[]) => ({}))
const getSecrets = vi.fn(async (..._a: unknown[]) => ({ secrets: [] as unknown[] }))
vi.mock('@/utils/SecretsApiClient', () => ({ secretsApiClient: { createSecret: (...a: unknown[]) => createSecret(...a), updateSecret: (...a: unknown[]) => updateSecret(...a), getSecrets: (...a: unknown[]) => getSecrets(...a) } }))
vi.mock('@/utils/ApiClient', () => ({ default: {} }))

import { createVncCompanion } from '../useSecretsInfraApi'

const t = (key: string) => key
const form = { type: 'infrastructure_host', name: 'box', host: 'h', capabilities: ['ssh', 'vnc'], vnc_password: 'pw' }  // pragma: allowlist secret
const hostData = { scope: 'general', chat_id: null }

describe('createVncCompanion', () => {
  beforeEach(() => { createSecret.mockClear(); updateSecret.mockClear(); getSecrets.mockReset(); getSecrets.mockResolvedValue({ secrets: [] }) })

  it('creates a linked password secret when the host has none', async () => {
    await createVncCompanion({ data: { id: 'h1' } }, form, hostData, t)
    expect(createSecret).toHaveBeenCalledTimes(1)
    const body = createSecret.mock.calls[0][0] as Record<string, unknown>
    expect(body).toMatchObject({ type: 'password', value: 'pw', metadata: { vnc_host_id: 'h1' } })
    expect(updateSecret).not.toHaveBeenCalled()
  })

  it('replaces the value of the already linked secret on edit', async () => {
    getSecrets.mockResolvedValue({ secrets: [{ id: 's9', type: 'password', metadata: { vnc_host_id: 'h1' } }, { id: 's8', type: 'password', metadata: { vnc_host_id: 'other' } }] })
    await createVncCompanion({ data: { id: 'h1' } }, form, hostData, t)
    expect(updateSecret).toHaveBeenCalledWith('s9', { value: 'pw' }, { chatId: null })
    expect(createSecret).not.toHaveBeenCalled()
  })

  it('a failed refetch surfaces and writes nothing (no stale-list fallback)', async () => {
    getSecrets.mockImplementation(async () => { throw new Error('list failed') })
    await expect(createVncCompanion({ data: { id: 'h1' } }, form, hostData, t)).rejects.toThrow('list failed')
    expect(createSecret).not.toHaveBeenCalled()
    expect(updateSecret).not.toHaveBeenCalled()
  })

  it('uses a freshly fetched list, so a stale form list cannot cause a duplicate', async () => {
    getSecrets.mockResolvedValue({ secrets: [{ id: 's7', type: 'password', metadata: { vnc_host_id: 'h1' } }] })
    await createVncCompanion({ data: { id: 'h1' } }, form, hostData, t)
    expect(updateSecret).toHaveBeenCalledWith('s7', { value: 'pw' }, { chatId: null })
    expect(createSecret).not.toHaveBeenCalled()
  })

  it.each([
    ['no password typed', { ...form, vnc_password: '' }], // pragma: allowlist secret
    ['no vnc capability', { ...form, capabilities: ['ssh'] }],
    ['not a host', { ...form, type: 'api_key' }],
  ])('does nothing for %s', async (_n, f) => {
    await createVncCompanion({ data: { id: 'h1' } }, f, hostData, t)
    expect(createSecret).not.toHaveBeenCalled()
    expect(updateSecret).not.toHaveBeenCalled()
  })

  it('refuses when the host id is unknown, with the i18n key', async () => {
    await expect(createVncCompanion({}, form, hostData, t)).rejects.toThrow('security.secretsManager.vncCompanionNoHostId')
  })
})
