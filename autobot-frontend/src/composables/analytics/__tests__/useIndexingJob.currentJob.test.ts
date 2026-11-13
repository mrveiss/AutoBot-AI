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
import { IDLE_POLLS_BEFORE_GIVING_UP, useIndexingJob, type UseIndexingJobDeps } from '../useIndexingJob'
import type { CodebaseRunState } from '../useRunState'

const { fetchWithAuth, getServiceUrl } = vi.hoisted(() => ({ fetchWithAuth: vi.fn(), getServiceUrl: vi.fn() }))
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl } }))

// `mockReset: true` wipes implementations between tests, so they are (re)applied here.
beforeEach(() => {
  getServiceUrl.mockResolvedValue('http://backend')
})

const IDLE = { has_active_job: false, task_id: null, status: 'idle' }
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const scoped = (url: string) => `${url}?source_id=autobot`

function build(
  withSourceId: (url: string) => string,
  loadRunState = vi.fn(async () => {}),
  sourceKey: () => string = () => 'source_id=autobot',
  known = { run: ref<CodebaseRunState | null>(null), readFailed: ref(false) },
) {
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
    runState: { loadRunState, ...known },
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

  it('a tracked job followed by queued (the slot went to another source) drops the old task id: Stop posts nothing', async () => {
    fetchWithAuth.mockResolvedValueOnce(respond({ ...RUNNING, progress: { percent: 40 } })).mockResolvedValue(respond(QUEUED))
    const { job, deps } = build(scoped)
    await job.pollJobStatus()
    expect([job.currentJobId.value, deps.progressPercent.value]).toEqual(['t9', 40])
    await job.pollJobStatus() // the tracked job ended and another source's job took the slot
    expect([job.currentJobId.value, deps.progressPercent.value]).toEqual([null, 0])
    expect(deps.progressStatus.value).toBe('analytics.codebase.status.queued')
    fetchWithAuth.mockClear()
    await job.cancelIndexingJob() // the cancel route is not source-scoped: it would stop the other source's job
    expect(fetchWithAuth).not.toHaveBeenCalled()
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

describe('a tracked job that left the task slot answers idle: its outcome is read off the run record (#21003)', () => {
  const QUEUED = { has_active_job: true, task_id: null, source_id: 'autobot', status: 'queued', position: 1 }
  const RUNNING = { has_active_job: true, task_id: 't9', source_id: 'autobot', status: 'running', progress: {} }
  const record = (over: Partial<CodebaseRunState>): CodebaseRunState => ({
    run_id: 't9', status: 'completed', partial: false, reason: '', started_at: 's', finished_at: 'f', last_completed_at: 'f', ...over,
  })
  /** The run-state read answers `answer`; `failed` makes it a read that failed (what was known stays). */
  function reading(answer: CodebaseRunState | null, failed = false) {
    const known = { run: ref<CodebaseRunState | null>(failed ? answer : null), readFailed: ref(false) }
    const loadRunState = vi.fn(async () => {
      if (failed) known.readFailed.value = true
      else known.run.value = answer
    })
    return build(scoped, loadRunState, undefined, known)
  }

  beforeEach(() => {
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue(respond(IDLE))
  })

  it('queued then idle with a completed record: completion is announced and the follow-up scans run', async () => {
    fetchWithAuth.mockResolvedValueOnce(respond(QUEUED))
    const { job, deps } = reading(record({ run_id: 'minted-later' }))
    await job.pollJobStatus()
    await job.pollJobStatus() // the job started and ended between two polls
    expect(deps.onIndexComplete).toHaveBeenCalledTimes(1)
    expect(deps.notify).toHaveBeenCalledWith('analytics.codebase.notify.indexingCompleted', 'success')
    expect([deps.analyzing.value, deps.progressPercent.value]).toEqual([false, 100])
  })

  it('running then idle with a killed record of that job: the failure and its reason are announced', async () => {
    fetchWithAuth.mockResolvedValueOnce(respond(RUNNING))
    const { job, deps } = reading(record({ status: 'killed', partial: true, reason: 'killed by the hard timeout' }))
    await job.pollJobStatus()
    await job.pollJobStatus()
    expect(deps.onIndexComplete).not.toHaveBeenCalled()
    expect(deps.notify).toHaveBeenCalledWith('analytics.codebase.notify.indexingFailed', 'error')
    expect(job.currentJobId.value).toBeNull()
  })

  it('nothing is announced when the record is of another run, or could not be read', async () => {
    for (const made of [reading(record({ run_id: 'older' })), reading(record({}), true)]) {
      fetchWithAuth.mockResolvedValueOnce(respond(RUNNING))
      await made.job.pollJobStatus()
      await made.job.pollJobStatus()
      expect(made.loadRunState).toHaveBeenCalledTimes(1)
      expect(made.deps.onIndexComplete).not.toHaveBeenCalled()
      expect(made.deps.notify).not.toHaveBeenCalled()
      expect(made.deps.analyzing.value).toBe(false)
    }
  })

  it('control: a wait that was given up (no job ever seen) announces nothing, whatever the record says', async () => {
    const { job, deps } = reading(record({}))
    for (let i = 0; i <= IDLE_POLLS_BEFORE_GIVING_UP; i++) await job.pollJobStatus()
    expect(deps.analyzing.value).toBe(false)
    expect(deps.onIndexComplete).not.toHaveBeenCalled()
    expect(deps.notify).not.toHaveBeenCalled()
  })
})

describe('a source switch while a job is tracked (#20513)', () => {
  const RUNNING_A = { has_active_job: true, task_id: 'ta', source_id: 'a', status: 'running', progress: {} }
  // A body that names no source cannot be told apart by `jobBelongsToSource`, so only the poll
  // session stops it from landing on the page after a switch.
  const RUNNING_A_UNNAMED = { has_active_job: true, task_id: 'ta', status: 'running', progress: {} }
  const RUNNING_B = { has_active_job: true, task_id: 'tb', source_id: 'b', status: 'running', progress: {} }
  const QUEUED_B = { has_active_job: true, task_id: null, source_id: 'b', status: 'queued', position: 1 }
  const IDLE_B = { has_active_job: false, task_id: null, source_id: 'b', status: 'idle' }
  const DONE_A = { has_active_job: false, task_id: 'ta', source_id: 'a', status: 'completed' }
  const callsTo = (part: string) => fetchWithAuth.mock.calls.map((c) => c[0] as string).filter((u) => u.includes(part))

  const deferred = () => {
    let resolve!: () => void
    const promise = new Promise<void>((r) => { resolve = r })
    return { promise, resolve }
  }
  /** Lets every pending continuation run: a macrotask boundary, not a count of ticks. */
  const settle = async () => {
    if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(0)
    else await new Promise<void>((r) => setTimeout(r, 0))
  }
  /** A request is held until its `kind:source` gate resolves; an aborted request rejects like a real fetch. */
  type Holds = Record<string, Promise<void> | undefined>
  const route = (bodies: { a: unknown; b: unknown }, holds: Holds) => (url: string, init?: RequestInit) => {
    const src = url.includes('source_id=b') ? 'b' : 'a'
    const kind = url.includes('/index/current') ? 'current'
      : url.includes('/index/cancel') ? 'cancel'
        : url.includes('/codebase/problems') ? 'problems'
          : url.includes('/codebase/stats') ? 'stats' : 'other'
    const answer = async () => {
      await holds[`${kind}:${src}`]
      if (kind === 'problems') return respond({ problems: [{ from: src }] })
      if (kind === 'stats') return respond({ stats: { from: src } })
      if (kind === 'cancel') return respond({ success: true })
      return respond(src === 'b' ? bodies.b : bodies.a)
    }
    return new Promise((resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
      answer().then(resolve, reject)
    })
  }

  function rig(bodies: { a: unknown; b: unknown }) {
    const holds: Holds = {}
    const source = ref('a')
    const made = build((url) => `${url}?source_id=${source.value}`, vi.fn(async () => {}), () => source.value)
    made.deps.selectedSource.value = { id: 'a' }
    fetchWithAuth.mockImplementation(route(bodies, holds))
    const switchTo = async (id: string) => {
      made.deps.selectedSource.value = { id }
      source.value = id
      await nextTick()
      await settle()
    }
    return { ...made, holds, switchTo }
  }

  beforeEach(() => {
    fetchWithAuth.mockReset()
  })

  it('mounting fires no extra /index/current request', async () => {
    const source = ref('a')
    build((url) => `${url}?${source.value}`, vi.fn(async () => {}), () => source.value)
    await nextTick()
    await settle()
    expect(callsTo('/index/current')).toHaveLength(0)
  })

  it('switching while polling a running job drops it: id cleared, cancel posts nothing, run state read once', async () => {
    vi.useFakeTimers()
    try {
      const { job, deps, loadRunState, switchTo } = rig({ a: RUNNING_A, b: IDLE_B })
      await job.checkCurrentIndexingJob()
      expect(job.currentJobId.value).toBe('ta')
      const runStateReads = loadRunState.mock.calls.length
      await switchTo('b')
      expect(job.currentJobId.value).toBeNull()
      expect(deps.analyzing.value).toBe(false)
      expect(loadRunState.mock.calls.length).toBe(runStateReads) // the run-state composable re-reads it on a switch itself
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
      const { job, deps, switchTo } = rig({ a: RUNNING_A, b: QUEUED_B })
      await job.checkCurrentIndexingJob()
      await switchTo('b')
      expect(deps.progressStatus.value).toBe('analytics.codebase.status.queued')
      expect(job.currentJobId.value).toBeNull()
      const before = callsTo('/index/current').length
      await vi.advanceTimersByTimeAsync(2100)
      const added = callsTo('/index/current').slice(before)
      expect(added.length).toBeGreaterThan(0)
      expect(added.every((u) => u.includes('source_id=b'))).toBe(true)
      job.stopJobPolling()
    } finally {
      vi.useRealTimers()
    }
  })

  it('a poll of the old source that resumes after the switch writes nothing (fails without the poll session: id and analyzing come back)', async () => {
    const { job, deps, holds, switchTo } = rig({ a: RUNNING_A_UNNAMED, b: IDLE_B })
    try {
      await job.pollJobStatus()
      expect(job.currentJobId.value).toBe('ta')
      holds['current:a'] = deferred().promise // never answered: the switch aborts it
      const answerB = deferred()
      holds['current:b'] = answerB.promise // the new source has not answered when the old poll resumes
      const inflight = job.pollJobStatus()
      await settle()
      const intermediate = callsTo('/codebase/problems').length
      await switchTo('b')
      await inflight
      await settle()
      expect(job.currentJobId.value).toBeNull()
      expect(deps.analyzing.value).toBe(false)
      expect(callsTo('/codebase/problems')).toHaveLength(intermediate) // no intermediate polling for the old job
      answerB.resolve()
      await settle()
      expect(job.currentJobId.value).toBeNull()
      expect(deps.analyzing.value).toBe(false)
    } finally {
      job.stopJobPolling()
    }
  })

  it('intermediate problems and stats of the old source that arrive after the switch do not replace the new source\'s', async () => {
    const { job, deps, holds, switchTo } = rig({ a: RUNNING_A, b: IDLE_B })
    try {
      const problemsA = deferred()
      const statsA = deferred()
      holds['problems:a'] = problemsA.promise
      holds['stats:a'] = statsA.promise
      const inflight = job.pollJobStatus() // sets the id, then waits for the intermediate results
      await settle()
      expect(callsTo('/codebase/problems')).toHaveLength(1)
      await switchTo('b')
      deps.problemsReport.value = [{ from: 'b' }]
      deps.codebaseStats.value = { from: 'b' }
      problemsA.resolve()
      statsA.resolve()
      await inflight
      await settle()
      expect(deps.problemsReport.value).toEqual([{ from: 'b' }])
      expect(deps.codebaseStats.value).toEqual({ from: 'b' })
      expect(job.currentJobId.value).toBeNull()
    } finally {
      job.stopJobPolling()
    }
  })

  it('a job of the old source that finishes after the switch does not clear the new source\'s job id', async () => {
    const { job, deps, switchTo } = rig({ a: DONE_A, b: RUNNING_B })
    try {
      const followUp = deferred()
      vi.mocked(deps.onIndexComplete).mockImplementation(() => followUp.promise)
      const finished = job.pollJobStatus() // A ended: notice shown, now awaiting the follow-up scans
      await settle()
      expect(deps.notify).toHaveBeenCalledTimes(1)
      await switchTo('b')
      expect(job.currentJobId.value).toBe('tb')
      followUp.resolve()
      await finished
      await settle()
      expect(job.currentJobId.value).toBe('tb')
      expect(deps.analyzing.value).toBe(true)
      expect(deps.notify).toHaveBeenCalledTimes(2) // A's completion, then B's "already running" notice; nothing else
    } finally {
      job.stopJobPolling()
    }
  })

  it('a cancel of the old source that is answered after the switch does not stop the new source\'s job', async () => {
    const { job, deps, holds, switchTo } = rig({ a: RUNNING_A, b: RUNNING_B })
    try {
      await job.pollJobStatus()
      const cancelAnswer = deferred()
      holds['cancel:a'] = cancelAnswer.promise
      const cancelling = job.cancelIndexingJob()
      await settle()
      await switchTo('b')
      expect(job.currentJobId.value).toBe('tb')
      cancelAnswer.resolve()
      await cancelling
      await settle()
      expect(job.currentJobId.value).toBe('tb')
      expect(deps.analyzing.value).toBe(true)
      expect(deps.notify).not.toHaveBeenCalledWith('analytics.codebase.notify.indexingJobCancelled', 'success')
    } finally {
      job.stopJobPolling()
    }
  })
})
