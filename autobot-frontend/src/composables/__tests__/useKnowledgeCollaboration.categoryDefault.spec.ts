// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Coverage for the `mode` default in useKnowledgeCollaboration's
// `scopedSearch` (#14047).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useKnowledgeCollaboration } from '../useKnowledgeCollaboration'
import { CATEGORY_DEFAULTS } from '@/config/ssot-config'

const mockPost = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  ApiClient: class {
    post = mockPost
    get = vi.fn()
    put = vi.fn()
    delete = vi.fn()
  },
}))

vi.mock('@/config/ssot-config', () => ({
  CATEGORY_DEFAULTS: { GENERAL: 'general', SEARCH_MODE_HYBRID: 'hybrid' },
}))

describe('useKnowledgeCollaboration.scopedSearch mode default (#14047)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPost.mockResolvedValue({})
  })

  it('missing options.mode defaults to CATEGORY_DEFAULTS.SEARCH_MODE_HYBRID', async () => {
    const { scopedSearch } = useKnowledgeCollaboration()

    await scopedSearch('query', {})

    expect(mockPost).toHaveBeenCalledWith(
      '/api/knowledge/search/scoped',
      expect.objectContaining({ mode: CATEGORY_DEFAULTS.SEARCH_MODE_HYBRID }),
    )
  })

  it('explicit options.mode overrides the default', async () => {
    const { scopedSearch } = useKnowledgeCollaboration()

    await scopedSearch('query', { mode: 'semantic' })

    expect(mockPost).toHaveBeenCalledWith(
      '/api/knowledge/search/scoped',
      expect.objectContaining({ mode: 'semantic' }),
    )
  })
})
