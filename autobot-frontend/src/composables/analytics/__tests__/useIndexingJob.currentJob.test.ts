// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * /index/current is asked for the selected source (#20513), and how the newest run ended is read
 * when the page opens and when a job ends (#21003).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { IDLE_POLLS_BEFORE_GIVING_UP, useIndexingJob, type UseIndexingJobDeps } from '../useIndexingJob'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn(async () => 'http://backend') },
}))

const IDLE = { has_active_job: false, task_id: null, status: 'idle' }
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const scoped = (url: string) => `${url}?source_id=autobot`

function build(withSourceId: (url: string) => string, loadRunState = vi.fn(async () => {}), sourceKey: () => string = () => 'source_id=autobot') {
  const deps = {
    rootPath: ref('/repo'),
    analyzing: ref(false),
    progressPercent: ref(0),
    progressStatus: ref(''),
    selectedSource: ref({ id: 'autobot' }),
    withSourceId,
    sourceKey,
    notify: vi.fn(),
    t: (key: string) => key,
    problemsReport: ref([]),
    codebaseStats: ref(null),
    declarationAnalysis: ref([]),
    duplicateAnalysis: ref([]),
    hardcodeAnalysis: ref([]),
    chartData: ref(null),
    runState: { loadRunState },
    showKnowledgeBaseOptIn: ref(false),
    onIndexComplete: vi.fn(async () => {}),
    storageKeyPath: 'k',
  } as unknown as UseIndexingJobDeps
  return { job: useIndexingJob(deps), loadRunState, deps }
}

describe('useIndexingJob current-job read (#20513, #21003)', () => {
  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue(respond(IDLE))
  })

  it('asks /index/current for the selected source', async () => {
    const { job } = build(scoped)
    await job.checkCurrentIndexingJob()
    const urls = fetchWithAuth.mock.calls.map((call) => call[0] as string)
    expect(urls).toContain('http://backend/api/analytics/codebase/index/current?source_id=autobot')
  })

  it('with no source selected /index/current is not requested (it would answer 422)', async () => {
    const { job } = build((url) => url)
    await job.checkCurrentIndexingJob()
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })

  it('opening the page reads how the newest run ended', async () => {
    const { job, loadRunState } = build(scoped)
    await job.checkCurrentIndexingJob()
    expect(loadRunState).toHaveBeenCalledTimes(1)
  })

  it('a job that ended failed re-reads how the run ended', async () => {
    fetchWithAuth.mockResolvedValue(respond({ has_active_job: false, task_id: 't1', source_id: 'autobot', status: 'failed', error: 'x' }))
    const { job, loadRunState } = build(scoped)
    await job.pollJobStatus()
    expect(loadRunState).toHaveBeenCalledTimes(1)
  })
})

describe('a request queued behind another source\'s job (#20513)', () => {
  const QUEUED = { has_active_job: true, task_id: null, source_id: 'autobot', status: 'queued', position: 2 }
  const RUNNING = { has_active_job: true, task_id: 't9', source_id: 'autobot', status: 'running', progress: {} }
  const currentCalls = () => fetchWithAuth.mock.calls.map((c) => c[0] as string).filter((u) => u.includes('/index/current'))

  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue(respond(IDLE))
  })

  it('polling keeps waiting and shows the queued text with the position', async () => {
    fetchWithAuth.mockResolvedValue(respond(QUEUED))
    const { job, deps } = build(scoped)
    await job.pollJobStatus()
    expect(deps.analyzing.value).toBe(true)
    expect(deps.progressStatus.value).toBe('analytics.codebase.status.queued')
    expect(job.currentJobId.value).toBeNull()
    expect(fetchWithAuth.mock.calls.every((c) => (c[0] as string).includes('/index/current'))).toBe(true) // no problems/stats polls
    expect(deps.notify).not.toHaveBeenCalled()
  })

  it('queued then running sets the job id', async () => {
    fetchWithAuth.mockResolvedValueOnce(respond(QUEUED)).mockResolvedValue(respond(RUNNING))
    const { job } = build(scoped)
    await job.pollJobStatus()
    expect(job.currentJobId.value).toBeNull()
    await job.pollJobStatus()
    expect(job.currentJobId.value).toBe('t9')
  })

  it('queued then idle: the job that started and ended is terminal', async () => {
    fetchWithAuth.mockResolvedValueOnce(respond(QUEUED)).mockResolvedValue(respond(IDLE))
    const { job, deps, loadRunState } = build(scoped)
    await job.pollJobStatus()
    await job.pollJobStatus()
    expect(deps.analyzing.value).toBe(false)
    expect(loadRunState).toHaveBeenCalledTimes(1)
  })

  it('idle while waiting for a request this page queued: waits, then gives up after the bound', async () => {
    const { job, deps, loadRunState } = build(scoped)
    deps.analyzing.value = true
    for (let i = 0; i < IDLE_POLLS_BEFORE_GIVING_UP; i++) await job.pollJobStatus()
    expect(deps.analyzing.value).toBe(true)
    expect(loadRunState).not.toHaveBeenCalled()
    await job.pollJobStatus()
    expect(deps.analyzing.value).toBe(false)
    expect(loadRunState).toHaveBeenCalledTimes(1)
  })

  it('page open while queued starts polling, without the "already running" notice', async () => {
    vi.useFakeTimers()
    try {
      fetchWithAuth.mockResolvedValue(respond(QUEUED))
      const { job, deps } = build(scoped)
      await job.checkCurrentIndexingJob()
      expect(deps.analyzing.value).toBe(true)
      expect(deps.progressStatus.value).toBe('analytics.codebase.status.queued')
      expect(deps.progressPercent.value).toBe(0)
      expect(job.currentJobId.value).toBeNull()
      expect(deps.notify).not.toHaveBeenCalled()
      const before = currentCalls().length
      await vi.advanceTimersByTimeAsync(2100)
      expect(currentCalls().length).toBeGreaterThan(before)
      job.stopJobPolling()
    } finally {
      vi.useRealTimers()
    }
  })

  it('cancel while only queued posts nothing (it would stop another source\'s job)', async () => {
    fetchWithAuth.mockResolvedValue(respond(QUEUED))
    const { job } = build(scoped)
    await job.pollJobStatus()
    fetchWithAuth.mockClear()
    await job.cancelIndexingJob()
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })
})

describe('a source switch while a job is tracked (#20513)', () => {
  const RUNNING = { has_active_job: true, task_id: 't9', source_id: 'autobot', status: 'running', progress: {} }
  const QUEUED_B = { has_active_job: true, task_id: null, source_id: 'autobot', status: 'queued', position: 1 }
  const IDLE_B = { has_active_job: false, task_id: null, status: 'idle' }
  const indexCalls = () => fetchWithAuth.mock.calls.map((c) => c[0] as string).filter((u) => u.includes('/index/current'))

  beforeEach(() => {
    fetchWithAuth.mockReset()
  })

  it('mounting fires no extra /index/current request', async () => {
    const source = ref('a')
    build((url) => `${url}?${source.value}`, vi.fn(async () => {}), () => source.value)
    await nextTick()
    await flushPromises()
    expect(indexCalls()).toHaveLength(0)
  })

  it('switching while polling a running job drops it: id cleared, cancel posts nothing', async () => {
    vi.useFakeTimers()
    try {
      const source = ref('a')
      fetchWithAuth.mockImplementation(async (url: string) => respond(url.includes('source_id=b') ? IDLE_B : RUNNING))
      const { job, deps } = build((url) => `${url}?source_id=${source.value}`, vi.fn(async () => {}), () => source.value)
      await job.checkCurrentIndexingJob()
      expect(job.currentJobId.value).toBe('t9')
      source.value = 'b'
      await nextTick()
      await flushPromises()
      expect(job.currentJobId.value).toBeNull()
      expect(deps.analyzing.value).toBe(false)
      fetchWithAuth.mockClear()
      await job.cancelIndexingJob()
      expect(fetchWithAuth).not.toHaveBeenCalled()
      job.stopJobPolling()
    } finally {
      vi.useRealTimers()
    }
  })

  it('switching to a source with a queued request shows the queued text and polls for it', async () => {
    vi.useFakeTimers()
    try {
      const source = ref('a')
      fetchWithAuth.mockImplementation(async (url: string) => respond(url.includes('source_id=b') ? QUEUED_B : RUNNING))
      const { job, deps } = build((url) => `${url}?source_id=${source.value}`, vi.fn(async () => {}), () => source.value)
      await job.checkCurrentIndexingJob()
      source.value = 'b'
      await nextTick()
      await flushPromises()
      expect(deps.progressStatus.value).toBe('analytics.codebase.status.queued')
      expect(job.currentJobId.value).toBeNull()
      const before = indexCalls().length
      await vi.advanceTimersByTimeAsync(2100)
      const added = indexCalls().slice(before)
      expect(added.length).toBeGreaterThan(0)
      expect(added.every((u) => u.includes('source_id=b'))).toBe(true)
      job.stopJobPolling()
    } finally {
      vi.useRealTimers()
    }
  })
})
