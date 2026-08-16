// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Coverage for the `category` default in useDocumentationSearch's
// `searchDocs` / `browseMore` mappers (#14047).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useDocumentationSearch } from '../useDocumentationSearch'
import { CATEGORY_DEFAULTS } from '@/config/ssot-config'

const mockPost = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ post: mockPost, get: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
  CATEGORY_DEFAULTS: { GENERAL: 'general', SEARCH_MODE_HYBRID: 'hybrid' },
}))

vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: () => ({ load: vi.fn(), data: { value: null }, error: { value: null } }),
}))

describe('useDocumentationSearch category default (#14047)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('searchDocs: missing metadata.category defaults to CATEGORY_DEFAULTS.GENERAL', async () => {
    mockPost.mockResolvedValueOnce({ results: [{ content: 'hi', metadata: {} }] })
    const { searchDocs } = useDocumentationSearch()

    const results = await searchDocs('query', [])

    expect(results[0].category).toBe(CATEGORY_DEFAULTS.GENERAL)
  })

  it('searchDocs: explicit metadata.category overrides the default', async () => {
    mockPost.mockResolvedValueOnce({
      results: [{ content: 'hi', metadata: { category: 'security' } }],
    })
    const { searchDocs } = useDocumentationSearch()

    const results = await searchDocs('query', [])

    expect(results[0].category).toBe('security')
  })

  it('browseMore: missing category defaults to CATEGORY_DEFAULTS.GENERAL', async () => {
    mockPost.mockResolvedValueOnce({ documents: [{ content_hash: 'h1' }] })
    const { browseMore } = useDocumentationSearch()

    const results = await browseMore('query', null, 1)

    expect(results[0].category).toBe(CATEGORY_DEFAULTS.GENERAL)
  })

  it('browseMore: explicit category overrides the default', async () => {
    mockPost.mockResolvedValueOnce({
      documents: [{ content_hash: 'h1', category: 'security' }],
    })
    const { browseMore } = useDocumentationSearch()

    const results = await browseMore('query', null, 1)

    expect(results[0].category).toBe('security')
  })
})
