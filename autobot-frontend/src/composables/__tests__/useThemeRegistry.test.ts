// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/ApiClient', () => ({ default: { get: vi.fn() } }))
import apiClient from '@/utils/ApiClient'
import { fetchInstalledThemes } from '../useThemeRegistry'

describe('fetchInstalledThemes', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns installed themes from the registry', async () => {
    ;(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] },
    ])
    const themes = await fetchInstalledThemes()
    expect(themes.map((t) => t.id)).toEqual(['aqua'])
  })

  it('returns [] when the registry call fails (graceful)', async () => {
    ;(apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network'))
    expect(await fetchInstalledThemes()).toEqual([])
  })
})
