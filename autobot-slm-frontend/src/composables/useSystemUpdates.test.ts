// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 (batch 4) — proves the system-updates composable routes every
 * method through the canonical `slmApiClient` with endpoints relative to the
 * API base and query params serialised onto the path (no axios `params`), and
 * returns parsed JSON directly (no `.data`). Also asserts the graceful
 * semantics survive: badge/poll probes fail silently (single-shot, no WARN),
 * and the mutating methods keep their `[]`/`false`/`null` returns while
 * populating `error.value` from the thrown message.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

import { useSystemUpdates } from './useSystemUpdates'

describe('useSystemUpdates — migrated onto slmApiClient (#12420 Phase 2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('fetchSummary GETs /updates/summary single-shot and silent', async () => {
    const body = {
      system_update_count: 3,
      security_update_count: 1,
      nodes_with_updates: 2,
      last_checked: null,
    }
    mockGet.mockResolvedValue(body)

    const u = useSystemUpdates()
    const result = await u.fetchSummary()

    expect(mockGet).toHaveBeenCalledWith('/updates/summary', {
      maxRetries: 1,
      suppressErrorLog: true,
    })
    expect(result).toEqual(body)
    expect(u.summary.value).toEqual(body)
    expect(u.updateCount.value).toBe(3)
  })

  it('fetchSummary fails silently, returning null without setting error', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 503'))

    const u = useSystemUpdates()
    const result = await u.fetchSummary()

    expect(result).toBeNull()
    expect(u.error.value).toBeNull()
  })

  it('fetchPackages serialises node_id/severity onto the path', async () => {
    mockGet.mockResolvedValue({ packages: [{ update_id: 'a' }], total: 1, by_node: { n1: 1 } })

    const u = useSystemUpdates()
    const result = await u.fetchPackages('n1', 'critical')

    expect(mockGet).toHaveBeenCalledWith('/updates/packages?node_id=n1&severity=critical')
    expect(result).toEqual([{ update_id: 'a' }])
    expect(u.packagesByNode.value).toEqual({ n1: 1 })
  })

  it('fetchPackages omits the query string when no filters are given', async () => {
    mockGet.mockResolvedValue({ packages: [], total: 0, by_node: {} })

    await useSystemUpdates().fetchPackages()

    expect(mockGet).toHaveBeenCalledWith('/updates/packages')
  })

  it('fetchPackages returns [] and sets error.value on failure', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 500: nope'))

    const u = useSystemUpdates()
    const result = await u.fetchPackages()

    expect(result).toEqual([])
    expect(u.error.value).toBe('HTTP 500: nope')
    expect(u.loading.value).toBe(false)
  })

  it('discoverUpdates POSTs to /updates/discover and returns the job id', async () => {
    mockPost.mockResolvedValue({ success: true, message: 'ok', job_id: 'job-1' })

    const u = useSystemUpdates()
    const jobId = await u.discoverUpdates(['n1'], 'gpu')

    expect(mockPost).toHaveBeenCalledWith('/updates/discover', {
      node_ids: ['n1'],
      role: 'gpu',
    })
    expect(jobId).toBe('job-1')
    expect(u.discoverStatus.value?.status).toBe('pending')
  })

  it('discoverUpdates surfaces a non-success message and returns null', async () => {
    mockPost.mockResolvedValue({ success: false, message: 'busy', job_id: '' })

    const u = useSystemUpdates()
    const jobId = await u.discoverUpdates()

    expect(mockPost).toHaveBeenCalledWith('/updates/discover', {
      node_ids: null,
      role: null,
    })
    expect(jobId).toBeNull()
    expect(u.error.value).toBe('busy')
  })

  it('pollDiscoverStatus GETs the job status single-shot and silent', async () => {
    mockGet.mockResolvedValue({ job_id: 'job-1', status: 'running' })

    const u = useSystemUpdates()
    const result = await u.pollDiscoverStatus('job-1')

    expect(mockGet).toHaveBeenCalledWith('/updates/discover/job-1', {
      maxRetries: 1,
      suppressErrorLog: true,
    })
    expect(result).toMatchObject({ status: 'running' })
  })

  it('pollDiscoverStatus returns null silently on failure', async () => {
    mockGet.mockRejectedValue(new Error('HTTP 404'))

    const result = await useSystemUpdates().pollDiscoverStatus('job-1')

    expect(result).toBeNull()
  })

  it('fetchJobs serialises the limit onto the path', async () => {
    mockGet.mockResolvedValue({ jobs: [{ job_id: 'j' }], total: 1 })

    const u = useSystemUpdates()
    const result = await u.fetchJobs(5)

    expect(mockGet).toHaveBeenCalledWith('/updates/jobs?limit=5')
    expect(result).toEqual([{ job_id: 'j' }])
  })

  it('applyUpdates POSTs the payload and refreshes jobs on success', async () => {
    mockPost.mockResolvedValueOnce({ success: true })
    mockGet.mockResolvedValue({ jobs: [], total: 0 })

    const u = useSystemUpdates()
    const ok = await u.applyUpdates('n1', ['u1', 'u2'])

    expect(mockPost).toHaveBeenCalledWith('/updates/apply', {
      node_id: 'n1',
      update_ids: ['u1', 'u2'],
    })
    expect(mockGet).toHaveBeenCalledWith('/updates/jobs?limit=20')
    expect(ok).toBe(true)
  })

  it('applyUpdates returns false and sets error.value on failure', async () => {
    mockPost.mockRejectedValue(new Error('HTTP 500: fail'))

    const u = useSystemUpdates()
    const ok = await u.applyUpdates('n1', ['u1'])

    expect(ok).toBe(false)
    expect(u.error.value).toBe('HTTP 500: fail')
  })

  it('upgradeAll POSTs to /updates/apply-all', async () => {
    mockPost.mockResolvedValueOnce({ success: true })
    mockGet.mockResolvedValue({ jobs: [], total: 0 })

    const ok = await useSystemUpdates().upgradeAll('n1')

    expect(mockPost).toHaveBeenCalledWith('/updates/apply-all', {
      node_id: 'n1',
      upgrade_all: true,
    })
    expect(ok).toBe(true)
  })

  it('cancelJob POSTs to the cancel endpoint and refreshes jobs', async () => {
    mockPost.mockResolvedValueOnce({ success: true })
    mockGet.mockResolvedValue({ jobs: [], total: 0 })

    const ok = await useSystemUpdates().cancelJob('job-1')

    expect(mockPost).toHaveBeenCalledWith('/updates/jobs/job-1/cancel')
    expect(ok).toBe(true)
  })

  it('cancelJob returns false and sets error.value on failure', async () => {
    mockPost.mockRejectedValue(new Error('HTTP 500: nope'))

    const u = useSystemUpdates()
    const ok = await u.cancelJob('job-1')

    expect(ok).toBe(false)
    expect(u.error.value).toBe('HTTP 500: nope')
  })
})
