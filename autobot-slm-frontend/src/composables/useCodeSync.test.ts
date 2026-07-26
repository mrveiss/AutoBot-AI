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

/**
 * Issue #12593 — during Update-All stage 3 (`slm_self_update`) the SLM control
 * plane restarts itself, so the page (which polls that same control plane) sees
 * ~1min of transient poll failures and previously showed only a generic
 * "updating..." spinner → read as frozen. These pure helpers drive the
 * reconnecting affordance and the (unchanged) transient-error give-up.
 */
import {
  isSelfUpdateReconnecting,
  classifyUpdateAllPollError,
  SLM_SELF_UPDATE_STAGE,
  type UpdateAllJob,
  type UpdateAllStage,
} from './useCodeSync'

function makeStage(name: string, status: UpdateAllStage['status']): UpdateAllStage {
  return {
    name,
    status,
    message: null,
    sha: null,
    deps_changed: false,
    log_lines: [],
    started_at: null,
    completed_at: null,
  }
}

function makeJob(runningStage: string): UpdateAllJob {
  return {
    job_id: 'job-ua',
    status: 'running',
    stages: [
      makeStage('github_fetch', 'success'),
      makeStage('code_source_pull', 'success'),
      makeStage(SLM_SELF_UPDATE_STAGE, runningStage === SLM_SELF_UPDATE_STAGE ? 'running' : 'pending'),
      makeStage('fleet_nodes', runningStage === 'fleet_nodes' ? 'running' : 'pending'),
    ],
    total_fleet_nodes: 0,
    completed_fleet_nodes: 0,
    failed_fleet_nodes: 0,
    created_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    failure_reason: null,
  }
}

describe('isSelfUpdateReconnecting (#12593)', () => {
  it('is true when stage 3 is running and at least one poll failed transiently', () => {
    expect(isSelfUpdateReconnecting(makeJob(SLM_SELF_UPDATE_STAGE), 1)).toBe(true)
    expect(isSelfUpdateReconnecting(makeJob(SLM_SELF_UPDATE_STAGE), 5)).toBe(true)
  })

  it('is false with zero transient errors even while stage 3 is running (poll still succeeding)', () => {
    expect(isSelfUpdateReconnecting(makeJob(SLM_SELF_UPDATE_STAGE), 0)).toBe(false)
  })

  it('does NOT fire for a non-stage-3 transient error (e.g. fleet_nodes running)', () => {
    expect(isSelfUpdateReconnecting(makeJob('fleet_nodes'), 3)).toBe(false)
  })

  it('is false when there is no job', () => {
    expect(isSelfUpdateReconnecting(null, 10)).toBe(false)
  })
})

describe('classifyUpdateAllPollError (#12593 keeps the #9971 give-up unchanged)', () => {
  const LOST = 30
  const MAX = 90

  it('continues below the lost-contact threshold', () => {
    expect(classifyUpdateAllPollError(1, LOST, MAX)).toBe('continue')
    expect(classifyUpdateAllPollError(29, LOST, MAX)).toBe('continue')
  })

  it('reports lost-contact at the lost-contact threshold (still polling)', () => {
    expect(classifyUpdateAllPollError(30, LOST, MAX)).toBe('lost-contact')
    expect(classifyUpdateAllPollError(89, LOST, MAX)).toBe('lost-contact')
  })

  it('hard give-up still fires at the 90-error max threshold', () => {
    expect(classifyUpdateAllPollError(90, LOST, MAX)).toBe('giveup')
    expect(classifyUpdateAllPollError(120, LOST, MAX)).toBe('giveup')
  })
})
