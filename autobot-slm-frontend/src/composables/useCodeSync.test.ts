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
 *
 * #12420 Phase 2 (batch 6) — useCodeSync migrated off its per-composable axios
 * instance onto the canonical `slmApiClient`. The 404-vs-transient poll
 * contract that backs #12593 (see the getUpdateAllStatus block below) is
 * asserted end-to-end through the new `rawRequest` path.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()
const mockRawRequest = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    rawRequest: (...args: unknown[]) => mockRawRequest(...args),
  },
}))

// useRoles owns its own axios client (out of scope for this batch); stub it so
// syncNode's SLM-server role lookup (#9956) is deterministic and offline.
const mockGetNodeRoles = vi.fn()
vi.mock('./useRoles', () => ({
  useRoles: () => ({
    roles: [],
    fetchRoles: vi.fn(),
    syncRole: vi.fn(),
    pullFromSource: vi.fn(),
    getNodeRoles: (...args: unknown[]) => mockGetNodeRoles(...args),
  }),
}))

import { useCodeSync } from './useCodeSync'
import { mockResponse } from './slmApiClient.testHelper'

describe('useCodeSync — async drift/resolve job (#11303)', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
    mockRawRequest.mockReset()
  })

  it('startResolveDriftAsync resolves immediately with a job_id (no inline rsync/post-steps wait)', async () => {
    mockRawRequest.mockResolvedValue(
      mockResponse(200, { job_id: 'job-1', component: 'autobot-slm-backend', status: 'running' }),
    )

    const codeSync = useCodeSync()
    const result = await codeSync.startResolveDriftAsync('autobot-slm-backend')

    expect(mockRawRequest).toHaveBeenCalledWith('/code-sync/drift/resolve-async', {
      method: 'POST',
      body: { component: 'autobot-slm-backend' },
    })
    expect(result).toEqual({ job_id: 'job-1', component: 'autobot-slm-backend', status: 'running' })
  })

  it('startResolveDriftAsync surfaces a 409 (restart in flight) detail verbatim without throwing', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(409, { detail: 'restart in flight' }))

    const codeSync = useCodeSync()
    const result = await codeSync.startResolveDriftAsync('autobot-slm-backend')

    expect(result).toBeNull()
    expect(codeSync.error.value).toBe('restart in flight')
  })

  it('getResolveDriftStatus returns the persisted job row once the job finishes', async () => {
    mockRawRequest.mockResolvedValue(
      mockResponse(200, {
        job_id: 'job-1',
        component: 'autobot-slm-backend',
        status: 'completed',
        success: true,
        deps_changed: false,
        message: 'Resynced autobot-slm-backend from code_source',
        post_steps: ['rsync ok', 'pip install ok'],
        created_at: null,
        completed_at: null,
      }),
    )

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('job-1')

    expect(mockRawRequest).toHaveBeenCalledWith('/code-sync/drift/resolve/status/job-1', {
      method: 'GET',
    })
    expect(result?.status).toBe('completed')
    expect(result?.success).toBe(true)
  })

  it('getResolveDriftStatus returns null on a true 404 so the poller stops', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(404, { detail: 'unknown job' }))

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('unknown-job')

    expect(result).toBeNull()
  })

  it('getResolveDriftStatus returns undefined on a 5xx (component self-restart) so the poller keeps retrying', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(503, { detail: 'service unavailable' }))

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('job-1')

    expect(result).toBeUndefined()
  })

  it('getResolveDriftStatus returns undefined on a connection-refused error so the poller keeps retrying', async () => {
    mockRawRequest.mockRejectedValue(new Error('ECONNREFUSED'))

    const codeSync = useCodeSync()
    const result = await codeSync.getResolveDriftStatus('job-1')

    expect(result).toBeUndefined()
  })
})

/**
 * Issue #12593 (backed by the #12420 batch-6 migration) — during Update-All
 * stage 3 (`slm_self_update`) the SLM control plane restarts itself. The
 * code-sync page polls that SAME control plane via getUpdateAllStatus(), so it
 * sees ~1min of transient poll failures (connection refused / 5xx). The poll
 * loop MUST keep polling through that window (return `undefined`) and only stop
 * on a true 404 (no job ever started → return `null`). This contract is what
 * lets the reconnecting affordance render instead of a hard "job failed".
 *
 * These tests prove the contract survives the slmApiClient migration by driving
 * getUpdateAllStatus()/startUpdateAll() through the mocked `rawRequest` path.
 */
describe('getUpdateAllStatus poll contract through slmApiClient (#12593 / #12420 batch 6)', () => {
  beforeEach(() => {
    mockRawRequest.mockReset()
  })

  const job = {
    job_id: 'job-ua',
    status: 'running',
    stages: [],
    total_fleet_nodes: 0,
    completed_fleet_nodes: 0,
    failed_fleet_nodes: 0,
    skipped_fleet_nodes: 0,
    created_at: '2026-01-01T00:00:00Z',
    completed_at: null,
    failure_reason: null,
  }

  it('returns the job on 200 and targets the status endpoint via rawRequest (single-shot GET)', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(200, job))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    expect(mockRawRequest).toHaveBeenCalledWith('/code-sync/update-all/status', {
      method: 'GET',
    })
    expect(result).toEqual(job)
  })

  it('returns null ONLY on a true 404 (no job started) so the caller stops polling', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(404, { detail: 'no job' }))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    expect(result).toBeNull()
  })

  it('returns undefined on a 502 during the SLM self-restart so the caller KEEPS polling', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(502, { detail: 'bad gateway' }))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    // Not null — a self-restart bounce must never be read as "stop polling".
    expect(result).toBeUndefined()
  })

  it('returns undefined on a 503 (control plane bouncing) so the caller KEEPS polling', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(503, { detail: 'unavailable' }))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    expect(result).toBeUndefined()
  })

  it('returns undefined on connection-refused / network error so the caller KEEPS polling', async () => {
    mockRawRequest.mockRejectedValue(new Error('Failed to fetch'))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    expect(result).toBeUndefined()
  })

  it('returns undefined on a request timeout so the caller KEEPS polling', async () => {
    mockRawRequest.mockRejectedValue(new Error('Request timeout after 30000ms'))

    const codeSync = useCodeSync()
    const result = await codeSync.getUpdateAllStatus()

    expect(result).toBeUndefined()
  })

  it('startUpdateAll returns the initial job on 200', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(200, job))

    const codeSync = useCodeSync()
    const result = await codeSync.startUpdateAll()

    expect(mockRawRequest).toHaveBeenCalledWith('/code-sync/update-all', {
      method: 'POST',
    })
    expect(result).toEqual(job)
  })

  it('startUpdateAll returns null and surfaces the 409 detail (already running)', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(409, { detail: 'Update already in progress' }))

    const codeSync = useCodeSync()
    const result = await codeSync.startUpdateAll()

    expect(result).toBeNull()
    expect(codeSync.error.value).toBe('Update already in progress')
  })

  it('startUpdateAll returns null on a network error without throwing', async () => {
    mockRawRequest.mockRejectedValue(new Error('ECONNREFUSED'))

    const codeSync = useCodeSync()
    const result = await codeSync.startUpdateAll()

    expect(result).toBeNull()
    expect(codeSync.error.value).toBe('Failed to start update')
  })
})

/**
 * Issue #12420 Phase 2 (batch 6) — spot-check that the convenience-method
 * migration preserves the graceful-return contracts: mutating/fetch helpers
 * keep their `[]`/`null`/`false` returns and populate `error.value` from the
 * thrown message, and syncNode still treats the SLM self-restart 502 as success.
 */
describe('useCodeSync — slmApiClient convenience migration (#12420 batch 6)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockRawRequest.mockReset()
    mockGetNodeRoles.mockReset()
  })

  it('fetchStatus GETs /code-sync/status and stores the parsed body', async () => {
    const body = {
      latest_version: 'abc',
      local_version: 'abc',
      last_fetch: null,
      has_update: false,
      outdated_nodes: 0,
      total_nodes: 3,
    }
    mockGet.mockResolvedValue(body)

    const codeSync = useCodeSync()
    const result = await codeSync.fetchStatus()

    expect(mockGet).toHaveBeenCalledWith('/code-sync/status')
    expect(result).toEqual(body)
    expect(codeSync.status.value).toEqual(body)
  })

  it('fetchStatus returns null and sets error.value from the thrown message', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 500: boom'))

    const codeSync = useCodeSync()
    const result = await codeSync.fetchStatus()

    expect(result).toBeNull()
    expect(codeSync.error.value).toBe('HTTP 500: boom')
  })

  it('fetchPendingNodes returns [] on failure (graceful)', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 500'))

    const codeSync = useCodeSync()
    const result = await codeSync.fetchPendingNodes()

    expect(result).toEqual([])
  })

  it('getRecentJobs GETs a single-shot poll with the limit on the path and returns [] on failure', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 503'))

    const codeSync = useCodeSync()
    const result = await codeSync.getRecentJobs(5)

    expect(mockGet).toHaveBeenCalledWith('/code-sync/fleet/jobs?limit=5', {
      maxRetries: 1,
    })
    expect(result).toEqual([])
  })

  it('syncNode treats the SLM self-restart 502 as success when the node is an SLM server', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(502, { detail: 'bad gateway' }))
    mockGetNodeRoles.mockResolvedValue({ detected_roles: ['slm-backend'] })

    const codeSync = useCodeSync()
    const result = await codeSync.syncNode('node-1', { restart: true })

    expect(result.success).toBe(true)
    expect(result.node_id).toBe('node-1')
    expect(result.message).toContain('SLM Manager restart')
  })

  it('syncNode surfaces a 502 as failure when the node is NOT an SLM server', async () => {
    mockRawRequest.mockResolvedValue(mockResponse(502, { detail: 'bad gateway' }))
    mockGetNodeRoles.mockResolvedValue({ detected_roles: ['worker'] })

    const codeSync = useCodeSync()
    const result = await codeSync.syncNode('node-1', { restart: true })

    expect(result.success).toBe(false)
    expect(codeSync.error.value).toBe('bad gateway')
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
    skipped_fleet_nodes: 0,
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
