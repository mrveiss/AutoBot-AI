// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #21584 — getNodes() is the one node-list fetch (fleet store, agents view, roles view, code-source
 * dialog): a fleet larger than the backend's page size comes back whole, in requests no larger than the
 * ceiling, and a page that cannot be read is reported with what was read.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { errorResponse, jsonResponse } from './slmApiClient.testHelper'
import { PartialListError } from '@/utils/fetchAllPages'

const mockRaw = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
  default: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
}))

import { useSlmApi } from './useSlmApi'

const TOTAL = 230
const row = (i: number) => ({
  id: i, node_id: `node-${i}`, hostname: `host-${i}`, ip_address: `10.0.0.${i % 250}`, status: 'online',
  roles: [], cpu_percent: 0, memory_percent: 0, disk_percent: 0, last_heartbeat: null,
  agent_version: null, os_info: null, created_at: '', updated_at: '',
})

/** Answers `/nodes?page=P&per_page=N` from a table of TOTAL rows; `failPage` answers 504. */
function serve(failPage?: number) {
  mockRaw.mockImplementation(async (url: string) => {
    const q = new URL(url, 'http://x').searchParams
    const page = Number(q.get('page'))
    const perPage = Number(q.get('per_page'))
    if (page === failPage) return errorResponse(504, { detail: 'timeout' })
    const start = (page - 1) * perPage
    const nodes = Array.from({ length: Math.max(0, Math.min(perPage, TOTAL - start)) }, (_, i) => row(start + i + 1))
    return jsonResponse({ nodes, total: TOTAL, page, per_page: perPage })
  })
}

describe('useSlmApi.getNodes (#21584)', () => {
  beforeEach(() => {
    mockRaw.mockReset()
  })

  it('returns every node of a fleet larger than one page, each request within the ceiling', async () => {
    serve()
    const nodes = await useSlmApi().getNodes()

    expect(nodes).toHaveLength(TOTAL)
    expect(nodes[0].node_id).toBe('node-1')
    expect(nodes[TOTAL - 1].node_id).toBe(`node-${TOTAL}`)
    const sizes = mockRaw.mock.calls.map(([url]) => Number(new URL(url as string, 'http://x').searchParams.get('per_page')))
    expect(mockRaw).toHaveBeenCalledTimes(3)
    expect(sizes.every((n) => n <= 100)).toBe(true)
  })

  it('a page that fails reports the mapped nodes read so far and the fleet total', async () => {
    serve(2)
    const err = await useSlmApi().getNodes().catch((e: unknown) => e)

    expect(err).toBeInstanceOf(PartialListError)
    const partial = err as PartialListError<{ node_id: string }>
    expect(partial.items).toHaveLength(100)
    expect(partial.items[0].node_id).toBe('node-1')
    expect(partial.total).toBe(TOTAL)
  })
})
