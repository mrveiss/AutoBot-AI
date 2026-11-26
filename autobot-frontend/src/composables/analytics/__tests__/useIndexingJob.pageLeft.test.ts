// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * A page that was left ends its indexing-job session (#21474).
 *
 * A source switch remounts the project page. The previous page could still be awaiting
 * `/index/current`; its answer then resumed `checkCurrentIndexingJob`, which showed "indexing
 * already running" for the source the user had left and started job polling that nothing owned.
 * Disposing the page's scope now ends the poll session, so the late answer writes nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { useIndexingJob, type UseIndexingJobDeps } from '../useIndexingJob'

const { fetchWithAuth, getServiceUrl } = vi.hoisted(() => ({ fetchWithAuth: vi.fn(), getServiceUrl: vi.fn() }))
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl } }))

const RUNNING = { has_active_job: true, task_id: 't9', source_id: 'autobot', status: 'running', progress: { percent: 40 } }
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const currentCalls = () => fetchWithAuth.mock.calls.filter((c) => (c[0] as string).includes('/index/current')).length

function deps(): UseIndexingJobDeps {
  return {
    rootPath: ref('/repo'),
    analyzing: ref(false),
    progressPercent: ref(0),
    progressStatus: ref(''),
    selectedSource: ref({ id: 'autobot' }),
    withSourceId: (url: string) => `${url}?source_id=autobot`,
    sourceKey: () => 'source_id=autobot',
    notify: vi.fn(),
    t: (key: string) => key,
    problemsReport: ref([]),
    codebaseStats: ref(null),
    declarationAnalysis: ref([]),
    duplicateAnalysis: ref([]),
    hardcodeAnalysis: ref([]),
    chartData: ref(null),
    runState: { loadRunState: vi.fn(async () => {}), run: ref(null), readFailed: ref(false) },
    showKnowledgeBaseOptIn: ref(false),
    onIndexComplete: vi.fn(async () => {}),
    storageKeyPath: 'k',
  } as unknown as UseIndexingJobDeps
}

beforeEach(() => {
  getServiceUrl.mockResolvedValue('http://backend')
  fetchWithAuth.mockReset()
})

describe('checkCurrentIndexingJob after the page was left (#21474)', () => {
  // `/index/current` has already answered (its data is assigned) while the run-state read the same
  // step awaits is still out; the page is left in that window. `useApiResource` drops answers that
  // arrive after disposal, so it is this window -- an answer already taken -- that reached the writes.
  it('an active job read before unmount, resumed after it, shows nothing and starts no polling', async () => {
    fetchWithAuth.mockResolvedValue(respond(RUNNING))
    let runStateRead!: () => void
    const d = deps()
    vi.mocked(d.runState.loadRunState).mockImplementation(() => new Promise<void>((resolve) => { runStateRead = resolve }))
    const scope = effectScope()
    const job = scope.run(() => useIndexingJob(d))!

    const checking = job.checkCurrentIndexingJob(true)
    await vi.waitFor(() => expect(currentCalls()).toBe(1))
    await new Promise((resolve) => setTimeout(resolve, 0)) // the /index/current answer is taken
    scope.stop()
    runStateRead()
    await checking
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(d.notify).not.toHaveBeenCalled()
    expect(d.analyzing.value).toBe(false)
    expect(job.currentJobId.value).toBeNull()
    expect(currentCalls()).toBe(1) // no poll tick: polling was never started
  })

  it('control: the same answer while the page is open shows the running job and polls', async () => {
    fetchWithAuth.mockResolvedValue(respond(RUNNING))
    const d = deps()
    const scope = effectScope()
    const job = scope.run(() => useIndexingJob(d))!

    await job.checkCurrentIndexingJob(false)

    expect(d.notify).toHaveBeenCalledWith('analytics.codebase.notify.indexingAlreadyRunning', 'info')
    expect(d.analyzing.value).toBe(true)
    await vi.waitFor(() => expect(currentCalls()).toBeGreaterThan(1))
    scope.stop()
  })
})
