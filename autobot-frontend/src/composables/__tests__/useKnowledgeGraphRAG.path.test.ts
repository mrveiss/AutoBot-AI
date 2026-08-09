// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useKnowledgeGraphRAG.findPath tests — Issue #13474.
 *
 * The connection-path query has three outcomes the UI must render differently:
 * a path, "both exist but are not connected", and "a name did not resolve".
 * Collapsing any two of them would tell the user the wrong thing, so each is
 * asserted separately here.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useKnowledgeGraphRAG } from '../knowledge/useKnowledgeGraphRAG'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    rawRequest: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

import apiClient from '@/utils/ApiClient'

/** Minimal stand-in for the fetch Response the composable reads. */
function mockResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'OK',
    json: async () => body,
  } as unknown as Response
}

const FOUND_BODY = {
  success: true,
  found: true,
  reason: null,
  from_entity: { id: 'e1', name: 'Redis Config', type: 'decision' },
  to_entity: { id: 'e2', name: 'Incident 7', type: 'incident' },
  missing_entities: [],
  hops: 1,
  path: [
    {
      relation: 'CAUSED',
      direction: 'outgoing',
      edge_id: 'edge-1',
      from: 'e1',
      to: 'e2',
      node: { id: 'e2', name: 'Incident 7', type: 'incident' },
    },
  ],
  query: { direction: 'both' },
  traversal_time: 0.004,
  request_id: 'req-1',
}

describe('useKnowledgeGraphRAG.findPath (#13474)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts to /graph-rag/path and exposes the returned path', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(200, FOUND_BODY))
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'Redis Config', to_entity: 'Incident 7' })

    expect(apiClient.rawRequest).toHaveBeenCalledWith(
      '/api/graph-rag/path',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(pathResult.value?.found).toBe(true)
    expect(pathResult.value?.hops).toBe(1)
    expect(pathResult.value?.path[0].relation).toBe('CAUSED')
    expect(pathResult.value?.path[0].direction).toBe('outgoing')
  })

  it('sends the documented defaults when the caller omits them', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(200, FOUND_BODY))
    const { findPath } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'B' })

    const body = vi.mocked(apiClient.rawRequest).mock.calls[0][1]?.body as Record<string, unknown>
    expect(body).toEqual({
      from_entity: 'A',
      to_entity: 'B',
      relation: null,
      max_depth: 6,
      direction: 'both',
    })
  })

  it('forwards every caller-supplied parameter', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(200, FOUND_BODY))
    const { findPath } = useKnowledgeGraphRAG()

    await findPath({
      from_entity: 'A',
      to_entity: 'B',
      relation: 'CAUSED',
      max_depth: 3,
      direction: 'incoming',
    })

    const body = vi.mocked(apiClient.rawRequest).mock.calls[0][1]?.body as Record<string, unknown>
    expect(body.relation).toBe('CAUSED')
    expect(body.max_depth).toBe(3)
    expect(body.direction).toBe('incoming')
  })

  it('keeps "not connected" as a normal result, not an error', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse(200, {
        ...FOUND_BODY,
        found: false,
        reason: 'no_path',
        hops: 0,
        path: [],
      }),
    )
    const { findPath, pathResult, errorMessage } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'B' })

    expect(pathResult.value?.found).toBe(false)
    expect(pathResult.value?.reason).toBe('no_path')
    expect(errorMessage.value).toBe('')
  })

  it('reads missing_entities out of a 404 instead of losing them in an error string', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse(404, {
        detail: { error: 'entity_not_found', missing_entities: ['Does Not Exist'] },
      }),
    )
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'Redis Config', to_entity: 'Does Not Exist' })

    expect(pathResult.value?.reason).toBe('entity_not_found')
    expect(pathResult.value?.missing_entities).toEqual(['Does Not Exist'])
    // Distinct from 'no_path' — a typo must not read as "these are unrelated".
    expect(pathResult.value?.found).toBe(false)
  })

  it('accepts a bare 404 body without the FastAPI detail envelope', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse(404, { error: 'entity_not_found', missing_entities: ['Nope'] }),
    )
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'Nope' })

    expect(pathResult.value?.missing_entities).toEqual(['Nope'])
  })

  it('raises on an unparseable 404 rather than blaming the user\'s input', async () => {
    // #13474 review: mapping every 404 to "entity not found" told the user
    // their data was wrong when the endpoint simply was not deployed.
    vi.mocked(apiClient.rawRequest).mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => {
        throw new Error('not json')
      },
    } as unknown as Response)
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await expect(findPath({ from_entity: 'A', to_entity: 'B' })).rejects.toThrow('HTTP 404')
    expect(pathResult.value).toBeNull()
  })

  it('raises on a bare FastAPI 404 from a backend without this route', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(404, { detail: 'Not Found' }))
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await expect(findPath({ from_entity: 'A', to_entity: 'B' })).rejects.toThrow('HTTP 404')
    expect(pathResult.value).toBeNull()
  })

  it('accepts a 404 that identifies itself without listing names', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse(404, { detail: { error: 'entity_not_found' } }),
    )
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'B' })

    expect(pathResult.value?.reason).toBe('entity_not_found')
    expect(pathResult.value?.missing_entities).toEqual(['A', 'B'])
  })

  it('passes through not_in_graph as its own outcome', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(
      mockResponse(200, { ...FOUND_BODY, found: false, reason: 'not_in_graph', hops: 0, path: [] }),
    )
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'B' })

    // Distinct from no_path: the entities exist but were never mirrored into
    // the traversal graph, so "not connected" would be a wrong answer.
    expect(pathResult.value?.reason).toBe('not_in_graph')
  })

  it('does not report a server failure as "no path"', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(500, {}))
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await expect(findPath({ from_entity: 'A', to_entity: 'B' })).rejects.toThrow('HTTP 500')
    expect(pathResult.value).toBeNull()
  })

  it('clears a previous result before running a new query', async () => {
    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(200, FOUND_BODY))
    const { findPath, pathResult } = useKnowledgeGraphRAG()

    await findPath({ from_entity: 'A', to_entity: 'B' })
    expect(pathResult.value?.found).toBe(true)

    vi.mocked(apiClient.rawRequest).mockResolvedValue(mockResponse(500, {}))
    await expect(findPath({ from_entity: 'A', to_entity: 'B' })).rejects.toThrow()

    // A stale "found" path must not linger next to a failed query.
    expect(pathResult.value).toBeNull()
  })
})
