// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Tests for useToolApproval composable (#4952)
 *
 * Covers:
 *  - APPROVAL_REQUIRED live event sets pendingToolApproval
 *  - Events with wrong event_type are ignored
 *  - submitToolApproval calls POST /api/agent-terminal/tools/approve/{approval_id}
 *  - submitToolApproval clears pendingToolApproval on success
 *  - submitToolApproval throws (and leaves pending) on HTTP error
 *  - clearToolApproval dismisses without calling the endpoint
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Capture the 'global' channel listener injected by useToolApproval so tests
// can fire synthetic live events.
let capturedGlobalListener: ((event: unknown) => void) | null = null

vi.mock('@/services/LiveEventService', () => ({
  default: {
    subscribe: vi.fn((channel: string, cb: (e: unknown) => void) => {
      if (channel === 'global') capturedGlobalListener = cb
      return () => { capturedGlobalListener = null }
    }),
  },
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getApiUrl: vi.fn(async (path: string) => `http://backend${path}`),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: vi.fn(() => '/api'),
}))

let mockFetchResponse: { ok: boolean; status: number; text: () => Promise<string> } = {
  ok: true,
  status: 200,
  text: async () => '',
}

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(async () => mockFetchResponse),
}))

// ---------------------------------------------------------------------------
// Import the composable AFTER mocks are in place
// ---------------------------------------------------------------------------
import { useToolApproval } from '../useToolApproval'
import { fetchWithAuth } from '@/utils/fetchWithAuth'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeLiveEvent(event_type: string, payload: Record<string, unknown>) {
  return { type: 'live_event', channel: 'global', event_type, event_id: 1, payload }
}

const validPayload = {
  approval_id: 'test-uuid-1234',
  tool_name: 'bash',
  arguments: { command: 'rm -rf /' },
  reason: 'Agent wants to run a destructive command',
  risk_level: 'critical',
  timeout_seconds: 300,
  task_id: 'task-abc',
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useToolApproval', () => {
  beforeEach(() => {
    capturedGlobalListener = null
    mockFetchResponse = { ok: true, status: 200, text: async () => '' }
    vi.clearAllMocks()
  })

  it('starts with no pending approval', () => {
    const { pendingToolApproval } = useToolApproval()
    expect(pendingToolApproval.value).toBeNull()
  })

  it('sets pendingToolApproval when APPROVAL_REQUIRED event arrives', () => {
    const { pendingToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', validPayload))
    expect(pendingToolApproval.value).not.toBeNull()
    expect(pendingToolApproval.value!.approval_id).toBe('test-uuid-1234')
    expect(pendingToolApproval.value!.tool_name).toBe('bash')
    expect(pendingToolApproval.value!.risk_level).toBe('critical')
    expect(pendingToolApproval.value!.task_id).toBe('task-abc')
  })

  it('ignores events with a different event_type', () => {
    const { pendingToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('SOME_OTHER_EVENT', validPayload))
    expect(pendingToolApproval.value).toBeNull()
  })

  it('ignores events without approval_id', () => {
    const { pendingToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', { ...validPayload, approval_id: '' }))
    expect(pendingToolApproval.value).toBeNull()
  })

  it('submitToolApproval POSTs to /api/agent-terminal/tools/approve/{approval_id}', async () => {
    const { pendingToolApproval, submitToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', validPayload))

    await submitToolApproval(true, 'looks safe')

    expect(fetchWithAuth).toHaveBeenCalledWith(
      'http://backend/api/agent-terminal/tools/approve/test-uuid-1234',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ approved: true, comment: 'looks safe', task_id: 'task-abc' }),
      })
    )
    // Cleared after success
    expect(pendingToolApproval.value).toBeNull()
  })

  it('submitToolApproval sends approved=false for deny', async () => {
    const { submitToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', validPayload))

    await submitToolApproval(false)

    expect(fetchWithAuth).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: JSON.stringify({ approved: false, comment: null, task_id: 'task-abc' }),
      })
    )
  })

  it('throws and keeps pendingToolApproval when HTTP POST fails', async () => {
    mockFetchResponse = { ok: false, status: 500, text: async () => 'internal error' }
    const { pendingToolApproval, submitToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', validPayload))

    await expect(submitToolApproval(true)).rejects.toThrow('500')
    // Still pending — user should be able to retry
    expect(pendingToolApproval.value).not.toBeNull()
  })

  it('clearToolApproval dismisses without calling the endpoint', () => {
    const { pendingToolApproval, clearToolApproval } = useToolApproval()
    capturedGlobalListener!(makeLiveEvent('APPROVAL_REQUIRED', validPayload))
    expect(pendingToolApproval.value).not.toBeNull()

    clearToolApproval()

    expect(pendingToolApproval.value).toBeNull()
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })
})
