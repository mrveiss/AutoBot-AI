// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * /index/current is asked for the selected source (#20513), and how the newest run ended is read
 * when the page opens and when a job ends (#21003).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useIndexingJob, type UseIndexingJobDeps } from '../useIndexingJob'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({
  default: { getServiceUrl: vi.fn().mockResolvedValue('http://backend') },
}))

const IDLE = { has_active_job: false, task_id: null, status: 'idle' }
const respond = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) })
const scoped = (url: string) => `${url}?source_id=autobot`

function build(withSourceId: (url: string) => string, loadRunState = vi.fn(async () => {})) {
  const deps = {
    rootPath: ref('/repo'),
    analyzing: ref(false),
    progressPercent: ref(0),
    progressStatus: ref(''),
    selectedSource: ref({ id: 'autobot' }),
    withSourceId,
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
  return { job: useIndexingJob(deps), loadRunState }
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
