// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Coverage for #12386 — the #12376 repoint of ApiService.performResearch.
 *
 * PR #12376 moved this call to POST /api/agent/research/comprehensive and
 * replaced the legacy `{ query, focus, max_results }` body with the backend
 * ResearchTaskRequest field `{ research_query }`. These tests pin the path and
 * body so the request shape can't silently regress.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiService } from '../api'

// Keep the real module (ApiService also imports getConfig etc. from it) and
// only pin getApiBase to '/api' so the asserted path is deterministic.
vi.mock('@/config/ssot-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/ssot-config')>()),
  getApiBase: () => '/api'
}))

describe('ApiService.performResearch (#12386)', () => {
  let postSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    postSpy = vi.spyOn(apiService, 'post').mockResolvedValue({ success: true } as never)
  })

  it('POSTs to /api/agent/research/comprehensive with { research_query }', async () => {
    await apiService.performResearch('hi')

    expect(postSpy).toHaveBeenCalledWith('/api/agent/research/comprehensive', {
      research_query: 'hi'
    })
  })

  it('does not send the legacy query/focus/max_results fields', async () => {
    await apiService.performResearch('hi')

    const body = postSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).toEqual({ research_query: 'hi' })
    expect(body).not.toHaveProperty('query')
    expect(body).not.toHaveProperty('focus')
    expect(body).not.toHaveProperty('max_results')
  })
})
