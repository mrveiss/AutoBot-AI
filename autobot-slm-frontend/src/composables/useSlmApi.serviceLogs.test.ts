// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #16256 — getServiceLogs() must carry the same long remote-exec budget
 * ToolsView's log fetch used to build inline. A journal fetch runs over SSH,
 * like /nodes/{id}/exec, so the client's 30s CRUD-read default would abort a
 * slow one long before it can return.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { jsonResponse } from './slmApiClient.testHelper'
import { REMOTE_EXEC_TIMEOUT_MS } from '@/constants/api-timeouts'

const mockRaw = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
  default: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
}))

import { useSlmApi } from './useSlmApi'

describe('useSlmApi.getServiceLogs (#16256)', () => {
  beforeEach(() => {
    mockRaw.mockReset()
  })

  it('sends the node/service path with the requested line count', async () => {
    mockRaw.mockResolvedValue(
      jsonResponse({ lines_returned: 25, logs: 'a\nb', node_id: 'node-1', service_name: 'redis' })
    )

    const api = useSlmApi()
    await api.getServiceLogs('node-1', 'redis', { lines: 25 })

    expect(mockRaw).toHaveBeenCalledTimes(1)
    const [url, opts] = mockRaw.mock.calls[0] as [string, { method: string; timeout?: number }]
    expect(url).toBe('/nodes/node-1/services/redis/logs?lines=25')
    expect(opts.method).toBe('GET')
  })

  it('gives the fetch the remote-exec budget, not the client default', async () => {
    mockRaw.mockResolvedValue(
      jsonResponse({ lines_returned: 0, logs: '', node_id: 'node-1', service_name: 'redis' })
    )

    const api = useSlmApi()
    await api.getServiceLogs('node-1', 'redis', { lines: 100 })

    const [, opts] = mockRaw.mock.calls[0] as [string, { timeout?: number }]
    expect(opts.timeout).toBe(REMOTE_EXEC_TIMEOUT_MS)
  })
})
