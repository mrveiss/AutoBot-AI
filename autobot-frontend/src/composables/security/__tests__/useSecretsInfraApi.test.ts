// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useSecretsInfraApi — verifies the composable routes infra-host / secrets-usage
 * calls through the canonical apiClient (no inline getBackendUrl prefix) while
 * preserving the graceful-null fallbacks (#12363 Phase 2 batch 4).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), delete: vi.fn() },
}))
import apiClient from '@/utils/ApiClient'
import { useSecretsInfraApi } from '../useSecretsInfraApi'

const get = apiClient.get as ReturnType<typeof vi.fn>
const del = apiClient.delete as ReturnType<typeof vi.fn>

describe('useSecretsInfraApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetchInfraHosts calls the relative infra-hosts path and returns data', async () => {
    get.mockResolvedValue({ hosts: [{ id: 'h1' }] })
    const { fetchInfraHosts } = useSecretsInfraApi()
    const res = await fetchInfraHosts()
    expect(get).toHaveBeenCalledWith('/api/infrastructure/hosts')
    expect(res.hosts).toHaveLength(1)
  })

  it('fetchInfraHosts swallows errors and returns empty hosts', async () => {
    get.mockRejectedValue(new Error('boom'))
    const { fetchInfraHosts } = useSecretsInfraApi()
    expect(await fetchInfraHosts()).toEqual({ hosts: [] })
  })

  it('fetchSecretsUsage calls the relative secrets-usage path', async () => {
    get.mockResolvedValue({ secrets_usage: { a: [] } })
    const { fetchSecretsUsage } = useSecretsInfraApi()
    const res = await fetchSecretsUsage()
    expect(get).toHaveBeenCalledWith('/api/templates/templates/secrets-usage')
    expect(res.secrets_usage).toEqual({ a: [] })
  })

  it('fetchSecretsUsage swallows errors and returns empty map', async () => {
    get.mockRejectedValue(new Error('boom'))
    const { fetchSecretsUsage } = useSecretsInfraApi()
    expect(await fetchSecretsUsage()).toEqual({ secrets_usage: {} })
  })

  it('deleteInfraHost calls delete with the relative host path', async () => {
    del.mockResolvedValue({})
    const { deleteInfraHost } = useSecretsInfraApi()
    await deleteInfraHost('h9')
    expect(del).toHaveBeenCalledWith('/api/infrastructure/hosts/h9')
  })
})
