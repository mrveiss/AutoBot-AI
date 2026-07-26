// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useVoiceBundle — verifies the composable routes voice-bundle calls through
 * apiClient.rawRequest (base URL resolved by the client, no inline getBackendUrl)
 * while preserving the exact status/error handling and graceful-null semantics
 * (#12363 Phase 2 batch 4).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({
  default: { rawRequest: vi.fn() },
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))
import apiClient from '@/utils/ApiClient'
import { useVoiceBundle, useAdminVoiceBundle } from '../useVoiceBundle'

const rawRequest = apiClient.rawRequest as ReturnType<typeof vi.fn>

function okJson(data: unknown): Response {
  return { ok: true, status: 200, json: async () => data } as unknown as Response
}
function errJson(status: number, data: unknown): Response {
  return { ok: false, status, json: async () => data } as unknown as Response
}

describe('useVoiceBundle', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetchMyBundle resolves the bundle via rawRequest on the relative path', async () => {
    rawRequest.mockResolvedValue(okJson({ bundle_name: 'voice_safe', tool_count: 3, resolution: 'role_default' }))
    const { fetchMyBundle, bundleInfo, error } = useVoiceBundle()
    await fetchMyBundle()
    expect(rawRequest).toHaveBeenCalledWith('/api/voice/realtime/bundle/me')
    expect(bundleInfo.value?.bundle_name).toBe('voice_safe')
    expect(error.value).toBeNull()
  })

  it('fetchMyBundle surfaces the detail error message and nulls the bundle', async () => {
    rawRequest.mockResolvedValue(errJson(403, { detail: 'forbidden' }))
    const { fetchMyBundle, bundleInfo, error } = useVoiceBundle()
    await fetchMyBundle()
    expect(error.value).toBe('forbidden')
    expect(bundleInfo.value).toBeNull()
  })
})

describe('useAdminVoiceBundle', () => {
  beforeEach(() => vi.clearAllMocks())

  it('assignBundle PUTs the bundle body and returns true on success', async () => {
    rawRequest.mockResolvedValue(okJson({}))
    const { assignBundle } = useAdminVoiceBundle()
    const ok = await assignBundle('u1', 'voice_admin')
    expect(ok).toBe(true)
    expect(rawRequest).toHaveBeenCalledWith('/api/admin/voice/bundle/u1', {
      method: 'PUT',
      body: { bundle_name: 'voice_admin' },
    })
  })

  it('assignBundle returns false and records the detail error on failure', async () => {
    rawRequest.mockResolvedValue(errJson(400, { detail: 'bad bundle' }))
    const { assignBundle, saveError } = useAdminVoiceBundle()
    expect(await assignBundle('u1', null)).toBe(false)
    expect(saveError.value).toBe('bad bundle')
  })

  it('getUserBundle returns null on a non-ok response (graceful)', async () => {
    rawRequest.mockResolvedValue(errJson(404, {}))
    const { getUserBundle } = useAdminVoiceBundle()
    expect(await getUserBundle('u2')).toBeNull()
  })

  it('getUserBundle returns null when rawRequest throws (graceful)', async () => {
    rawRequest.mockRejectedValue(new Error('network'))
    const { getUserBundle } = useAdminVoiceBundle()
    expect(await getUserBundle('u2')).toBeNull()
  })
})
