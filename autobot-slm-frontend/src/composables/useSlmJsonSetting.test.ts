// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSlmJsonSetting } from './useSlmJsonSetting'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    getApiUrl: () => '',
    getAuthHeaders: () => ({}),
  }),
}))

interface Payload {
  enabled: boolean
}

describe('useSlmJsonSetting', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('load() returns the parsed JSON value on a 200 response', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ value: JSON.stringify({ enabled: true }) }),
    })) as unknown as typeof fetch

    const { load } = useSlmJsonSetting<Payload>('some.key')
    await expect(load()).resolves.toEqual({ enabled: true })
  })

  it('load() returns null on a non-ok response', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 404 })) as unknown as typeof fetch

    const { load } = useSlmJsonSetting<Payload>('some.key')
    await expect(load()).resolves.toBeNull()
  })

  it('save() PUTs first and falls back to POST on 404', async () => {
    const calls: Array<{ url: string; method?: string }> = []
    global.fetch = vi.fn(async (url, opts) => {
      calls.push({ url: String(url), method: opts?.method })
      if (opts?.method === 'PUT') {
        return { ok: false, status: 404 } as Response
      }
      return { ok: true, status: 201 } as Response
    }) as unknown as typeof fetch

    const { save, saving, saved } = useSlmJsonSetting<Payload>('some.key')
    const ok = await save({ enabled: true }, 'a description')

    expect(ok).toBe(true)
    expect(saved.value).toBe(true)
    expect(saving.value).toBe(false)
    expect(calls.map((c) => c.method)).toEqual(['PUT', 'POST'])
    expect(calls[0].url).toContain('/api/settings/some.key')
  })

  it('save() does not fall back to POST when PUT succeeds', async () => {
    const calls: Array<string | undefined> = []
    global.fetch = vi.fn(async (_url, opts) => {
      calls.push(opts?.method)
      return { ok: true, status: 200 } as Response
    }) as unknown as typeof fetch

    const { save, saved } = useSlmJsonSetting<Payload>('some.key')
    const ok = await save({ enabled: false }, 'desc')

    expect(ok).toBe(true)
    expect(saved.value).toBe(true)
    expect(calls).toEqual(['PUT'])
  })
})
