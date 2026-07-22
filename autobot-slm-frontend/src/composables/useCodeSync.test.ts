// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #11303 — per-component drift/resolve must be an async job (job_id +
 * status polling) instead of an inline await that blocks the caller for the
 * full 40-120s rsync + post-sync-steps duration. These tests prove the new
 * composable methods return promptly with a job_id and that status polling
 * distinguishes "unknown job" (stop) from "transient error during the
 * component's own service restart" (keep polling).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCodeSync } from './useCodeSync'

const mockPost = vi.fn()
const mockGet = vi.fn()

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ logout: vi.fn() }),
}))

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  return {
    ...actual,
    default: {
      ...actual.default,
      create: () => ({
        post: mockPost,
        get: mockGet,
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      }),
    },
  }
})

describe('useCodeSync — async drift/resolve job (#11303)', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
  })

  it('startResolveDriftAsync resolves immediately with a job_id (no inline rsync/post-steps wait)', async () => {
    mockPost.mockResolvedValue({
      data: { job_id: 'job-1', component: 'autobot-slm-backend', status: 'running' },
    })

    const codeSync = useCodeSync()
    const result = await codeSync.startResolveDriftAsync('autobot-slm-backend')

    expect(mockPost).toHaveBeenCalledWith('/code-sync/drift/resolve-async', {
      component: 'autobot-slm-backend',
    })
    expect(result).toEqual({ job_id: 'job-1', component: 'autobot-slm-backend', status: 'running' })
  })

  it('startResolveDriftAsync surfaces a 409 (restart in flight) without throwing', async () => {
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'restart in flight' } } })

    const codeSync = useCodeSync()
    const result = await codeSync.startResolveDriftAsync('autobot-slm-backend')

    expect(result).toBeNull()
    expect(codeSync.error.value).toBe('restart in flight')
  })

  it('getResolveDriftStatus returns the persisted job row once the job finishes', async () => {
    mockGet.mockResolvedValue({
      data: {
        job_id: 'job-1',
        component: 'autobot-slm-backend',
        status: 'completed',
        success: true,
        deps_changed: false,
        message: 'Resynced autobot-slm-backend from code_source',
        post_steps: ['rsync ok', 'pip install ok'],
        created_at: null,
        completed_at: null,
      },
    })

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('job-1')

    expect(mockGet).toHaveBeenCalledWith('/code-sync/drift/resolve/status/job-1')
    expect(result?.status).toBe('completed')
    expect(result?.success).toBe(true)
  })

  it('getResolveDriftStatus returns null on a true 404 so the poller stops', async () => {
    mockGet.mockRejectedValue({ response: { status: 404 } })

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('unknown-job')

    expect(result).toBeNull()
  })

  it('getResolveDriftStatus returns undefined on a transient error (component self-restart) so the poller keeps retrying', async () => {
    mockGet.mockRejectedValue(new Error('ECONNREFUSED'))

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('job-1')

    expect(result).toBeUndefined()
  })
})
