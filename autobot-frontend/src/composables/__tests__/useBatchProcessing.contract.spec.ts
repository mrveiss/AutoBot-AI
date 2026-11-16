// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #21649: useBatchProcessing reads the shapes the batch-jobs backend sends and lets
 * failures through.
 *
 * - GET /api/batch-jobs returns `{ jobs, total_count, status_counts }`; the per-status
 *   counts come from `status_counts`.
 * - logs, templates and schedules are bare arrays.
 * - a failed list load is an error, never an empty list: `jobsView` keeps loading,
 *   error and empty apart.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockCall, mockPost, poller } = vi.hoisted(() => ({
  mockCall: vi.fn(),
  mockPost: vi.fn(),
  poller: { tick: null as null | (() => Promise<void>) },
}))

vi.mock('@/utils/ApiClient', () => ({ default: { call: mockCall, post: mockPost } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/composables/useProbeBackedHealth', () => ({
  useProbeBackedHealth: () => vi.fn(),
  probeStatusToLegacy: vi.fn(),
}))
vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: (tick: () => Promise<void>) => {
    poller.tick = tick
    return { start: vi.fn(), stop: vi.fn() }
  },
}))

import { useBatchProcessingApi, useBatchProcessingState } from '../useBatchProcessing'

const job = (job_id: string, status = 'pending') => ({
  job_id,
  name: job_id,
  job_type: 'custom',
  status,
  progress: 0,
  parameters: {},
  created_at: '2026-11-15T00:00:00Z',
})

const LIST = {
  jobs: [job('a', 'running'), job('b', 'failed')],
  total_count: 2,
  status_counts: { running: 1, failed: 1, completed: 4 },
}

/** Reply to typed calls by route; anything unexpected fails the test loudly. */
function replies(map: Record<string, unknown>) {
  mockCall.mockImplementation(async (_method: string, path: string) => {
    const reply = map[path]
    if (reply instanceof Error) throw reply
    if (reply === undefined) throw new Error(`unexpected call ${path}`)
    return reply
  })
}

describe('useBatchProcessingApi (#21649)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists jobs with the filter as query and returns the reply unchanged', async () => {
    replies({ '/api/batch-jobs': LIST })
    const result = await useBatchProcessingApi().listJobs({ status: 'failed', limit: 10 })
    expect(result).toBe(LIST)
    expect(mockCall).toHaveBeenCalledWith('get', '/api/batch-jobs', {
      query: { status: 'failed', job_type: undefined, limit: 10 },
    })
  })

  it('rejects when the list fails, instead of resolving an empty list', async () => {
    const failure = new Error('HTTP 503')
    replies({ '/api/batch-jobs': failure })
    await expect(useBatchProcessingApi().listJobs()).rejects.toBe(failure)
  })

  it('reads logs, templates and schedules as the bare arrays the backend sends', async () => {
    const logs = [{ timestamp: 't', level: 'info', message: 'm' }]
    const templates = [{ template_id: 't1', name: 'T', job_type: 'custom', parameters: {}, created_at: 'c' }]
    const schedules = [{ schedule_id: 's1', job_id: 'a', cron_expression: '* * * * *', enabled: true, next_run: 'n' }]
    replies({
      '/api/batch-jobs/{job_id}/logs': logs,
      '/api/batch-jobs/templates/': templates,
      '/api/batch-jobs/schedules/': schedules,
    })
    const api = useBatchProcessingApi()
    expect(await api.getJobLogs('a')).toBe(logs)
    expect(await api.listTemplates()).toBe(templates)
    expect(await api.listSchedules()).toBe(schedules)
    expect(mockCall).toHaveBeenCalledWith('get', '/api/batch-jobs/{job_id}/logs', { path: { job_id: 'a' } })
  })

  it('sends template name and type as query and the parameters as the body', async () => {
    replies({ '/api/batch-jobs/templates/': {} })
    await useBatchProcessingApi().createTemplate({ name: 'T', job_type: 'backup', parameters: { x: 1 } })
    expect(mockCall).toHaveBeenCalledWith('post', '/api/batch-jobs/templates/', {
      query: { name: 'T', job_type: 'backup' },
      body: { x: 1 },
    })
  })

  it('sends every schedule field as query', async () => {
    replies({ '/api/batch-jobs/schedules/': {} })
    await useBatchProcessingApi().createSchedule({ job_id: 'a', cron_expression: '0 * * * *', enabled: false })
    expect(mockCall).toHaveBeenCalledWith('post', '/api/batch-jobs/schedules/', {
      query: { job_id: 'a', cron_expression: '0 * * * *', enabled: false },
    })
  })
})

describe('useBatchProcessingState (#21649)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('starts in loading, then shows the jobs with counts from status_counts', async () => {
    replies({ '/api/batch-jobs': LIST })
    const state = useBatchProcessingState()
    expect(state.jobsView.value).toBe('loading')
    await state.loadJobs()
    expect(state.jobsView.value).toBe('ready')
    expect(state.jobs.value.map((j) => j.job_id)).toEqual(['a', 'b'])
    expect(state.totalCount.value).toBe(2)
    expect(state.runningCount.value).toBe(1)
    expect(state.failedCount.value).toBe(1)
    expect(state.completedCount.value).toBe(4)
    expect(state.pendingCount.value).toBe(0)
    expect(state.error.value).toBeNull()
  })

  it('shows empty only after a successful load that returned no jobs', async () => {
    replies({ '/api/batch-jobs': { jobs: [], total_count: 0, status_counts: {} } })
    const state = useBatchProcessingState()
    await state.loadJobs()
    expect(state.jobsView.value).toBe('empty')
  })

  it('records a failed load as an error, not as an empty list', async () => {
    const failure = new Error('HTTP 503')
    replies({ '/api/batch-jobs': failure })
    const state = useBatchProcessingState()
    await state.loadJobs()
    expect(state.jobsView.value).toBe('error')
    expect(state.error.value).toBe(failure)
    expect(state.loading.value).toBe(false)
  })

  it('clears the error when a later load succeeds', async () => {
    replies({ '/api/batch-jobs': new Error('HTTP 503') })
    const state = useBatchProcessingState()
    await state.loadJobs()
    replies({ '/api/batch-jobs': LIST })
    await state.loadJobs()
    expect(state.jobsView.value).toBe('ready')
    expect(state.error.value).toBeNull()
  })

  it('keeps template and schedule failures in their own error refs', async () => {
    const failure = new Error('HTTP 500')
    replies({ '/api/batch-jobs/templates/': failure, '/api/batch-jobs/schedules/': [] })
    const state = useBatchProcessingState()
    await state.loadTemplates()
    await state.loadSchedules()
    expect(state.templatesError.value).toBe(failure)
    expect(state.templates.value).toEqual([])
    expect(state.schedulesError.value).toBeNull()
    expect(state.error.value).toBeNull()
  })

  it('rejects a failed mutation to its caller and does not reload', async () => {
    const failure = new Error('HTTP 404')
    replies({ '/api/batch-jobs/{job_id}': failure })
    const state = useBatchProcessingState()
    await expect(state.deleteJob('gone')).rejects.toBe(failure)
    expect(mockCall).not.toHaveBeenCalledWith('get', '/api/batch-jobs', expect.anything())
  })

  it('keeps a logs failure out of the list error', async () => {
    const failure = new Error('HTTP 404')
    replies({ '/api/batch-jobs/{job_id}/logs': failure })
    const state = useBatchProcessingState()
    expect(await state.loadJobLogs('a')).toBeNull()
    expect(state.logsError.value).toBe(failure)
    expect(state.error.value).toBeNull()
  })

  it('keeps polling after a retry until the queued job\'s record moves, then stops (#20644 review)', async () => {
    const failed = { ...job('f', 'failed'), started_at: 't1' }
    const listOf = (j: unknown) => ({ jobs: [j], total_count: 1, status_counts: {} })
    replies({ '/api/batch-jobs': listOf(failed), '/api/batch-jobs/{job_id}/run': failed })
    const state = useBatchProcessingState()
    await state.loadJobs()
    state.startPolling(1000)
    await state.runJob('f')
    expect(state.awaitingRun.value).toBe(true)
    mockCall.mockClear()
    await poller.tick!()
    expect(mockCall).toHaveBeenCalledWith('get', '/api/batch-jobs', expect.anything())
    expect(state.awaitingRun.value).toBe(true)
    replies({ '/api/batch-jobs': listOf({ ...failed, status: 'running', started_at: 't2' }) })
    await poller.tick!()
    expect(state.awaitingRun.value).toBe(false)
  })

  it('a run request that fails stops waiting for that job', async () => {
    replies({
      '/api/batch-jobs': { jobs: [job('f', 'failed')], total_count: 1, status_counts: {} },
      '/api/batch-jobs/{job_id}/run': new Error('HTTP 409'),
    })
    const state = useBatchProcessingState()
    await state.loadJobs()
    await expect(state.runJob('f')).rejects.toThrow('HTTP 409')
    expect(state.awaitingRun.value).toBe(false)
  })
})
