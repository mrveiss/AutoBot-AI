// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #11302 — Application-log viewer.
 *
 * getAppLogs() calls GET /monitoring/app-logs with the query params required
 * by the backend allowlist-mapped endpoint, and returns the parsed
 * AppLogsResponse untouched (ApiClient/axios envelope already unwrapped by
 * `.data` inside the composable — see feedback_apiclient_envelope_pattern).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSlmApi } from './useSlmApi'

const mockGet = vi.fn()

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  return {
    ...actual,
    default: {
      ...actual.default,
      create: () => ({
        get: mockGet,
        post: vi.fn(),
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      }),
    },
  }
})

describe('useSlmApi.getAppLogs (#11302)', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('sends node_id and service as required query params', async () => {
    mockGet.mockResolvedValue({
      data: { entries: [], total: 0, page: 1, per_page: 100, node_id: 'node-1', service: 'backend' },
    })

    const api = useSlmApi()
    await api.getAppLogs({ node_id: 'node-1', service: 'backend' })

    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url] = mockGet.mock.calls[0]
    expect(url).toContain('/monitoring/app-logs?')
    expect(url).toContain('node_id=node-1')
    expect(url).toContain('service=backend')
  })

  it('omits optional filters when not provided', async () => {
    mockGet.mockResolvedValue({
      data: { entries: [], total: 0, page: 1, per_page: 100, node_id: 'node-1', service: 'backend' },
    })

    const api = useSlmApi()
    await api.getAppLogs({ node_id: 'node-1', service: 'backend' })

    const [url] = mockGet.mock.calls[0]
    expect(url).not.toContain('severity=')
    expect(url).not.toContain('q=')
    expect(url).not.toContain('mcp_instance=')
  })

  it('includes severity, hours, q, page, per_page and mcp_instance when provided', async () => {
    mockGet.mockResolvedValue({
      data: { entries: [], total: 0, page: 2, per_page: 50, node_id: 'node-1', service: 'mcp-bridge' },
    })

    const api = useSlmApi()
    await api.getAppLogs({
      node_id: 'node-1',
      service: 'mcp-bridge',
      severity: 'error',
      hours: 24,
      q: 'disk',
      page: 2,
      per_page: 50,
      mcp_instance: 'worker1',
    })

    const [url] = mockGet.mock.calls[0]
    expect(url).toContain('severity=error')
    expect(url).toContain('hours=24')
    expect(url).toContain('q=disk')
    expect(url).toContain('page=2')
    expect(url).toContain('per_page=50')
    expect(url).toContain('mcp_instance=worker1')
  })

  it('returns the parsed AppLogsResponse from the backend', async () => {
    const backendResponse = {
      entries: [
        { line_number: 1, timestamp: '2026-07-23T10:00:00+00:00', severity: 'ERROR', message: 'boom' },
      ],
      total: 1,
      page: 1,
      per_page: 100,
      node_id: 'node-1',
      service: 'backend',
    }
    mockGet.mockResolvedValue({ data: backendResponse })

    const api = useSlmApi()
    const result = await api.getAppLogs({ node_id: 'node-1', service: 'backend' })

    expect(result).toEqual(backendResponse)
  })
})
